# =============================================================================
# Execution 过期 lease 恢复
#
# 定位
#   Worker 循环在领取新任务前收敛失联 attempt 的审计服务
#
# 职责
#   有界扫描过期租约｜依据恢复证明分类｜转入 retry、cancel 或 fatal 状态
#
# 边界
#   没有持久证明时不得宣告成功；恢复只处理已确认过期的当前 attempt。
#
# 调用链
#   Worker runtime → JobRecovery → JobAttempts / Storage job_control
# =============================================================================

from __future__ import annotations

from collections.abc import Callable, Sequence
from secrets import randbelow

from product.backend.core.lifecycle import JobState
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage import JobRecord, StorageUnitOfWork
from product.backend.infra.runtime.jobs.events import EventMetadata, append_job_event
from product.backend.infra.runtime.jobs.models import ConfirmRecovery, JobEventType, JobMutationResult, RecoveryCandidate, RecoveryScan, RetryPolicy, compute_retry_available_at, validate_control_request
from product.backend.infra.runtime.jobs.targets import JobTargetOutcome, JobTargetRegistry, default_run_job_targets

_TERMINAL_JOB_STATES = {
    JobState.SUCCEEDED,
    JobState.FAILED,
    JobState.CANCELLED,
}


class JobRecovery:
    """只读列出恢复候选，并在受限证明后解除过期 RUNNING。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        *,
        retry_policy: RetryPolicy | None = None,
        jitter_source: Callable[[int], int] = randbelow,
        targets: JobTargetRegistry | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._retry_policy = retry_policy or RetryPolicy()
        self._jitter_source = jitter_source
        self._targets = targets or default_run_job_targets()

    def list_recovery_candidates(
        self,
        request: RecoveryScan,
        *,
        known_secrets: Sequence[str] = (),
    ) -> tuple[RecoveryCandidate, ...]:
        """只枚举租约已经过期的运行中任务，不在扫描阶段改变任何状态。"""

        validate_control_request(request, known_secrets)
        with self._new_uow(known_secrets) as work:
            jobs = work.job_control.list_expired_running(
                request.now_us, request.limit, target_types=self._targets.target_types,
            )
            return tuple(
                RecoveryCandidate(
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
        request: ConfirmRecovery,
        *,
        known_secrets: Sequence[str] = (),
    ) -> JobMutationResult:
        """在再次核对原 fence 后确认恢复，防止复活已被其他 Worker 接管的任务。"""

        validate_control_request(request, known_secrets)
        with self._new_uow(known_secrets) as work:
            current = self._require_recovery_fence(work, request)
            self._targets.resolve(current)
            # 恢复动作沿用正常重试预算，不能借崩溃恢复绕过最大尝试次数。
            cancelled = current.cancel_requested_at_us is not None
            exhausted = current.attempt >= current.max_attempts
            target = (
                JobState.CANCELLED
                if cancelled
                else JobState.FAILED
                if exhausted
                else JobState.RETRY_WAIT
            )
            available_at_us = (
                None
                if exhausted or cancelled
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
            if cancelled:
                run, recording = self._targets.finish(
                    work,
                    job,
                    request.now_us,
                    JobTargetOutcome.CANCELLED,
                )
            elif exhausted:
                run, recording = self._targets.finish(
                    work,
                    job,
                    request.now_us,
                    JobTargetOutcome.FAILED,
                )
            else:
                run, recording = self._targets.load(work, job)
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
            return JobMutationResult(
                job=job,
                run=run,
                recording=recording,
            )

    def _require_recovery_fence(
        self,
        work: StorageUnitOfWork,
        request: ConfirmRecovery,
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
        request: ConfirmRecovery,
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
