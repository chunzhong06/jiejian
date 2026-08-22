from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any

import pytest
from sqlalchemy import text

from product.backend.core.lifecycle import JobState, RunLifecycle
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage import StorageUnitOfWork

pytestmark = pytest.mark.database
from product.backend.infra.runtime.jobs.models import (
    ClaimJob,
    ConfirmRecovery,
    RecoveryOperator,
    RecoveryProofType,
    RecoveryReasonCode,
    RecoveryScan,
    RequestCancellation,
    RetryableFailureCode,
    RetryableFailure,
)

NOW_US = 1_790_000_000_000_000


def _claim_request(job_id: str, **changes: Any) -> ClaimJob:
    values = {
        "job_id": job_id,
        "lease_owner": "worker-1",
        "now_us": NOW_US + 10,
        "lease_duration_us": 1_000,
    }
    return ClaimJob(**(values | changes))


def test_concurrent_identical_submits_create_one_run_and_job(
    worker_services: Any,
) -> None:
    barrier = Barrier(2)

    def submit_once() -> tuple[bool, str, str]:
        barrier.wait()
        result = worker_services.queue.submit(worker_services.submit_request())
        return result.created, result.job.job_id, result.run.run_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(lambda _: submit_once(), range(2)))

    assert sorted(created for created, _, _ in results) == [False, True]
    assert len({job_id for _, job_id, _ in results}) == 1
    assert len({run_id for _, _, run_id in results}) == 1
    with worker_services.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM jobs")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM runs")).scalar_one() == 1


def test_concurrent_claims_allow_exactly_one_worker(
    worker_services: Any,
) -> None:
    submitted = worker_services.queue.submit(worker_services.submit_request())
    barrier = Barrier(2)

    def claim_once(owner: str) -> tuple[str, int | str]:
        barrier.wait()
        try:
            result = worker_services.attempts.claim(
                ClaimJob(
                    job_id=submitted.job.job_id,
                    lease_owner=owner,
                    now_us=NOW_US + 10,
                    lease_duration_us=1_000,
                )
            )
        except JiejianError as exc:
            return "error", exc.code
        assert result is not None
        return "claimed", result.job.fencing_token

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(claim_once, ("worker-1", "worker-2")))

    assert sum(kind == "claimed" for kind, _ in results) == 1
    assert sum(kind == "error" for kind, _ in results) == 1
    assert {value for kind, value in results if kind == "error"} == {
        ErrorCode.JOB_NOT_CLAIMABLE.value
    }
    with StorageUnitOfWork(worker_services.session_factory) as work:
        job = work.jobs.get(submitted.job.job_id)
        assert job is not None
        assert job.attempt == 1 and job.fencing_token == 1
        assert len(work.job_events.list_for_job(job.job_id)) == 2


def test_concurrent_waiting_cancellation_is_idempotent(
    worker_services: Any,
) -> None:
    submitted = worker_services.queue.submit(worker_services.submit_request())
    barrier = Barrier(2)

    def cancel_once() -> tuple[bool, int]:
        barrier.wait()
        result = worker_services.queue.request_cancellation(
            RequestCancellation(
                job_id=submitted.job.job_id,
                now_us=NOW_US + 5,
            )
        )
        return result.completed, result.first_requested_at_us

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(lambda _: cancel_once(), range(2)))

    assert results == ((True, NOW_US + 5), (True, NOW_US + 5))
    with StorageUnitOfWork(worker_services.session_factory) as work:
        events = work.job_events.list_for_job(submitted.job.job_id)
        assert [event.event_type for event in events] == [
            "JOB_SUBMITTED",
            "JOB_CANCEL_REQUESTED",
            "JOB_CANCELLED",
        ]


def test_future_available_job_is_not_claimable(worker_services: Any) -> None:
    submitted = worker_services.queue.submit(
        worker_services.submit_request(available_at_us=NOW_US + 100)
    )
    with pytest.raises(JiejianError) as captured:
        worker_services.attempts.claim(
            _claim_request(submitted.job.job_id, now_us=NOW_US + 99)
        )
    assert captured.value.code == ErrorCode.JOB_NOT_CLAIMABLE.value
    claimed = worker_services.attempts.claim(
        _claim_request(submitted.job.job_id, now_us=NOW_US + 100)
    )
    assert claimed is not None and claimed.job.state is JobState.RUNNING


