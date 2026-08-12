# =============================================================================
# Recording Job target
#
# 定位
#   通用 Job 状态变化与 Recording 状态机之间的适配边界
#
# 职责
#   校验 Recording 目标｜映射领取/取消/失败/恢复结果｜保持两类状态语义分离
#
# 调用链
#   JobTargetRegistry / JobControlRepository → RecordingJobTargetHandler → Recording repository
# =============================================================================

from __future__ import annotations

from ..errors import ErrorCode, JiejianError
from ..execution.targets import (
    JobTargetHandler,
    JobTargetOutcome,
)
from ..recording.models import (
    RecordingReasonCode,
    RecordingState,
    RecordingTerminalState,
    transition_recording_state,
)
from ..storage import JobRecord, RecordingRecord, RunRecord, StorageUnitOfWork


class RecordingJobTargetHandler(JobTargetHandler):
    def load(
        self,
        work: StorageUnitOfWork,
        job: JobRecord,
    ) -> tuple[RunRecord | None, RecordingRecord | None]:
        if job.recording_id is None or job.run_id is not None:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "任务录制目标关联非法")
        recording = work.recordings.get(job.recording_id)
        if recording is None:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "任务关联录制不存在")
        return None, recording

    def advance_after_claim(
        self,
        work: StorageUnitOfWork,
        job: JobRecord,
        now_us: int,
    ) -> tuple[RunRecord | None, RecordingRecord | None]:
        _, recording = self.load(work, job)
        assert recording is not None
        if recording.state is RecordingState.CREATED:
            started = transition_recording_state(
                recording.to_domain(),
                RecordingState.STARTING,
                operator="WORKER",
                occurred_at_us=now_us,
            )
            recording = RecordingRecord.from_domain(
                started,
                flow_id=recording.flow_id,
                browser_events=recording.browser_events,
            )
            work.recordings.replace(recording)
        elif recording.state is not RecordingState.STARTING:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "录制状态无法进入启动")
        return None, recording

    def finish(
        self,
        work: StorageUnitOfWork,
        job: JobRecord,
        now_us: int,
        outcome: JobTargetOutcome,
    ) -> tuple[RunRecord | None, RecordingRecord | None]:
        _, recording = self.load(work, job)
        assert recording is not None
        recording_target = (
            RecordingTerminalState.CANCELLED
            if outcome is JobTargetOutcome.CANCELLED
            else RecordingTerminalState.FAILED
        )
        recording_reason = (
            RecordingReasonCode.CANCEL_REQUESTED
            if outcome is JobTargetOutcome.CANCELLED
            else RecordingReasonCode.PROCESSING_FAILED
        )
        domain = recording.to_domain()
        if (
            domain.state is RecordingState.CREATED
            and recording_target is RecordingTerminalState.CANCELLED
        ):
            domain = transition_recording_state(
                domain,
                RecordingState.CANCELLED,
                operator="WORKER",
                occurred_at_us=now_us,
                reason_code=recording_reason,
            )
        else:
            if domain.state is not RecordingState.CLEANING:
                domain = transition_recording_state(
                    domain,
                    RecordingState.CLEANING,
                    operator="WORKER",
                    occurred_at_us=now_us,
                    reason_code=recording_reason,
                    pending_terminal_state=recording_target,
                )
            domain = transition_recording_state(
                domain,
                RecordingState(recording_target.value),
                operator="WORKER",
                occurred_at_us=now_us,
                reason_code=recording_reason,
            )
        updated = RecordingRecord.from_domain(
            domain,
            flow_id=recording.flow_id,
            browser_events=recording.browser_events,
        )
        work.recordings.replace(updated)
        return None, updated
