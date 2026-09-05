# =============================================================================
# Execution attempt 与租约
#
# 定位
#   Handler 与 Storage 原子 Job 控制之间的应用服务
#
# 职责
#   claim 当前 attempt｜续租与 fencing 校验｜完成、重试、取消和恢复
#
# 边界
#   所有变更通过原子仓储执行；owner/token 不匹配时不得提交任何终态。
#
# 调用链
#   RunnerSupervisor / RecordingJobHandler → JobAttempts → Storage job_control
# =============================================================================

from __future__ import annotations

from collections.abc import Callable, Sequence
from secrets import randbelow

from product.backend.core.lifecycle import JobState
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage import JobRecord, StorageUnitOfWork
from product.backend.infra.runtime.jobs.events import EventMetadata, append_job_event
from product.backend.infra.runtime.jobs.models import CancellationResult, ClaimJob, ClaimedJob, CompleteCancellation, FatalFailure, JobEventType, JobMutationResult, RetryPolicy, RetryableFailure, RenewLease, WaitingFatalFailure, checked_time_add, compute_retry_available_at, validate_control_request
from product.backend.infra.runtime.jobs.targets import JobTargetOutcome, JobTargetRegistry, default_run_job_targets

_TERMINAL_JOB_STATES = {
    JobState.SUCCEEDED,
    JobState.FAILED,
    JobState.CANCELLED,
}