def test_expired_lease_is_only_listed_and_cannot_be_claimed_again(
    worker_services: Any,
) -> None:
    submitted = worker_services.queue.submit(worker_services.submit_request())
    claimed = worker_services.attempts.claim(
        _claim_request(submitted.job.job_id, lease_duration_us=10)
    )
    assert claimed is not None
    candidates = worker_services.recovery.list_recovery_candidates(
        RecoveryScan(now_us=NOW_US + 20)
    )
    assert [(item.job_id, item.fencing_token) for item in candidates] == [
        (claimed.job.job_id, claimed.job.fencing_token)
    ]
    with pytest.raises(JiejianError) as captured:
        worker_services.attempts.claim(
            _claim_request(
                submitted.job.job_id,
                lease_owner="worker-2",
                now_us=NOW_US + 20,
            )
        )
    assert captured.value.code == ErrorCode.JOB_RECOVERY_REQUIRED.value
    with StorageUnitOfWork(worker_services.session_factory) as work:
        persisted = work.jobs.get(claimed.job.job_id)
        assert persisted is not None
        assert persisted.state is JobState.RUNNING
        assert persisted.fencing_token == claimed.job.fencing_token
        assert len(work.job_events.list_for_job(persisted.job_id)) == 2


@pytest.mark.parametrize(
    ("proof_type", "reason_code"),
    [
        (
            RecoveryProofType.EXECUTION_EXITED,
            RecoveryReasonCode.PROCESS_EXIT_CONFIRMED,
        ),
        (
            RecoveryProofType.CLEANUP_COMPLETED,
            RecoveryReasonCode.CLEANUP_CONFIRMED,
        ),
    ],
)
def test_both_recovery_proofs_release_expired_job_and_invalidate_old_token(
    worker_services: Any,
    proof_type: RecoveryProofType,
    reason_code: RecoveryReasonCode,
) -> None:
    submitted = worker_services.queue.submit(worker_services.submit_request())
    claimed = worker_services.attempts.claim(
        _claim_request(submitted.job.job_id, lease_duration_us=10)
    )
    assert claimed is not None
    recovered = worker_services.recovery.confirm_recovery(
        ConfirmRecovery(
            job_id=claimed.job.job_id,
            lease_owner="worker-1",
            fencing_token=claimed.job.fencing_token,
            now_us=NOW_US + 20,
            proof_type=proof_type,
            operator=RecoveryOperator.RECOVERY_CONTROLLER,
            reason_code=reason_code,
        )
    )
    assert recovered.job.state is JobState.RETRY_WAIT
    assert recovered.job.lease_owner is None
    assert recovered.job.fencing_token == claimed.job.fencing_token

    with pytest.raises(JiejianError) as stale:
        worker_services.recovery.confirm_recovery(
            ConfirmRecovery(
                job_id=claimed.job.job_id,
                lease_owner="worker-1",
                fencing_token=claimed.job.fencing_token,
                now_us=NOW_US + 21,
                proof_type=proof_type,
                operator=RecoveryOperator.RECOVERY_CONTROLLER,
                reason_code=reason_code,
            )
        )
    assert stale.value.code == ErrorCode.JOB_LEASE_MISMATCH.value

    next_claim = worker_services.attempts.claim(
        _claim_request(
            submitted.job.job_id,
            lease_owner="worker-2",
            now_us=recovered.job.available_at_us,
        )
    )
    assert next_claim is not None
    assert next_claim.job.fencing_token == claimed.job.fencing_token + 1
    assert next_claim.job.attempt == claimed.job.attempt + 1


def test_recovery_at_attempt_limit_fails_job_and_run_without_verdict(
    worker_services: Any,
) -> None:
    submitted = worker_services.queue.submit(
        worker_services.submit_request(max_attempts=1)
    )
    claimed = worker_services.attempts.claim(
        _claim_request(submitted.job.job_id, lease_duration_us=10)
    )
    assert claimed is not None
    recovered = worker_services.recovery.confirm_recovery(
        ConfirmRecovery(
            job_id=claimed.job.job_id,
            lease_owner="worker-1",
            fencing_token=claimed.job.fencing_token,
            now_us=NOW_US + 20,
            proof_type=RecoveryProofType.EXECUTION_EXITED,
            operator=RecoveryOperator.WORKER_SUPERVISOR,
            reason_code=RecoveryReasonCode.PROCESS_EXIT_CONFIRMED,
        )
    )
    assert recovered.job.state is JobState.FAILED
    assert recovered.run.lifecycle is RunLifecycle.FAILED
    assert recovered.run.verdict is None
    with pytest.raises(JiejianError) as exhausted:
        worker_services.attempts.claim(
            _claim_request(submitted.job.job_id, now_us=NOW_US + 30)
        )
    assert exhausted.value.code == ErrorCode.JOB_TERMINAL_CONFLICT.value


