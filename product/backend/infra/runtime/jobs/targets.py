# =============================================================================
# Execution Job target 端口
#
# 定位
#   通用 Job 生命周期与 Run/Recording 持久目标之间的适配边界
#
# 职责
#   定义目标类型和完成结果｜注册目标处理器｜提供 Verification Run 默认实现
#
# 边界
#   通用队列不猜测目标状态机；每种 target 只能由已注册处理器解释。
#
# 调用链
#   ApplicationCore / JobQueue → JobTargetRegistry → Run or Recording target handler
# =============================================================================

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from product.backend.core.lifecycle import RunLifecycle
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage import JobRecord, RecordingRecord, RunRecord, StorageUnitOfWork


class JobTargetType(StrEnum):
    RUN = "RUN"
    RECORDING = "RECORDING"

    @classmethod
    def from_job(cls, job: JobRecord) -> JobTargetType:
        if job.run_id is not None and job.recording_id is None:
            return cls.RUN
        if job.recording_id is not None and job.run_id is None:
            return cls.RECORDING
        raise JiejianError(ErrorCode.JOB_PERSISTENCE, "任务关联目标非法")


class JobTargetOutcome(StrEnum):
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class JobTargetHandler(Protocol):
    def load(
        self,
        work: StorageUnitOfWork,
        job: JobRecord,
    ) -> tuple[RunRecord | None, RecordingRecord | None]:
        ...

    def advance_after_claim(
        self,
        work: StorageUnitOfWork,
        job: JobRecord,
        now_us: int,
    ) -> tuple[RunRecord | None, RecordingRecord | None]:
        ...

    def finish(
        self,
        work: StorageUnitOfWork,
        job: JobRecord,
        now_us: int,
        outcome: JobTargetOutcome,
    ) -> tuple[RunRecord | None, RecordingRecord | None]:
        ...


class JobTargetRegistry:
    """严格注册并委托 Job 目标生命周期适配器。"""

    def __init__(self) -> None:
        self._handlers: dict[JobTargetType, JobTargetHandler] = {}

    def register(
        self,
        target_type: JobTargetType,
        handler: JobTargetHandler,
    ) -> None:
        if not isinstance(target_type, JobTargetType):
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "任务目标类型非法")
        if target_type in self._handlers:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "任务目标处理器重复注册")
        self._handlers[target_type] = handler

    def resolve(self, job: JobRecord) -> JobTargetHandler:
        target_type = JobTargetType.from_job(job)
        try:
            return self._handlers[target_type]
        except KeyError:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "任务目标处理器未注册") from None

    def load(
        self,
        work: StorageUnitOfWork,
        job: JobRecord,
    ) -> tuple[RunRecord | None, RecordingRecord | None]:
        return self.resolve(job).load(work, job)

    def advance_after_claim(
        self,
        work: StorageUnitOfWork,
        job: JobRecord,
        now_us: int,
    ) -> tuple[RunRecord | None, RecordingRecord | None]:
        return self.resolve(job).advance_after_claim(work, job, now_us)

    def finish(
        self,
        work: StorageUnitOfWork,
        job: JobRecord,
        now_us: int,
        outcome: JobTargetOutcome,
    ) -> tuple[RunRecord | None, RecordingRecord | None]:
        return self.resolve(job).finish(work, job, now_us, outcome)


class RunJobTargetHandler:
    def load(
        self,
        work: StorageUnitOfWork,
        job: JobRecord,
    ) -> tuple[RunRecord | None, RecordingRecord | None]:
        if job.run_id is None or job.recording_id is not None:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "任务运行目标关联非法")
        run = work.runs.get(job.run_id)
        if run is None:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "任务关联运行不存在")
        return run, None

    def advance_after_claim(
        self,
        work: StorageUnitOfWork,
        job: JobRecord,
        now_us: int,
    ) -> tuple[RunRecord | None, RecordingRecord | None]:
        if job.run_id is None or job.recording_id is not None:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "任务运行目标关联非法")
        run = work.job_control.advance_run_after_claim(job.run_id, now_us)
        if run is None:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "运行状态无法进入预检")
        return run, None

    def finish(
        self,
        work: StorageUnitOfWork,
        job: JobRecord,
        now_us: int,
        outcome: JobTargetOutcome,
    ) -> tuple[RunRecord | None, RecordingRecord | None]:
        if job.run_id is None or job.recording_id is not None:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "任务运行目标关联非法")
        target = (
            RunLifecycle.CANCELLED
            if outcome is JobTargetOutcome.CANCELLED
            else RunLifecycle.FAILED
        )
        run = work.job_control.transition_run_terminal(job.run_id, target, now_us)
        if run is None:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "运行终态写入失败")
        return run, None


def default_run_job_targets() -> JobTargetRegistry:
    registry = JobTargetRegistry()
    registry.register(JobTargetType.RUN, RunJobTargetHandler())
    return registry
