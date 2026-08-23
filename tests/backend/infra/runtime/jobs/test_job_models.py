from __future__ import annotations

import pytest
from pydantic import ValidationError

from product.backend.infra.runtime.jobs.models import (
    ClaimJob,
    ConfirmRecovery,
    RecoveryOperator,
    RecoveryProofType,
    RecoveryReasonCode,
    RetryPolicy,
    SubmitJob,
)


def test_worker_dtos_are_strict_and_frozen_without_root_document_version() -> None:
    request = ClaimJob(
        lease_owner="worker-1",
        now_us=100,
        lease_duration_us=10,
    )
    assert "schema_version" not in request.model_dump(mode="python")
    with pytest.raises(ValidationError):
        ClaimJob(
            lease_owner="worker-1",
            now_us=100,
            lease_duration_us=10,
            unknown=True,
        )
    with pytest.raises(ValidationError):
        ClaimJob(
            lease_owner="worker-1",
            now_us="100",
            lease_duration_us=10,
        )
    with pytest.raises(ValidationError):
        request.now_us = 101


def test_submit_ids_are_optional_but_strict_when_supplied() -> None:
    values = {
        "project_id": "job-runtime-project",
        "operation_type": "ACTIVE_RUN",
        "idempotency_key": "request-1",
        "request_hash": "a" * 64,
        "contract_id": "contract",
        "contract_version": 1,
        "engine_version": "0.1.0",
        "max_attempts": 3,
        "available_at_us": 100,
        "now_us": 100,
    }
    assert SubmitJob(**values).run_id is None
    with pytest.raises(ValidationError):
        SubmitJob(**values, run_id="run_NOT_HEX")


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
def test_recovery_proof_pairs_are_explicit(
    proof_type: RecoveryProofType,
    reason_code: RecoveryReasonCode,
) -> None:
    request = ConfirmRecovery(
        job_id="job_" + "1" * 32,
        lease_owner="worker-1",
        fencing_token=1,
        now_us=100,
        proof_type=proof_type,
        operator=RecoveryOperator.RECOVERY_CONTROLLER,
        reason_code=reason_code,
    )
    assert request.reason_code is reason_code


def test_recovery_proof_rejects_mismatched_reason() -> None:
    with pytest.raises(ValidationError):
        ConfirmRecovery(
            job_id="job_" + "1" * 32,
            lease_owner="worker-1",
            fencing_token=1,
            now_us=100,
            proof_type=RecoveryProofType.EXECUTION_EXITED,
            operator=RecoveryOperator.WORKER_SUPERVISOR,
            reason_code=RecoveryReasonCode.CLEANUP_CONFIRMED,
        )


def test_retry_policy_rejects_inverted_or_unbounded_values() -> None:
    with pytest.raises(ValidationError):
        RetryPolicy(base_delay_us=11, max_delay_us=10, max_jitter_us=0)
    with pytest.raises(ValidationError):
        RetryPolicy(base_delay_us=1, max_delay_us=10, max_jitter_us=11)
