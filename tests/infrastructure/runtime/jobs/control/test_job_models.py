# 验证作业运行时中的作业模型。

from __future__ import annotations

from tests.support.builders.runtime.current_jobs import current_job, invalid_job_payload
from tests.support.contracts import JOB_TARGET_FIELDS, WORKER_CAPABILITIES
from product.backend.infrastructure.storage.execution.jobs import JobRecord
import pytest
from pydantic import ValidationError

from product.backend.infrastructure.runtime.jobs.models import ClaimJob, ConfirmRecovery, RecoveryOperator, RecoveryProofType, RecoveryReasonCode, RetryPolicy, SubmitJob


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
        "operation_type": "CHECK",
        "idempotency_key": "request-1",
        "request_hash": "a" * 64,
        "plan_fingerprint": "b" * 64,
        "source_fingerprint": "c" * 64,
        "policy_epoch": 1,
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

pytestmark = [pytest.mark.level2]


def test_job_fixture_contract_contains_every_target():
    assert JOB_TARGET_FIELDS <= set(JobRecord.model_fields)


def test_current_worker_registry_is_explicit():
    from product.backend.infrastructure.runtime.jobs.registration import current_check_and_recording_targets
    targets = current_check_and_recording_targets().target_types
    assert tuple(sorted('CHECK' if item.value == 'RUN' else item.value for item in targets)) == WORKER_CAPABILITIES


@pytest.mark.parametrize("target,operation", [("run_id", "CHECK"), ("recording_id", "RECORDING"),
                                           ("runtime_load_id", "RUNTIME_LOAD"), ("preflight_id", "PROOF_PREFLIGHT"), ("reference_capture_id", "REFERENCE_CAPTURE"), ("identity_preparation_id", "IDENTITY_PREPARATION")])
def test_current_jobs_are_valid_and_carry_all_target_fields(target, operation):
    job = current_job(target=target, operation_type=operation)
    assert all(hasattr(job, name) for name in JOB_TARGET_FIELDS)
    assert sum(getattr(job, name) is not None for name in JOB_TARGET_FIELDS) == 1


def test_invalid_wire_is_rejected_instead_of_bypassing_validation():
    with pytest.raises(ValidationError):
        JobRecord.model_validate(invalid_job_payload(run_id=None))
    with pytest.raises(ValidationError):
        current_job(target="preflight_id", operation_type="CHECK")
