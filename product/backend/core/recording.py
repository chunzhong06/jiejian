# =============================================================================
# Recording 生命周期
#
# 定位
# 浏览器录制状态、预算与显式转换的纯领域边界。
#
# 职责
# 约束合法状态迁移｜校验时间单调性｜生成不可变 Recording 新状态
#
# 边界
# 不启动浏览器、不持久化事件，也不允许基础设施绕过状态转换函数直接改写状态。
#
# 调用链
# Recording workflow / Job handler → transition_recording_state → Recording
# =============================================================================

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.identifiers import PROJECT_ID_PATTERN, RECORDING_ID_PATTERN

_REASON_CODE = r"^[A-Z][A-Z0-9_]{0,127}$"


class RecordingState(StrEnum):
    CREATED = "CREATED"
    STARTING = "STARTING"
    RECORDING = "RECORDING"
    CLEANING = "CLEANING"
    PROCESSING = "PROCESSING"
    PENDING_REVIEW = "PENDING_REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SAFETY_STOPPED = "SAFETY_STOPPED"


class RecordingTerminalState(StrEnum):
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SAFETY_STOPPED = "SAFETY_STOPPED"


class RecordingReasonCode(StrEnum):
    RECORDING_FINISHED = "RECORDING_FINISHED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    TARGET_SCOPE_VIOLATION = "TARGET_SCOPE_VIOLATION"
    EVENT_BUDGET_EXCEEDED = "EVENT_BUDGET_EXCEEDED"
    SESSION_REFERENCE_EXPIRED = "SESSION_REFERENCE_EXPIRED"
    UNSUPPORTED_RESPONSE = "UNSUPPORTED_RESPONSE"
    BROWSER_START_FAILED = "BROWSER_START_FAILED"
    BROWSER_INTERACTION_FAILED = "BROWSER_INTERACTION_FAILED"
    PROCESSING_FAILED = "PROCESSING_FAILED"
    CLEANUP_FAILED = "CLEANUP_FAILED"
    REVIEW_COMPLETED = "REVIEW_COMPLETED"


class RecordingModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    schema_version: Literal["1"] = "1"


class RecordingStateEvent(RecordingModel):
    sequence: int = Field(ge=1)
    source: RecordingState
    target: RecordingState
    operator: str = Field(min_length=1, max_length=128)
    occurred_at_us: int = Field(ge=0)
    reason_code: str | None = Field(default=None, pattern=_REASON_CODE)


class Recording(RecordingModel):
    recording_id: str = Field(pattern=RECORDING_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    state: RecordingState = RecordingState.CREATED
    created_at_us: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)
    started_at_us: int | None = Field(default=None, ge=0)
    capture_finished_at_us: int | None = Field(default=None, ge=0)
    finished_at_us: int | None = Field(default=None, ge=0)
    pending_terminal_state: RecordingTerminalState | None = None
    reason_codes: tuple[str, ...] = Field(default=(), max_length=64)
    events: tuple[RecordingStateEvent, ...] = Field(default=(), max_length=128)

    @model_validator(mode="after")
    def validate_lifecycle_times(self) -> Recording:
        if self.updated_at_us < self.created_at_us:
            raise ValueError("recording update time precedes creation")
        if self.started_at_us is not None and self.started_at_us < self.created_at_us:
            raise ValueError("recording start time precedes creation")
        if (
            self.capture_finished_at_us is not None
            and self.started_at_us is not None
            and self.capture_finished_at_us < self.started_at_us
        ):
            raise ValueError("recording capture finish precedes start")
        if self.finished_at_us is not None and self.finished_at_us < self.updated_at_us:
            raise ValueError("recording finish time precedes update")
        if len(set(self.reason_codes)) != len(self.reason_codes) or any(
            re.fullmatch(_REASON_CODE, code) is None for code in self.reason_codes
        ):
            raise ValueError("recording reason codes must be unique stable codes")
        expected_sequences = tuple(range(1, len(self.events) + 1))
        if tuple(event.sequence for event in self.events) != expected_sequences:
            raise ValueError("recording event sequence must be continuous")
        terminal_states = {
            RecordingState.COMPLETED,
            RecordingState.FAILED,
            RecordingState.CANCELLED,
            RecordingState.SAFETY_STOPPED,
        }
        if (self.state in terminal_states) != (self.finished_at_us is not None):
            raise ValueError("recording terminal state and finish time must agree")
        if (
            self.pending_terminal_state is not None
            and self.state is not RecordingState.CLEANING
        ):
            raise ValueError("pending terminal state only belongs to cleanup")
        started_states = {
            RecordingState.STARTING,
            RecordingState.RECORDING,
            RecordingState.CLEANING,
            RecordingState.PROCESSING,
            RecordingState.PENDING_REVIEW,
            RecordingState.COMPLETED,
            RecordingState.SAFETY_STOPPED,
        }
        if self.state in started_states and self.started_at_us is None:
            raise ValueError("started recording state requires start time")
        processed_states = {
            RecordingState.PROCESSING,
            RecordingState.PENDING_REVIEW,
            RecordingState.COMPLETED,
        }
        if self.state in processed_states and self.capture_finished_at_us is None:
            raise ValueError("processed recording state requires capture finish time")
        return self