def test_expired_running_cancellation_recovers_to_cancelled_without_retry(
    worker_services: Any,
) -> None:
    submitted = worker_services.queue.submit(worker_services.submit_request())
    claimed = worker_services.attempts.claim(
        _claim_request(submitted.job.job_id, lease_duration_us=10)
    )
    assert claimed is not None
    requested = worker_services.queue.request_cancellation(
        RequestCancellation(job_id=claimed.job.job_id, now_us=NOW_US + 11)
    )
    assert requested.job.state is JobState.RUNNING

    recovered = worker_services.recovery.confirm_recovery(
        ConfirmRecovery(
            job_id=claimed.job.job_id,
            lease_owner="worker-1",
            fencing_token=claimed.job.fencing_token,
            now_us=NOW_US + 20,
            proof_type=RecoveryProofType.EXECUTION_EXITED,
            operator=RecoveryOperator.WORKER_SUPERVISOR,
            reason_code=RecoveryReasonCode.PROCESS_EXIT_CONFIRMED,
        )
    )

    assert recovered.job.state is JobState.CANCELLED
    assert recovered.run.lifecycle is RunLifecycle.CANCELLED
    with pytest.raises(JiejianError) as terminal:
        worker_services.attempts.claim(
            _claim_request(recovered.job.job_id, now_us=NOW_US + 30)
        )
    assert terminal.value.code == ErrorCode.JOB_TERMINAL_CONFLICT.value


def test_retry_wait_cancel_keeps_first_request_time_and_never_reclaims(
    worker_services: Any,
) -> None:
    submitted = worker_services.queue.submit(worker_services.submit_request())
    claimed = worker_services.attempts.claim(_claim_request(submitted.job.job_id))
    assert claimed is not None
    waiting = worker_services.attempts.record_retryable_failure(
        RetryableFailure(
            job_id=claimed.job.job_id,
            lease_owner="worker-1",
            fencing_token=claimed.job.fencing_token,
            now_us=NOW_US + 20,
            reason_code=RetryableFailureCode.WORKER_INTERRUPTED,
        )
    )
    cancelled = worker_services.queue.request_cancellation(
        RequestCancellation(
            job_id=waiting.job.job_id,
            now_us=NOW_US + 21,
        )
    )
    assert cancelled.job.state is JobState.CANCELLED
    assert cancelled.first_requested_at_us == NOW_US + 21
    with pytest.raises(JiejianError) as terminal:
        worker_services.attempts.claim(
            _claim_request(
                waiting.job.job_id,
                now_us=waiting.job.available_at_us,
            )
        )
    assert terminal.value.code == ErrorCode.JOB_TERMINAL_CONFLICT.value


def test_recovery_event_metadata_is_stable_and_owner_is_not_copied(
    worker_services: Any,
) -> None:
    submitted = worker_services.queue.submit(worker_services.submit_request())
    claimed = worker_services.attempts.claim(
        _claim_request(submitted.job.job_id, lease_duration_us=10)
    )
    assert claimed is not None
    worker_services.recovery.confirm_recovery(
        ConfirmRecovery(
            job_id=claimed.job.job_id,
            lease_owner="worker-1",
            fencing_token=claimed.job.fencing_token,
            now_us=NOW_US + 20,
            proof_type=RecoveryProofType.CLEANUP_COMPLETED,
            operator=RecoveryOperator.WORKER_SUPERVISOR,
            reason_code=RecoveryReasonCode.CLEANUP_CONFIRMED,
        )
    )
    with StorageUnitOfWork(worker_services.session_factory) as work:
        events = work.job_events.list_for_job(claimed.job.job_id)
        assert [event.sequence for event in events] == [1, 2, 3]
        recovery = events[-1]
        assert recovery.event_type == "JOB_RECOVERY_CONFIRMED"
        assert recovery.metadata["proof_type"] == "CLEANUP_COMPLETED"
        assert "lease_owner" not in recovery.metadata
        assert "worker-1" not in repr(recovery.metadata)


def test_known_secret_as_owner_is_rejected_without_owner_echo(
    worker_services: Any,
) -> None:
    submitted = worker_services.queue.submit(worker_services.submit_request())
    sentinel = "stage22-owner-secret"
    with pytest.raises(JiejianError) as captured:
        worker_services.attempts.claim(
            ClaimJob(
                job_id=submitted.job.job_id,
                lease_owner=sentinel,
                now_us=NOW_US + 10,
                lease_duration_us=1_000,
            ),
            known_secrets=(sentinel,),
        )
    assert captured.value.code == ErrorCode.JOB_SECRET.value
    assert sentinel not in str(captured.value) + repr(captured.value.to_dict())
    with StorageUnitOfWork(worker_services.session_factory) as work:
        job = work.jobs.get(submitted.job.job_id)
        assert job is not None and job.state is JobState.PENDING
