"""让既有 Job 控制面在同一事务中操作 Run 或 Recording 目标。"""

from __future__ import annotations

from ..domain.lifecycle import RunLifecycle
from ..domain.recording import (
    RecordingReasonCode,
    RecordingState,
    RecordingTerminalState,
    transition_recording_state,
)
from ..errors import ErrorCode, JiejianError
from ..storage import JobRecord, RecordingRecord, RunRecord, StorageUnitOfWork


def load_job_target(
    work: StorageUnitOfWork,
    job: JobRecord,
) -> tuple[RunRecord | None, RecordingRecord | None]:
    if job.run_id is not None:
        run = work.runs.get(job.run_id)
        if run is None:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "任务关联运行不存在")
        return run, None
    recording = (
        work.recordings.get(job.recording_id)
        if job.recording_id is not None
        else None
    )
    if recording is None:
        raise JiejianError(ErrorCode.JOB_PERSISTENCE, "任务关联录制不存在")
    return None, recording


def advance_job_target_after_claim(
    work: StorageUnitOfWork,
    job: JobRecord,
    now_us: int,
) -> tuple[RunRecord | None, RecordingRecord | None]:
    if job.run_id is not None:
        run = work.job_control.advance_run_after_claim(job.run_id, now_us)
        if run is None:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "运行状态无法进入预检")
        return run, None
    _, recording = load_job_target(work, job)
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


def finish_job_target(
    work: StorageUnitOfWork,
    job: JobRecord,
    now_us: int,
    *,
    run_target: RunLifecycle,
    recording_target: RecordingTerminalState,
    recording_reason: RecordingReasonCode,
) -> tuple[RunRecord | None, RecordingRecord | None]:
    if job.run_id is not None:
        run = work.job_control.transition_run_terminal(
            job.run_id,
            run_target,
            now_us,
        )
        if run is None:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "运行终态写入失败")
        return run, None
    _, recording = load_job_target(work, job)
    assert recording is not None
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
