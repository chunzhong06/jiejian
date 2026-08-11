from __future__ import annotations

import pytest
from pydantic import ValidationError

from jiejian.domain.recording import (
    Recording,
    RecordingReasonCode,
    RecordingState,
    RecordingTerminalState,
    transition_recording_state,
)
from jiejian.errors import JiejianError


def _recording() -> Recording:
    return Recording(
        schema_version="1",
        recording_id="rec_0123456789abcdef0123456789abcdef",
        project_id="ownership-recording",
        created_at_us=1,
        updated_at_us=1,
    )


def _transition(
    recording: Recording,
    target: RecordingState,
    occurred_at_us: int,
    **kwargs,
) -> Recording:
    return transition_recording_state(
        recording,
        target,
        operator="unit-test",
        occurred_at_us=occurred_at_us,
        **kwargs,
    )


def test_recording_normal_lifecycle_reaches_review_then_completion() -> None:
    recording = _transition(_recording(), RecordingState.STARTING, 2)
    recording = _transition(recording, RecordingState.RECORDING, 3)
    recording = _transition(
        recording,
        RecordingState.CLEANING,
        4,
        reason_code=RecordingReasonCode.RECORDING_FINISHED,
    )
    recording = _transition(recording, RecordingState.PROCESSING, 5)
    recording = _transition(recording, RecordingState.PENDING_REVIEW, 6)
    recording = _transition(
        recording,
        RecordingState.COMPLETED,
        7,
        reason_code=RecordingReasonCode.REVIEW_COMPLETED,
    )

    assert recording.state is RecordingState.COMPLETED
    assert recording.started_at_us == 2
    assert recording.capture_finished_at_us == 5
    assert recording.finished_at_us == 7
    assert tuple(event.sequence for event in recording.events) == (1, 2, 3, 4, 5, 6)


def test_recording_safety_stop_and_cleanup_failure_use_explicit_cleanup_state() -> None:
    recording = _transition(_recording(), RecordingState.STARTING, 2)
    recording = _transition(recording, RecordingState.RECORDING, 3)
    cleaning = _transition(
        recording,
        RecordingState.CLEANING,
        4,
        reason_code=RecordingReasonCode.TARGET_SCOPE_VIOLATION,
        pending_terminal_state=RecordingTerminalState.SAFETY_STOPPED,
    )
    stopped = _transition(
        cleaning,
        RecordingState.SAFETY_STOPPED,
        5,
        reason_code=RecordingReasonCode.TARGET_SCOPE_VIOLATION,
    )
    cleanup_failed = _transition(
        cleaning,
        RecordingState.FAILED,
        5,
        reason_code=RecordingReasonCode.CLEANUP_FAILED,
    )

    assert stopped.state is RecordingState.SAFETY_STOPPED
    assert cleanup_failed.state is RecordingState.FAILED
    assert cleanup_failed.reason_codes == (
        "TARGET_SCOPE_VIOLATION",
        "CLEANUP_FAILED",
    )


def test_recording_rejects_illegal_assignment_transition_and_time_regression() -> None:
    recording = _recording()
    with pytest.raises(JiejianError) as illegal:
        _transition(recording, RecordingState.RECORDING, 2)
    assert illegal.value.code == "RECORD_STATE_INVALID"

    starting = _transition(recording, RecordingState.STARTING, 2)
    with pytest.raises(JiejianError) as regressed:
        _transition(starting, RecordingState.RECORDING, 1)
    assert regressed.value.code == "RECORD_STATE_PRECONDITION"

    with pytest.raises(ValidationError):
        Recording.model_validate(
            {
                **recording.model_dump(mode="python"),
                "state": RecordingState.PROCESSING,
            }
        )
