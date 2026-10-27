# 录制草稿编译阶段的内部中间事实。
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from product.protocols.recording.flow_draft import FlowDraftVariableSource
from product.protocols.recording.events import RecordingEvent

@dataclass(slots=True)
class _LogicalAction:
    events: list[RecordingEvent]

    @property
    def action_ids(self) -> tuple[str, ...]:
        return tuple((event.action_id for event in self.events if event.action_id))

@dataclass(slots=True)
class _StepData:
    first_sequence: int
    identity_id: str
    actions: list[RecordingEvent] = field(default_factory=list)
    request: RecordingEvent | None = None
    response: RecordingEvent | None = None
    step_id: str = ''
    path: str | None = None
    json_body: dict[str, Any] = field(default_factory=dict)
    dependencies: set[str] = field(default_factory=set)

@dataclass(frozen=True, slots=True)
class _ValueSource:
    value: str | int
    source: FlowDraftVariableSource

@dataclass(slots=True)
class _VariableData:
    name: str
    candidates: tuple[FlowDraftVariableSource, ...]
    consumers: set[str] = field(default_factory=set)