_TRANSITIONS: dict[RecordingState, frozenset[RecordingState]] = {
    RecordingState.CREATED: frozenset(
        {RecordingState.STARTING, RecordingState.FAILED, RecordingState.CANCELLED}
    ),
    RecordingState.STARTING: frozenset(
        {RecordingState.RECORDING, RecordingState.CLEANING}
    ),
    RecordingState.RECORDING: frozenset({RecordingState.CLEANING}),
    RecordingState.CLEANING: frozenset(
        {
            RecordingState.PROCESSING,
            RecordingState.FAILED,
            RecordingState.CANCELLED,
            RecordingState.SAFETY_STOPPED,
        }
    ),
    RecordingState.PROCESSING: frozenset(
        {RecordingState.PENDING_REVIEW, RecordingState.CLEANING}
    ),
    RecordingState.PENDING_REVIEW: frozenset(
        {RecordingState.COMPLETED, RecordingState.CANCELLED}
    ),
}


def transition_recording_state(
    recording: Recording,
    target: RecordingState | str,
    *,
    operator: str,
    occurred_at_us: int,
    reason_code: RecordingReasonCode | str | None = None,
    pending_terminal_state: RecordingTerminalState | None = None,
) -> Recording:
    """校验并执行一次 Recording 转换；清理前后的终态意图必须明确匹配。"""

    if not operator.strip():
        raise JiejianError(ErrorCode.STATE_OPERATOR_REQUIRED, "录制转换必须记录操作者")
    if occurred_at_us < recording.updated_at_us:
        raise JiejianError(
            ErrorCode.RECORD_STATE_PRECONDITION,
            "录制状态时间不得倒退",
        )
    try:
        resolved = target if isinstance(target, RecordingState) else RecordingState(target)
    except ValueError:
        raise JiejianError(ErrorCode.RECORD_STATE_INVALID, "录制目标状态不存在") from None
    if resolved not in _TRANSITIONS.get(recording.state, frozenset()):
        raise JiejianError(
            ErrorCode.RECORD_STATE_INVALID,
            "非法录制状态转换",
            details={"source": recording.state.value, "target": resolved.value},
        )

    stable_reason = (
        reason_code.value if isinstance(reason_code, RecordingReasonCode) else reason_code
    )
    updates: dict[str, object] = {
        "state": resolved,
        "updated_at_us": occurred_at_us,
        "pending_terminal_state": None,
    }
    if resolved is RecordingState.STARTING:
        updates["started_at_us"] = occurred_at_us
    if resolved is RecordingState.CLEANING:
        if pending_terminal_state is None and recording.state is not RecordingState.RECORDING:
            raise JiejianError(
                ErrorCode.RECORD_STATE_PRECONDITION,
                "非正常停止进入清理时必须声明终态",
            )
        updates["pending_terminal_state"] = pending_terminal_state
    elif recording.state is RecordingState.CLEANING:
        expected = recording.pending_terminal_state
        if resolved is RecordingState.PROCESSING:
            if expected is not None:
                raise JiejianError(
                    ErrorCode.RECORD_STATE_PRECONDITION,
                    "带终态意图的清理不能进入处理",
                )
            updates["capture_finished_at_us"] = occurred_at_us
        elif expected is not None and resolved.value != expected.value:
            cleanup_failed = (
                resolved is RecordingState.FAILED
                and stable_reason == RecordingReasonCode.CLEANUP_FAILED.value
            )
            if not cleanup_failed:
                raise JiejianError(
                    ErrorCode.RECORD_STATE_PRECONDITION,
                    "清理完成状态与终态意图不一致",
                )
    if resolved in {
        RecordingState.COMPLETED,
        RecordingState.FAILED,
        RecordingState.CANCELLED,
        RecordingState.SAFETY_STOPPED,
    }:
        updates["finished_at_us"] = occurred_at_us
    reason_codes = recording.reason_codes
    if stable_reason is not None and stable_reason not in reason_codes:
        reason_codes = (*reason_codes, stable_reason)
    updates["reason_codes"] = reason_codes
    event = RecordingStateEvent(
        schema_version="1",
        sequence=len(recording.events) + 1,
        source=recording.state,
        target=resolved,
        operator=operator,
        occurred_at_us=occurred_at_us,
        reason_code=stable_reason,
    )
    updates["events"] = (*recording.events, event)
    return Recording.model_validate({**recording.model_dump(mode="python"), **updates})
