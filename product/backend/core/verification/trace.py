# ExecutionTrace 只读事实模型：表达单个 Case 的真实事件 DAG，不参与安全判定。

from __future__ import annotations

import heapq
import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_PUBLIC_ID = r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}$"
_SEMANTIC_KEY = r"^[a-z][a-z0-9_]{0,63}$"
_REASON_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_INLINE_SECRET = re.compile(
    r"(?:\bBearer\s+\S+|\b(?:authorization|cookie|credential|password|passwd|"
    r"secret|token|api[_-]?key)\s*[:=]\s*\S+)",
    re.IGNORECASE,
)


class _TraceModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class TraceCorrelationKind(StrEnum):
    EXPLICIT_PARENT = "EXPLICIT_PARENT"
    CASE_MARKER = "CASE_MARKER"
    RESOURCE_LINK = "RESOURCE_LINK"
    TEMPORAL = "TEMPORAL"


class TraceAuthorizationDecision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"


# 单个节点只承载有界事实引用；原始正文、秘密和安全结论都不进入该模型。
class TraceEvent(_TraceModel):
    event_id: str = Field(pattern=_PUBLIC_ID)
    parent_event_ids: tuple[str, ...] = Field(default=(), max_length=16)
    case_id: str = Field(pattern=_PUBLIC_ID)
    action_id: str = Field(pattern=_PUBLIC_ID)
    resource_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    kind: str = Field(pattern=_SEMANTIC_KEY)
    semantic_key: str = Field(pattern=_SEMANTIC_KEY)
    subject_id: str | None = Field(default=None, pattern=_PUBLIC_ID)
    actor_id: str | None = Field(default=None, pattern=_PUBLIC_ID)
    credential_source: str | None = Field(default=None, pattern=_PUBLIC_ID)
    authority_scope: tuple[str, ...] = Field(default=(), max_length=32)
    authorization_decision: TraceAuthorizationDecision | None = None
    effect_id: str | None = Field(default=None, pattern=_PUBLIC_ID)
    source_component: str = Field(pattern=_PUBLIC_ID)
    source_location: str = Field(pattern=_PUBLIC_ID)
    correlation_kind: TraceCorrelationKind
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=64)
    recorded_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_event(self) -> TraceEvent:
        if self.event_id in self.parent_event_ids:
            raise ValueError("trace event cannot reference itself as a parent")
        if len(set(self.parent_event_ids)) != len(self.parent_event_ids):
            raise ValueError("trace event parent references must be unique")
        if len(set(self.resource_ids)) != len(self.resource_ids):
            raise ValueError("trace event resource IDs must be unique")
        if len(set(self.authority_scope)) != len(self.authority_scope):
            raise ValueError("trace event authority scope must be unique")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("trace event evidence refs must be unique")
        for value in (
            self.event_id,
            *self.parent_event_ids,
            self.case_id,
            self.action_id,
            *self.resource_ids,
            self.kind,
            self.semantic_key,
            self.subject_id,
            self.actor_id,
            self.credential_source,
            *self.authority_scope,
            self.effect_id,
            self.source_component,
            self.source_location,
            *self.evidence_refs,
        ):
            if value is not None and _INLINE_SECRET.search(value):
                raise ValueError("secret material must not enter a trace event")
        object.__setattr__(self, "parent_event_ids", tuple(sorted(self.parent_event_ids)))
        object.__setattr__(self, "resource_ids", tuple(sorted(self.resource_ids)))
        object.__setattr__(self, "authority_scope", tuple(sorted(self.authority_scope)))
        object.__setattr__(self, "evidence_refs", tuple(sorted(self.evidence_refs)))
        return self


# 一条 Trace 严格绑定一个 Case/Action，并在构造时收敛为稳定拓扑顺序。
class ExecutionTrace(_TraceModel):
    schema_version: Literal["1"] = "1"
    case_id: str = Field(pattern=_PUBLIC_ID)
    action_id: str = Field(pattern=_PUBLIC_ID)
    planned_subject_id: str = Field(pattern=_PUBLIC_ID)
    events: tuple[TraceEvent, ...] = Field(default=(), max_length=512)
    complete: bool
    reason_codes: tuple[str, ...] = Field(default=(), max_length=64)

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values):
            raise ValueError("trace reason codes must be unique")
        if any(not _REASON_CODE.fullmatch(value) for value in values):
            raise ValueError("trace reason codes must be stable uppercase tokens")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_trace(self) -> ExecutionTrace:
        if self.complete and (not self.events or self.reason_codes):
            raise ValueError("complete trace requires events and no reason codes")
        if not self.complete and not self.reason_codes:
            raise ValueError("partial trace requires a reason code")
        by_id = {event.event_id: event for event in self.events}
        if len(by_id) != len(self.events):
            raise ValueError("trace event IDs must be unique")
        for event in self.events:
            if event.case_id != self.case_id or event.action_id != self.action_id:
                raise ValueError("trace event does not match trace case and action")
            if any(parent not in by_id for parent in event.parent_event_ids):
                raise ValueError("trace event references a missing parent")
        ordered = _stable_topological_order(by_id)
        object.__setattr__(self, "events", ordered)
        return self


def _stable_topological_order(events: dict[str, TraceEvent]) -> tuple[TraceEvent, ...]:
    indegree = {event_id: len(event.parent_event_ids) for event_id, event in events.items()}
    children: dict[str, list[str]] = {event_id: [] for event_id in events}
    for event in events.values():
        for parent in event.parent_event_ids:
            children[parent].append(event.event_id)
    ready = [
        (event.recorded_at_us, event.event_id)
        for event in events.values()
        if indegree[event.event_id] == 0
    ]
    heapq.heapify(ready)
    ordered: list[TraceEvent] = []
    while ready:
        _, event_id = heapq.heappop(ready)
        event = events[event_id]
        ordered.append(event)
        for child_id in sorted(children[event_id]):
            indegree[child_id] -= 1
            if indegree[child_id] == 0:
                child = events[child_id]
                heapq.heappush(ready, (child.recorded_at_us, child.event_id))
    if len(ordered) != len(events):
        raise ValueError("trace event graph contains a cycle")
    return tuple(ordered)


__all__ = [
    "ExecutionTrace",
    "TraceAuthorizationDecision",
    "TraceCorrelationKind",
    "TraceEvent",
]
