# =============================================================================
# Execution 持久 Job 队列
#
# 定位
#   API/CLI 提交与 Worker claim 之间的持久生命周期入口
#
# 职责
#   幂等创建 Job｜请求取消｜协调 Job target、Run/Recording 与审计事件
#
# 调用链
#   Submission / API → JobQueueService → StorageUnitOfWork / JobTargetRegistry
# =============================================================================

from __future__ import annotations

from collections.abc import Callable, Sequence
from uuid import uuid4

from ..domain.lifecycle import JobState, RunLifecycle
from ..errors import ErrorCode, JiejianError
from ..storage import JobRecord, RunRecord, StorageUnitOfWork
from .events import append_job_event
from .models import (
    CancellationResultV1,
    JobEventType,
    JobSubmissionResultV1,
    RequestCancellationV1,
    SubmitJobV1,
    validate_control_request,
)
from .targets import JobTargetOutcome, JobTargetRegistry, default_run_job_targets

_TERMINAL_JOB_STATES = {
    JobState.SUCCEEDED,
    JobState.FAILED,
    JobState.CANCELLED,
}


class JobQueueService:
    """为未来 API/CLI 提供幂等提交和请求取消。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        *,
        targets: JobTargetRegistry | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._targets = targets or default_run_job_targets()

    def submit(
        self,
        request: SubmitJobV1,
        *,
        known_secrets: Sequence[str] = (),
    ) -> JobSubmissionResultV1:
        validate_control_request(request, known_secrets)
        run_id = request.run_id or f"run_{uuid4().hex}"
        job_id = request.job_id or f"job_{uuid4().hex}"
        try:
            with self._new_uow(known_secrets) as work:
                existing = work.jobs.get_by_idempotency(
                    request.project_id,
                    request.operation_type,
                    request.idempotency_key,
                )
                if existing is not None:
                    return self._existing_submission(work, existing, request)
                if work.projects.get(request.project_id) is None:
                    raise JiejianError(ErrorCode.JOB_PERSISTENCE, "任务所属项目不存在")
                run = RunRecord(
                    run_id=run_id,
                    project_id=request.project_id,
                    contract_id=request.contract_id,
                    contract_version=request.contract_version,
                    engine_version=request.engine_version,
                    lifecycle=RunLifecycle.QUEUED,
                    verdict=None,
                    created_at_us=request.now_us,
                    updated_at_us=request.now_us,
                    finished_at_us=None,
                )
                job = JobRecord(
                    job_id=job_id,
                    project_id=request.project_id,
                    run_id=run_id,
                    operation_type=request.operation_type,
                    state=JobState.PENDING,
                    idempotency_key=request.idempotency_key,
                    request_hash=request.request_hash,
                    attempt=0,
                    max_attempts=request.max_attempts,
                    available_at_us=request.available_at_us,
                    lease_owner=None,
                    fencing_token=0,
                    lease_expires_at_us=None,
                    cancel_requested_at_us=None,
                    created_at_us=request.now_us,
                    updated_at_us=request.now_us,
                )
                work.runs.add(run)
                work.jobs.add(job)
                append_job_event(
                    work,
                    job=job,
                    event_type=JobEventType.JOB_SUBMITTED,
                    source_state=None,
                    target_state=JobState.PENDING,
                    occurred_at_us=request.now_us,
                    metadata={"attempt": 0},
                )
                work.commit()
                return JobSubmissionResultV1(created=True, job=job, run=run)
        except JiejianError as exc:
            if exc.code != ErrorCode.STORAGE_CONSTRAINT.value:
                raise
        return self._resolve_submission_race(request, known_secrets)

    def request_cancellation(
        self,
        request: RequestCancellationV1,
        *,
        known_secrets: Sequence[str] = (),
    ) -> CancellationResultV1:
        validate_control_request(request, known_secrets)
        with self._new_uow(known_secrets) as work:
            initial = self._require_job(work, request.job_id)
            if initial.state in _TERMINAL_JOB_STATES:
                if (
                    initial.state is JobState.CANCELLED
                    and initial.cancel_requested_at_us is not None
                ):
                    run, recording = self._targets.load(work, initial)
                    return CancellationResultV1(
                        job=initial,
                        run=run,
                        recording=recording,
                        first_requested_at_us=initial.cancel_requested_at_us,
                        completed=True,
                    )
                raise JiejianError(ErrorCode.JOB_TERMINAL_CONFLICT, "终态任务不能取消")
            job, first_request = work.job_control.set_cancel_requested_at_if_absent(
                request.job_id,
                request.now_us,
            )
            if job is None:
                raise JiejianError(ErrorCode.JOB_CANCEL_CONFLICT, "任务取消请求冲突")
            if (
                job.state is JobState.CANCELLED
                and job.cancel_requested_at_us is not None
            ):
                run, recording = self._targets.load(work, job)
                return CancellationResultV1(
                    job=job,
                    run=run,
                    recording=recording,
                    first_requested_at_us=job.cancel_requested_at_us,
                    completed=True,
                )
            if first_request:
                append_job_event(
                    work,
                    job=job,
                    event_type=JobEventType.JOB_CANCEL_REQUESTED,
                    source_state=job.state,
                    target_state=job.state,
                    occurred_at_us=request.now_us,
                    metadata={"attempt": job.attempt},
                )
            if job.state in {JobState.PENDING, JobState.RETRY_WAIT}:
                return self._cancel_waiting(work, job, request.now_us)
            if job.state is not JobState.RUNNING:
                raise JiejianError(ErrorCode.JOB_CANCEL_CONFLICT, "任务取消请求冲突")
            run, recording = self._targets.load(work, job)
            work.commit()
            return CancellationResultV1(
                job=job,
                run=run,
                recording=recording,
                first_requested_at_us=job.cancel_requested_at_us,
                completed=False,
            )

    def _cancel_waiting(
        self,
        work: StorageUnitOfWork,
        job: JobRecord,
        now_us: int,
    ) -> CancellationResultV1:
        source_state = job.state
        cancelled = work.job_control.cancel_waiting(job.job_id, now_us)
        if cancelled is None:
            raise JiejianError(ErrorCode.JOB_CANCEL_CONFLICT, "任务取消请求冲突")
        run, recording = self._targets.finish(
            work,
            cancelled,
            now_us,
            JobTargetOutcome.CANCELLED,
        )
        append_job_event(
            work,
            job=cancelled,
            event_type=JobEventType.JOB_CANCELLED,
            source_state=source_state,
            target_state=JobState.CANCELLED,
            occurred_at_us=now_us,
            metadata={"attempt": cancelled.attempt},
        )
        work.commit()
        return CancellationResultV1(
            job=cancelled,
            run=run,
            recording=recording,
            first_requested_at_us=cancelled.cancel_requested_at_us,
            completed=True,
        )

    def _existing_submission(
        self,
        work: StorageUnitOfWork,
        job: JobRecord,
        request: SubmitJobV1,
    ) -> JobSubmissionResultV1:
        if job.request_hash != request.request_hash:
            raise JiejianError(
                ErrorCode.JOB_IDEMPOTENCY_CONFLICT,
                "幂等键对应的请求内容不一致",
            )
        return JobSubmissionResultV1(
            created=False,
            job=job,
            run=self._require_run(work, job.run_id),
        )

    def _resolve_submission_race(
        self,
        request: SubmitJobV1,
        known_secrets: Sequence[str],
    ) -> JobSubmissionResultV1:
        with self._new_uow(known_secrets) as work:
            existing = work.jobs.get_by_idempotency(
                request.project_id,
                request.operation_type,
                request.idempotency_key,
            )
            if existing is None:
                raise JiejianError(ErrorCode.JOB_PERSISTENCE, "任务提交失败")
            return self._existing_submission(work, existing, request)

    def _new_uow(self, known_secrets: Sequence[str]) -> StorageUnitOfWork:
        return self._uow_factory(
            known_secrets=tuple(secret for secret in known_secrets if secret)
        )

    def _require_job(self, work: StorageUnitOfWork, job_id: str) -> JobRecord:
        job = work.jobs.get(job_id)
        if job is None:
            raise JiejianError(ErrorCode.JOB_NOT_FOUND, "任务不存在")
        return job

    def _require_run(self, work: StorageUnitOfWork, run_id: str) -> RunRecord:
        run = work.runs.get(run_id)
        if run is None:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "任务关联运行不存在")
        return run
