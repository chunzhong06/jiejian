from __future__ import annotations

from functools import partial
from typing import Any

import pytest
from sqlalchemy import text

from product.backend.core.lifecycle import JobState, RunLifecycle
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage import StorageUnitOfWork, create_session_factory, create_sqlite_engine
from product.backend.infra.storage import JobEventRepository

pytestmark = pytest.mark.database
from product.backend.infra.runtime.jobs.attempts import JobAttempts
from product.backend.infra.runtime.jobs.models import (
    ClaimJob,
    CompleteCancellation,
    FatalFailureCode,
    FatalFailure,
    RequestCancellation,
    RetryPolicy,
    RetryableFailureCode,
    RetryableFailure,
    RenewLease,
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


def test_submit_is_idempotent_and_appends_only_one_initial_event(
    worker_services: Any,
) -> None:
    first = worker_services.queue.submit(worker_services.submit_request())
    reused = worker_services.queue.submit(worker_services.submit_request())

    assert first.created is True
    assert reused.created is False
    assert reused.job.job_id == first.job.job_id
    assert reused.run.run_id == first.run.run_id
    with StorageUnitOfWork(worker_services.session_factory) as work:
        events = work.job_events.list_for_job(first.job.job_id)
        assert [(event.sequence, event.event_type) for event in events] == [
            (1, "JOB_SUBMITTED")
        ]


def test_submit_same_scope_with_different_hash_is_stable_conflict(
    worker_services: Any,
) -> None:
    worker_services.queue.submit(worker_services.submit_request())
    with pytest.raises(JiejianError) as captured:
        worker_services.queue.submit(
            worker_services.submit_request(request_hash="b" * 64)
        )
    assert captured.value.code == ErrorCode.JOB_IDEMPOTENCY_CONFLICT.value
    assert captured.value.to_dict()["details"] == {}


def test_pending_cancel_is_atomic_and_first_time_is_immutable(
    worker_services: Any,
) -> None:
    submitted = worker_services.queue.submit(worker_services.submit_request())
    first = worker_services.queue.request_cancellation(
        RequestCancellation(job_id=submitted.job.job_id, now_us=NOW_US + 5)
    )
    repeated = worker_services.queue.request_cancellation(
        RequestCancellation(job_id=submitted.job.job_id, now_us=NOW_US + 9)
    )

    assert first.completed is repeated.completed is True
    assert first.first_requested_at_us == repeated.first_requested_at_us == NOW_US + 5
    assert repeated.job.state is JobState.CANCELLED
    assert repeated.run.lifecycle is RunLifecycle.CANCELLED
    assert repeated.run.verdict is None
    with StorageUnitOfWork(worker_services.session_factory) as work:
        events = work.job_events.list_for_job(submitted.job.job_id)
        assert [event.event_type for event in events] == [
            "JOB_SUBMITTED",
            "JOB_CANCEL_REQUESTED",
            "JOB_CANCELLED",
        ]
        assert [event.sequence for event in events] == [1, 2, 3]


def test_running_cancel_waits_for_matching_fenced_cleanup(
    worker_services: Any,
) -> None:
    submitted = worker_services.queue.submit(worker_services.submit_request())
    claimed = worker_services.attempts.claim(_claim_request(submitted.job.job_id))
    assert claimed is not None
    requested = worker_services.queue.request_cancellation(
        RequestCancellation(job_id=submitted.job.job_id, now_us=NOW_US + 20)
    )

    assert requested.completed is False
    assert requested.job.state is JobState.RUNNING
    assert requested.run.lifecycle is RunLifecycle.PREFLIGHT
    with pytest.raises(JiejianError) as stale:
        worker_services.attempts.complete_cancellation(
            CompleteCancellation(
                job_id=submitted.job.job_id,
                lease_owner="worker-2",
                fencing_token=claimed.job.fencing_token,
                now_us=NOW_US + 21,
            )
        )
    assert stale.value.code == ErrorCode.JOB_LEASE_MISMATCH.value

    completed = worker_services.attempts.complete_cancellation(
        CompleteCancellation(
            job_id=submitted.job.job_id,
            lease_owner="worker-1",
            fencing_token=claimed.job.fencing_token,
            now_us=NOW_US + 22,
        )
    )
    assert completed.completed is True
    assert completed.job.state is JobState.CANCELLED
    assert completed.run.lifecycle is RunLifecycle.CANCELLED
    assert completed.run.verdict is None


def test_renewal_preserves_attempt_and_token_and_rejects_stale_fence(
    worker_services: Any,
) -> None:
    submitted = worker_services.queue.submit(worker_services.submit_request())
    claimed = worker_services.attempts.claim(_claim_request(submitted.job.job_id))
    assert claimed is not None
    renewed = worker_services.attempts.renew_lease(
        RenewLease(
            job_id=claimed.job.job_id,
            lease_owner="worker-1",
            fencing_token=claimed.job.fencing_token,
            now_us=NOW_US + 20,
            lease_expires_at_us=NOW_US + 2_000,
        )
    )
    assert renewed.job.attempt == claimed.job.attempt
    assert renewed.job.fencing_token == claimed.job.fencing_token
    assert renewed.job.lease_expires_at_us == NOW_US + 2_000

    with pytest.raises(JiejianError) as stale:
        worker_services.attempts.renew_lease(
            RenewLease(
                job_id=claimed.job.job_id,
                lease_owner="worker-1",
                fencing_token=claimed.job.fencing_token + 1,
                now_us=NOW_US + 21,
                lease_expires_at_us=NOW_US + 3_000,
            )
        )
    assert stale.value.code == ErrorCode.JOB_LEASE_MISMATCH.value


def test_expired_lease_cannot_renew_or_write_attempt_result(
    worker_services: Any,
) -> None:
    submitted = worker_services.queue.submit(worker_services.submit_request())
    claimed = worker_services.attempts.claim(
        _claim_request(submitted.job.job_id, lease_duration_us=10)
    )
    assert claimed is not None
    expired_at = NOW_US + 21
    with pytest.raises(JiejianError) as renewal:
        worker_services.attempts.renew_lease(
            RenewLease(
                job_id=claimed.job.job_id,
                lease_owner="worker-1",
                fencing_token=claimed.job.fencing_token,
                now_us=expired_at,
                lease_expires_at_us=expired_at + 100,
            )
        )
    assert renewal.value.code == ErrorCode.JOB_LEASE_EXPIRED.value
    with pytest.raises(JiejianError) as failure:
        worker_services.attempts.record_fatal_failure(
            FatalFailure(
                job_id=claimed.job.job_id,
                lease_owner="worker-1",
                fencing_token=claimed.job.fencing_token,
                now_us=expired_at,
                reason_code=FatalFailureCode.WORKER_FATAL,
            )
        )
    assert failure.value.code == ErrorCode.JOB_RECOVERY_REQUIRED.value
    with StorageUnitOfWork(worker_services.session_factory) as work:
        persisted = work.jobs.get(claimed.job.job_id)
        assert persisted is not None
        assert persisted.state is JobState.RUNNING
        assert persisted.fencing_token == claimed.job.fencing_token


def test_retry_uses_bounded_deterministic_backoff_and_next_claim_new_token(
    worker_services: Any,
) -> None:
    attempts = JobAttempts(
        partial(StorageUnitOfWork, worker_services.session_factory),
        retry_policy=RetryPolicy(
            base_delay_us=100,
            max_delay_us=250,
            max_jitter_us=50,
        ),
        jitter_source=lambda _: 25,
    )
    submitted = worker_services.queue.submit(worker_services.submit_request())
    first = attempts.claim(
        ClaimJob(
            job_id=submitted.job.job_id,
            lease_owner="worker-1",
            now_us=NOW_US + 10,
            lease_duration_us=1_000,
        )
    )
    assert first is not None
    retried = attempts.record_retryable_failure(
        RetryableFailure(
            job_id=first.job.job_id,
            lease_owner="worker-1",
            fencing_token=first.job.fencing_token,
            now_us=NOW_US + 20,
            reason_code=RetryableFailureCode.EXEC_TIMEOUT,
        )
    )
    assert retried.job.state is JobState.RETRY_WAIT
    assert retried.job.available_at_us == NOW_US + 145
    assert retried.run.lifecycle is RunLifecycle.PREFLIGHT
    assert retried.run.verdict is None

    second = attempts.claim(
        ClaimJob(
            job_id=first.job.job_id,
            lease_owner="worker-2",
            now_us=NOW_US + 145,
            lease_duration_us=1_000,
        )
    )
    assert second is not None
    assert second.job.attempt == 2
    assert second.job.fencing_token == first.job.fencing_token + 1


def test_retry_delay_is_capped_and_attempt_exhaustion_fails_run(
    worker_services: Any,
) -> None:
    attempts = JobAttempts(
        partial(StorageUnitOfWork, worker_services.session_factory),
        retry_policy=RetryPolicy(
            base_delay_us=100,
            max_delay_us=100,
            max_jitter_us=0,
        ),
        jitter_source=lambda _: 0,
    )
    submitted = worker_services.queue.submit(
        worker_services.submit_request(max_attempts=2)
    )
    first = attempts.claim(
        ClaimJob(
            job_id=submitted.job.job_id,
            lease_owner="worker-1",
            now_us=NOW_US + 10,
            lease_duration_us=1_000,
        )
    )
    assert first is not None
    waiting = attempts.record_retryable_failure(
        RetryableFailure(
            job_id=first.job.job_id,
            lease_owner="worker-1",
            fencing_token=first.job.fencing_token,
            now_us=NOW_US + 20,
            reason_code=RetryableFailureCode.EXEC_REQUEST,
        )
    )
    assert waiting.job.available_at_us == NOW_US + 120
    second = attempts.claim(
        ClaimJob(
            job_id=first.job.job_id,
            lease_owner="worker-2",
            now_us=NOW_US + 120,
            lease_duration_us=1_000,
        )
    )
    assert second is not None
    failed = attempts.record_retryable_failure(
        RetryableFailure(
            job_id=second.job.job_id,
            lease_owner="worker-2",
            fencing_token=second.job.fencing_token,
            now_us=NOW_US + 130,
            reason_code=RetryableFailureCode.EXEC_REQUEST,
        )
    )
    assert failed.job.state is JobState.FAILED
    assert failed.run.lifecycle is RunLifecycle.FAILED
    assert failed.run.verdict is None


def test_fatal_failure_never_becomes_inconclusive(
    worker_services: Any,
) -> None:
    submitted = worker_services.queue.submit(worker_services.submit_request())
    claimed = worker_services.attempts.claim(_claim_request(submitted.job.job_id))
    assert claimed is not None
    failed = worker_services.attempts.record_fatal_failure(
        FatalFailure(
            job_id=claimed.job.job_id,
            lease_owner="worker-1",
            fencing_token=claimed.job.fencing_token,
            now_us=NOW_US + 20,
            reason_code=FatalFailureCode.PROTOCOL_INVALID,
        )
    )
    assert failed.job.state is JobState.FAILED
    assert failed.run.lifecycle is RunLifecycle.FAILED
    assert failed.run.verdict is None


def test_state_and_event_roll_back_together(
    worker_services: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submitted = worker_services.queue.submit(worker_services.submit_request())

    def reject_event(*_: Any, **__: Any) -> None:
        raise JiejianError(ErrorCode.STORAGE_FAILURE, "固定测试故障")

    monkeypatch.setattr(JobEventRepository, "append", reject_event)
    with pytest.raises(JiejianError):
        worker_services.attempts.claim(_claim_request(submitted.job.job_id))

    with StorageUnitOfWork(worker_services.session_factory) as work:
        job = work.jobs.get(submitted.job.job_id)
        run = work.runs.get(submitted.run.run_id)
        assert job is not None and job.state is JobState.PENDING
        assert job.attempt == 0 and job.fencing_token == 0
        assert run is not None and run.lifecycle is RunLifecycle.QUEUED
        assert len(work.job_events.list_for_job(job.job_id)) == 1


def test_known_secret_and_inline_credential_never_enter_database(
    worker_services: Any,
) -> None:
    sentinel = "stage22-real-secret-sentinel"
    with pytest.raises(JiejianError) as known:
        worker_services.queue.submit(
            worker_services.submit_request(idempotency_key=f"prefix-{sentinel}"),
            known_secrets=("", sentinel),
        )
    assert known.value.code == ErrorCode.JOB_SECRET.value
    assert sentinel not in str(known.value) + repr(known.value.to_dict())

    with pytest.raises(JiejianError) as inline:
        worker_services.queue.submit(
            worker_services.submit_request(
                idempotency_key="password=do-not-store",
            )
        )
    assert inline.value.code == ErrorCode.JOB_SECRET.value
    with worker_services.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM jobs")).scalar_one() == 0
    persisted = b"".join(
        candidate.read_bytes()
        for candidate in (
            worker_services.database_path,
            worker_services.database_path.with_name(
                worker_services.database_path.name + "-wal"
            ),
            worker_services.database_path.with_name(
                worker_services.database_path.name + "-shm"
            ),
        )
        if candidate.exists()
    )
    assert sentinel.encode() not in persisted
    assert b"do-not-store" not in persisted


def test_committed_state_and_events_survive_engine_restart(
    worker_services: Any,
) -> None:
    submitted = worker_services.queue.submit(worker_services.submit_request())
    claimed = worker_services.attempts.claim(_claim_request(submitted.job.job_id))
    assert claimed is not None
    worker_services.engine.dispose()
    restarted = create_sqlite_engine(worker_services.database_path)
    try:
        with StorageUnitOfWork(create_session_factory(restarted)) as work:
            job = work.jobs.get(submitted.job.job_id)
            run = work.runs.get(submitted.run.run_id)
            events = work.job_events.list_for_job(submitted.job.job_id)
            assert job is not None and job.state is JobState.RUNNING
            assert job.fencing_token == claimed.job.fencing_token
            assert run is not None and run.lifecycle is RunLifecycle.PREFLIGHT
            assert [event.sequence for event in events] == [1, 2]
    finally:
        restarted.dispose()
