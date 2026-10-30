# Execution Job target 端口
# 定义目标契约、核对冻结输入、处理持久状态；录制的完整执行流程由独立模块拥有
# 通用队列不猜测目标状态机；每种 target 只能由已注册处理器解释。

from __future__ import annotations

from product.protocols.preparation.proof_sources import proof_fingerprint
from product.protocols.runtime.node_runtime import node_document_fingerprint
from enum import StrEnum
from typing import Protocol

from product.backend.domain.lifecycle import RunLifecycle
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.infrastructure.storage import JobRecord, RecordingRecord, RunRecord, StorageUnitOfWork


class JobTargetType(StrEnum):
    RUN = "RUN"
    RECORDING = "RECORDING"
    RUNTIME_LOAD = "RUNTIME_LOAD"
    PROOF_PREFLIGHT = "PROOF_PREFLIGHT"
    REFERENCE_CAPTURE='REFERENCE_CAPTURE'
    IDENTITY_PREPARATION = 'IDENTITY_PREPARATION'

    @classmethod
    def from_job(cls, job: JobRecord) -> JobTargetType:
        if job.identity_preparation_id is not None:return cls.IDENTITY_PREPARATION
        if job.reference_capture_id is not None:return cls.REFERENCE_CAPTURE
        if job.preflight_id is not None:
            return cls.PROOF_PREFLIGHT
        if job.runtime_load_id is not None and job.run_id is None and job.recording_id is None:
            return cls.RUNTIME_LOAD
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

    @property
    def target_types(self) -> tuple[JobTargetType, ...]:
        """返回实际登记的能力，供领取前的数据库过滤使用。"""
        return tuple(sorted(self._handlers, key=lambda item: item.value))

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






class CheckJobTargetHandler(RunJobTargetHandler):
    """当前检查只以 v3 请求 hash 关联 Run；旧 RUN operation 不进入当前调度。"""

    def load(self, work, job):
        run, recording = super().load(work, job)
        if job.operation_type != "CHECK" or run.project_id != job.project_id or run.request_hash != job.request_hash:
            raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "任务执行请求与既有快照不一致")
        return run, recording

    def advance_after_claim(self, work, job, now_us):
        self.load(work, job)
        return super().advance_after_claim(work, job, now_us)

    def finish(self, work, job, now_us, outcome):
        self.load(work, job)
        return super().finish(work, job, now_us, outcome)


class ProofPreflightTargetHandler:
    def load(self, work, job):
        request = None if job.preflight_id is None else work.proof_sources.preflight(job.project_id, job.preflight_id)
        if (request is None or job.operation_type != "PROOF_PREFLIGHT"
                or proof_fingerprint(request) != job.request_hash):
            raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "预检查Job与冻结输入不一致")
        return None, None

    def advance_after_claim(self, work, job, now_us):
        return self.load(work, job)

    def finish(self, work, job, now_us, outcome):
        return self.load(work, job)


class ReferenceCaptureTargetHandler:
    def load(self,work,job):
        request=None if job.reference_capture_id is None else work.proof_artifacts.capture(job.project_id,job.reference_capture_id)
        if request is None or job.operation_type!='REFERENCE_CAPTURE' or job.max_attempts!=1 or proof_fingerprint(request)!=job.request_hash:
            raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT,'取样任务与冻结输入不一致')
        return None,None

    def advance_after_claim(self,work,job,now_us):
        self.load(work,job)
        request=work.proof_artifacts.capture(job.project_id,job.reference_capture_id)
        if not work.proof_artifacts.authorized(request):raise JiejianError(ErrorCode.STATE_PRECONDITION,'取样授权已撤销')
        return None,None

    def finish(self,work,job,now_us,outcome):
        self.load(work,job)
        request=work.proof_artifacts.capture(job.project_id,job.reference_capture_id)
        value=None if request.asset_id is None else work.proof_artifacts.input(job.project_id,request.asset_id)
        if value is not None and value.state=='PENDING':
            state='CANCELLED' if outcome.value=='CANCELLED' else 'INCOMPLETE'
            work.proof_artifacts.update_input(value.model_copy(update={'state':state}),expected_state='PENDING')
        if job.attempt==0 or request.plan.restore is not None:
            work.proof_artifacts.resolve_recovery(job.project_id,request.capture_id,None,now_us)
        return None,None


class RuntimeLoadTargetHandler:
    def load(self, work, job):
        request = None if job.runtime_load_id is None else work.runtime_loads.get(job.runtime_load_id)
        if (request is None or job.run_id is not None or job.recording_id is not None
                or job.operation_type != "RUNTIME_LOAD" or request.project_id != job.project_id
                or node_document_fingerprint(request) != job.request_hash):
            raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "运行加载Job与冻结输入不一致")
        # 输入与回执由runtime_loads持久保存；Run/Recording字段保持为空。
        return None, None

    def advance_after_claim(self, work, job, now_us):
        return self.load(work, job)

    def finish(self, work, job, now_us, outcome):
        return self.load(work, job)


class IdentityPreparationTargetHandler:
    def load(self, work, job):
        row = work.identity_preparations.get(job.identity_preparation_id)
        if row is None or row['project_id'] != job.project_id or row['request_fingerprint'] != job.request_hash:
            raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, '登录任务与冻结输入不一致')
        return None, None

    def advance_after_claim(self, work, job, now_us):
        return self.load(work, job)

    def finish(self, work, job, now_us, outcome):
        self.load(work, job)
        work.identity_preparations.update(job.identity_preparation_id,
            phase='CANCELLED' if outcome is JobTargetOutcome.CANCELLED else 'FAILED', now_us=now_us)
        return None, None