class JobAttempts:
    """领取、维持并结束一个当前 fenced 尝试。"""

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

    def claim(
        self,
        request: ClaimJob,
        *,
        known_secrets: Sequence[str] = (),
    ) -> ClaimedJob | None:
        """在单个事务中领取任务并返回新的 fencing token；竞争失败返回 ``None``。"""

        validate_control_request(request, known_secrets)
        lease_expires_at_us = checked_time_add(
            request.now_us,
            request.lease_duration_us,
        )
        with self._new_uow(known_secrets) as work:
            job = work.job_control.claim(
                job_id=request.job_id,
                lease_owner=request.lease_owner,
                now_us=request.now_us,
                lease_expires_at_us=lease_expires_at_us,
                target_types=self._targets.target_types,
            )
            if job is None:
                if request.job_id is None:
                    return None
                self._raise_claim_error(work, request.job_id, request.now_us)
            assert job is not None
            run, recording = self._targets.advance_after_claim(
                work,
                job,
                request.now_us,
            )
            append_job_event(
                work,
                job=job,
                event_type=JobEventType.JOB_CLAIMED,
                source_state=(
                    JobState.PENDING if job.attempt == 1 else JobState.RETRY_WAIT
                ),
                target_state=JobState.RUNNING,
                occurred_at_us=request.now_us,
                metadata={
                    "attempt": job.attempt,
                    "fencing_token": job.fencing_token,
                },
            )
            work.commit()
            return ClaimedJob(job=job, run=run, recording=recording)

    def renew_lease(
        self,
        request: RenewLease,
        *,
        known_secrets: Sequence[str] = (),
    ) -> JobMutationResult:
        """仅允许当前租约持有者续约，过期或失配的 fence 会作为并发冲突拒绝。"""

        validate_control_request(request, known_secrets)
        with self._new_uow(known_secrets) as work:
            job = work.job_control.renew_lease(
                job_id=request.job_id,
                lease_owner=request.lease_owner,
                fencing_token=request.fencing_token,
                now_us=request.now_us,
                lease_expires_at_us=request.lease_expires_at_us,
            )
            if job is None:
                self._raise_fenced_error(
                    work,
                    request.job_id,
                    request.lease_owner,
                    request.fencing_token,
                    request.now_us,
                    expired_code=ErrorCode.JOB_LEASE_EXPIRED,
                )
            assert job is not None
            run, recording = self._targets.load(work, job)
            append_job_event(
                work,
                job=job,
                event_type=JobEventType.JOB_LEASE_RENEWED,
                source_state=JobState.RUNNING,
                target_state=JobState.RUNNING,
                occurred_at_us=request.now_us,
                metadata={
                    "attempt": job.attempt,
                    "fencing_token": job.fencing_token,
                },
            )
            work.commit()
            return JobMutationResult(job=job, run=run, recording=recording)

    def complete_cancellation(
        self,
        request: CompleteCancellation,
        *,
        known_secrets: Sequence[str] = (),
    ) -> CancellationResult:
        """确认运行中任务的取消，并同步其 Run 或 Recording 生命周期。"""

        validate_control_request(request, known_secrets)
        with self._new_uow(known_secrets) as work:
            current = self._require_current_fence(work, request)
            if current.cancel_requested_at_us is None:
                raise JiejianError(ErrorCode.JOB_CANCEL_CONFLICT, "任务尚未请求取消")
            job = work.job_control.complete_running_cancellation(
                job_id=request.job_id,
                lease_owner=request.lease_owner,
                fencing_token=request.fencing_token,
                now_us=request.now_us,
            )
            if job is None:
                self._raise_fenced_error(
                    work,
                    request.job_id,
                    request.lease_owner,
                    request.fencing_token,
                    request.now_us,
                    expired_code=ErrorCode.JOB_RECOVERY_REQUIRED,
                )
            assert job is not None
            run, recording = self._targets.finish(
                work,
                job,
                request.now_us,
                JobTargetOutcome.CANCELLED,
            )
            append_job_event(
                work,
                job=job,
                event_type=JobEventType.JOB_CANCELLED,
                source_state=JobState.RUNNING,
                target_state=JobState.CANCELLED,
                occurred_at_us=request.now_us,
                metadata={
                    "attempt": job.attempt,
                    "fencing_token": request.fencing_token,
                },
            )
            work.commit()
            return CancellationResult(
                job=job,
                run=run,
                recording=recording,
                first_requested_at_us=job.cancel_requested_at_us,
                completed=True,
            )

    def record_retryable_failure(
        self,
        request: RetryableFailure,
        *,
        known_secrets: Sequence[str] = (),
    ) -> JobMutationResult:
        """记录可重试失败；达到次数上限后转为不可恢复失败。"""

        validate_control_request(request, known_secrets)
        with self._new_uow(known_secrets) as work:
            current = self._require_current_fence(work, request)
            if current.cancel_requested_at_us is not None:
                raise JiejianError(
                    ErrorCode.JOB_CANCEL_CONFLICT,
                    "取消中的任务不能进入重试等待",
                )
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
            return self._persist_failure(
                work,
                request=request,
                target=target,
                available_at_us=available_at_us,
            )

    def record_fatal_failure(
        self,
        request: FatalFailure,
        *,
        known_secrets: Sequence[str] = (),
    ) -> JobMutationResult:
        """记录不可重试失败；调用者仍必须持有当前 fence。"""

        validate_control_request(request, known_secrets)
        with self._new_uow(known_secrets) as work:
            self._require_current_fence(work, request)
            return self._persist_failure(
                work,
                request=request,
                target=JobState.FAILED,
                available_at_us=None,
            )

    def record_waiting_fatal_failure(
        self,
        request: WaitingFatalFailure,
        *,
        known_secrets: Sequence[str] = (),
    ) -> JobMutationResult | None:
        """原子结束尚未 claim 的等待态 Job；竞争失配时返回 ``None``。"""

        validate_control_request(request, known_secrets)
        with self._new_uow(known_secrets) as work:
            current = work.jobs.get(request.job_id)
            job = work.job_control.record_waiting_failure(
                job_id=request.job_id,
                now_us=request.now_us,
            )
            if job is None:
                return None
            # 条件 SQL 已经冻结 waiting + unleased；这里的预读只用于保留真实事件源状态。
            if current is None or current.state not in {
                JobState.PENDING,
                JobState.RETRY_WAIT,
            }:
                raise JiejianError(ErrorCode.STORAGE_STATE, "等待态失败源状态无效")
            run, recording = self._targets.finish(
                work,
                job,
                request.now_us,
                JobTargetOutcome.FAILED,
            )
            append_job_event(
                work,
                job=job,
                event_type=JobEventType.JOB_FAILED,
                source_state=current.state,
                target_state=JobState.FAILED,
                occurred_at_us=request.now_us,
                metadata={
                    "attempt": job.attempt,
                    "reason_code": request.reason_code.value,
                },
            )
            work.commit()
            return JobMutationResult(job=job, run=run, recording=recording)

    def _persist_failure(
        self,
        work: StorageUnitOfWork,
        *,
        request: RetryableFailure | FatalFailure,
        target: JobState,
        available_at_us: int | None,
    ) -> JobMutationResult:
        job = work.job_control.record_running_failure(
            job_id=request.job_id,
            lease_owner=request.lease_owner,
            fencing_token=request.fencing_token,
            now_us=request.now_us,
            target_state=target,
            available_at_us=available_at_us,
        )
        if job is None:
            self._raise_fenced_error(
                work,
                request.job_id,
                request.lease_owner,
                request.fencing_token,
                request.now_us,
                expired_code=ErrorCode.JOB_RECOVERY_REQUIRED,
            )
        assert job is not None
        if target is JobState.FAILED:
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
            event_type=(
                JobEventType.JOB_FAILED
                if target is JobState.FAILED
                else JobEventType.JOB_RETRY_SCHEDULED
            ),
            source_state=JobState.RUNNING,
            target_state=target,
            occurred_at_us=request.now_us,
            metadata=self._failure_metadata(
                job,
                request,
                available_at_us,
            ),
        )
        work.commit()
        return JobMutationResult(job=job, run=run, recording=recording)

    def _require_current_fence(
        self,
        work: StorageUnitOfWork,
        request: CompleteCancellation | RetryableFailure | FatalFailure,
    ) -> JobRecord:
        job = self._require_job(work, request.job_id)
        if job.state is not JobState.RUNNING:
            if job.state in _TERMINAL_JOB_STATES:
                raise JiejianError(
                    ErrorCode.JOB_TERMINAL_CONFLICT,
                    "终态任务不能修改",
                )
            raise JiejianError(ErrorCode.JOB_LEASE_MISMATCH, "任务租约不匹配")
        if (
            job.lease_owner != request.lease_owner
            or job.fencing_token != request.fencing_token
        ):
            raise JiejianError(ErrorCode.JOB_LEASE_MISMATCH, "任务租约不匹配")
        if job.lease_expires_at_us is None or job.lease_expires_at_us <= request.now_us:
            raise JiejianError(
                ErrorCode.JOB_RECOVERY_REQUIRED,
                "过期租约需要恢复审计",
            )
        return job

    def _raise_claim_error(
        self,
        work: StorageUnitOfWork,
        job_id: str,
        now_us: int,
    ) -> None:
        job = self._require_job(work, job_id)
        if job.state in _TERMINAL_JOB_STATES:
            raise JiejianError(ErrorCode.JOB_TERMINAL_CONFLICT, "终态任务不能领取")
        if job.state is JobState.RUNNING:
            if job.lease_expires_at_us is not None and job.lease_expires_at_us <= now_us:
                raise JiejianError(
                    ErrorCode.JOB_RECOVERY_REQUIRED,
                    "过期租约需要恢复审计",
                )
            raise JiejianError(ErrorCode.JOB_NOT_CLAIMABLE, "任务当前不可领取")
        if job.cancel_requested_at_us is not None:
            raise JiejianError(ErrorCode.JOB_CANCEL_CONFLICT, "任务已经请求取消")
        if job.attempt >= job.max_attempts:
            raise JiejianError(
                ErrorCode.JOB_ATTEMPTS_EXHAUSTED,
                "任务尝试次数已经耗尽",
            )
        raise JiejianError(ErrorCode.JOB_NOT_CLAIMABLE, "任务当前不可领取")

    def _raise_fenced_error(
        self,
        work: StorageUnitOfWork,
        job_id: str,
        lease_owner: str,
        fencing_token: int,
        now_us: int,
        *,
        expired_code: ErrorCode,
    ) -> None:
        job = self._require_job(work, job_id)
        if job.state in _TERMINAL_JOB_STATES:
            raise JiejianError(ErrorCode.JOB_TERMINAL_CONFLICT, "终态任务不能修改")
        if job.state is not JobState.RUNNING:
            raise JiejianError(ErrorCode.JOB_LEASE_MISMATCH, "任务租约不匹配")
        if job.lease_owner != lease_owner or job.fencing_token != fencing_token:
            raise JiejianError(ErrorCode.JOB_LEASE_MISMATCH, "任务租约不匹配")
        if job.lease_expires_at_us is None or job.lease_expires_at_us <= now_us:
            raise JiejianError(expired_code, "任务租约已经过期")
        raise JiejianError(ErrorCode.JOB_NOT_CLAIMABLE, "任务更新条件不满足")

    def _failure_metadata(
        self,
        job: JobRecord,
        request: RetryableFailure | FatalFailure,
        available_at_us: int | None,
    ) -> EventMetadata:
        metadata: EventMetadata = {
            "attempt": job.attempt,
            "fencing_token": request.fencing_token,
            "reason_code": request.reason_code.value,
        }
        if request.error_code is not None:
            metadata["error_code"] = request.error_code
        if request.phase is not None:
            metadata["phase"] = request.phase.value
        if request.cause_code is not None:
            metadata["cause_code"] = request.cause_code
        if request.cleanup_issue_codes:
            metadata["cleanup_issue_codes"] = ",".join(
                item.value for item in request.cleanup_issue_codes
            )
        if available_at_us is not None:
            metadata["available_at_us"] = available_at_us
        return metadata

    def _new_uow(self, known_secrets: Sequence[str]) -> StorageUnitOfWork:
        return self._uow_factory(
            known_secrets=tuple(secret for secret in known_secrets if secret)
        )

    def _require_job(self, work: StorageUnitOfWork, job_id: str) -> JobRecord:
        job = work.jobs.get(job_id)
        if job is None:
            raise JiejianError(ErrorCode.JOB_NOT_FOUND, "任务不存在")
        return job
