"""监督层使用的过期租约恢复审计服务。"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from secrets import randbelow

from ..domain.lifecycle import JobState, RunLifecycle
from ..domain.recording import RecordingReasonCode, RecordingTerminalState
from ..errors import ErrorCode, JiejianError
from ..storage import JobRecord, StorageUnitOfWork
from .events import EventMetadata, append_job_event
from .models import (
    ConfirmRecoveryV1,
    JobEventType,
    JobMutationResultV1,
    RecoveryCandidateV1,
    RecoveryScanV1,
    RetryPolicyV1,
    compute_retry_available_at,
    validate_control_request,
)
from .targets import finish_job_target, load_job_target

_TERMINAL_JOB_STATES = {
    JobState.SUCCEEDED,
    JobState.FAILED,
    JobState.CANCELLED,
}


class JobRecoveryService:
    """只读列出恢复候选，并在受限证明后解除过期 RUNNING。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        *,
        retry_policy: RetryPolicyV1 | None = None,
        jitter_source: Callable[[int], int] = randbelow,
    ) -> None:
        self._uow_factory = uow_factory
        self._retry_policy = retry_policy or RetryPolicyV1()
        self._jitter_source = jitter_source

    def list_recovery_candidates(
        self,
        request: RecoveryScanV1,
        *,
        known_secrets: Sequence[str] = (),
    ) -> tuple[RecoveryCandidateV1, ...]:
        validate_control_request(request, known_secrets)
        with self._new_uow(known_secrets) as work:
            jobs = work.job_control.list_expired_running(request.now_us, request.limit)
            return tuple(
                RecoveryCandidateV1(
                    job_id=job.job_id,
                    run_id=job.run_id,
                    recording_id=job.recording_id,
                    attempt=job.attempt,
                    max_attempts=job.max_attempts,
                    lease_owner=job.lease_owner,
                    fencing_token=job.fencing_token,
                    lease_expires_at_us=job.lease_expires_at_us,
                )
                for job in jobs
                if job.lease_owner is not None and job.lease_expires_at_us is not None
            )

    def confirm_recovery(
        self,
        request: ConfirmRecoveryV1,
        *,
        known_secrets: Sequence[str] = (),
    ) -> JobMutationResultV1:
        validate_control_request(request, known_secrets)
        with self._new_uow(known_secrets) as work:
            current = self._require_recovery_fence(work, request)
            exhausted = current.attempt >= current.max_attempts
            target = JobState.FAILED if exhausted else JobState.RETRY_WAIT
            available_at_us = (
                None
                if exhausted
                else compute_retry_available_at(
                    policy=self._retry_policy,
                    jitter_source=self._jitter_source,
                    now_us=request.now_us,
                    attempt=current.attempt,
                )
            )
            job = work.job_control.confirm_recovery(
                job_id=request.job_id,
                lease_owner=request.lease_owner,
                fencing_token=request.fencing_token,
                now_us=request.now_us,
                target_state=target,
                available_at_us=available_at_us,
            )
            if job is None:
                raise JiejianError(ErrorCode.JOB_LEASE_MISMATCH, "任务租约不匹配")
            if exhausted:
                run, recording = finish_job_target(
                    work,
                    job,
                    request.now_us,
                    run_target=RunLifecycle.FAILED,
                    recording_target=RecordingTerminalState.FAILED,
                    recording_reason=RecordingReasonCode.PROCESSING_FAILED,
                )
            else:
                run, recording = load_job_target(work, job)
            append_job_event(
                work,
                job=job,
                event_type=JobEventType.JOB_RECOVERY_CONFIRMED,
                source_state=JobState.RUNNING,
                target_state=target,
                occurred_at_us=request.now_us,
                metadata=self._recovery_metadata(
                    job,
                    request,
                    available_at_us,
                ),
            )
            work.commit()
            return JobMutationResultV1(
                job=job,
                run=run,
                recording=recording,
            )

    def _require_recovery_fence(
        self,
        work: StorageUnitOfWork,
        request: ConfirmRecoveryV1,
    ) -> JobRecord:
        current = work.jobs.get(request.job_id)
        if current is None:
            raise JiejianError(ErrorCode.JOB_NOT_FOUND, "任务不存在")
        if current.state is not JobState.RUNNING:
            if current.state in _TERMINAL_JOB_STATES:
                raise JiejianError(
                    ErrorCode.JOB_TERMINAL_CONFLICT,
                    "终态任务不能修改",
                )
            raise JiejianError(ErrorCode.JOB_LEASE_MISMATCH, "任务租约不匹配")
        if (
            current.lease_owner != request.lease_owner
            or current.fencing_token != request.fencing_token
        ):
            raise JiejianError(ErrorCode.JOB_LEASE_MISMATCH, "任务租约不匹配")
        if current.lease_expires_at_us is None or (
            current.lease_expires_at_us > request.now_us
        ):
            raise JiejianError(
                ErrorCode.JOB_RECOVERY_REQUIRED,
                "任务尚不满足恢复审计条件",
            )
        return current

    def _recovery_metadata(
        self,
        job: JobRecord,
        request: ConfirmRecoveryV1,
        available_at_us: int | None,
    ) -> EventMetadata:
        metadata: EventMetadata = {
            "attempt": job.attempt,
            "fencing_token": request.fencing_token,
            "operator": request.operator.value,
            "proof_type": request.proof_type.value,
            "reason_code": request.reason_code.value,
        }
        if available_at_us is not None:
            metadata["available_at_us"] = available_at_us
        return metadata

    def _new_uow(self, known_secrets: Sequence[str]) -> StorageUnitOfWork:
        return self._uow_factory(
            known_secrets=tuple(secret for secret in known_secrets if secret)
        )
