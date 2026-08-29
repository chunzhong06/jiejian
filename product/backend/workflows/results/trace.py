# 已发布 ExecutionTrace 构建：只消费冻结快照与 Evidence，不读取当前目标或运行现场。

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import ValidationError

from product.backend.core.verification.trace import (
    ExecutionTrace,
    TraceAuthorizationDecision,
    TraceCorrelationKind,
    TraceEvent,
)
from product.protocols.observer import ObservationCompleteness, ObserverType


_SEMANTIC_KEYS = frozenset(
    {
        "request_received",
        "server_identity_resolved",
        "export_request_created",
        "authorization_decided",
        "export_message_sent",
        "export_job_started",
        "export_job_completed",
        "archive_generated",
    }
)
_FIXED_DENY_KEYS = frozenset(
    {"request_received", "server_identity_resolved", "authorization_decided"}
)
_DOWNSTREAM_KEYS = frozenset(
    {"export_message_sent", "export_job_started", "archive_generated", "export_job_completed"}
)


def build_execution_traces(snapshot: Any, evidence_items: Iterable[Any]) -> tuple[ExecutionTrace, ...]:
    """为每份已发布 Case Evidence 构建一条确定性只读 Trace。"""

    traces = tuple(build_execution_trace(snapshot, evidence) for evidence in evidence_items)
    return tuple(sorted(traces, key=lambda item: (item.case_id, item.action_id)))


def build_execution_trace(snapshot: Any, evidence: Any) -> ExecutionTrace:
    # 单条构建同样只接收调用方已加载的冻结对象，不能借缺口回读 live runtime。
    case = evidence.case_snapshot
    case_id = str(case.case_id)
    action_id = str(case.action_id)
    planned_subject_id = str(case.subject_id)
    evidence_id = str(evidence.evidence_id)
    reasons: set[str] = set()
    records_by_id: dict[str, Mapping[str, Any]] = {}
    observed_audit_records = False
    complete_audit_records = False

    for observation in getattr(evidence, "observations", ()):
        if _value(getattr(observation, "observer_type", None)) != ObserverType.STRUCTURED_AUDIT_LOG.value:
            continue
        state = getattr(observation, "state", None)
        canonical_data = getattr(state, "canonical_data", None)
        records = canonical_data.get("records") if isinstance(canonical_data, Mapping) else None
        if not isinstance(records, list) or not records:
            continue
        observed_audit_records = True
        if _value(getattr(observation, "completeness", None)) == ObservationCompleteness.COMPLETE.value:
            complete_audit_records = True
        else:
            reasons.add("TRACE_AUDIT_INCOMPLETE")
        for record in records:
            if not isinstance(record, Mapping):
                reasons.add("TRACE_EVENT_INVALID")
                continue
            event_id = record.get("event_id")
            if not isinstance(event_id, str):
                reasons.add("TRACE_EVENT_INVALID")
                continue
            existing = records_by_id.get(event_id)
            if existing is not None and dict(existing) != dict(record):
                reasons.add("TRACE_EVENT_CONFLICT")
                continue
            records_by_id[event_id] = record

    if not observed_audit_records:
        reasons.add("TRACE_AUDIT_UNAVAILABLE")
    elif not complete_audit_records:
        reasons.add("TRACE_AUDIT_INCOMPLETE")

    action = next(
        (
            item
            for item in getattr(getattr(snapshot, "contract", None), "actions", ())
            if str(getattr(item, "action_id", "")) == action_id
        ),
        None,
    )
    effect_ids = tuple(str(value) for value in getattr(action, "effect_ids", ()))
    single_effect_id = effect_ids[0] if len(effect_ids) == 1 else None
    events: list[TraceEvent] = []
    for record in records_by_id.values():
        semantic_key = record.get("semantic_key")
        if semantic_key not in _SEMANTIC_KEYS:
            continue
        if record.get("event_type") != semantic_key:
            reasons.add("TRACE_EVENT_INVALID")
            continue
        parent_event_id = record.get("parent_event_id")
        try:
            event = TraceEvent(
                event_id=str(record["event_id"]),
                parent_event_ids=(str(parent_event_id),) if parent_event_id else (),
                case_id=case_id,
                action_id=action_id,
                resource_ids=(str(record["resource_id"]),),
                kind=str(record["kind"]),
                semantic_key=str(semantic_key),
                subject_id=_optional_string(record.get("subject_id")),
                actor_id=_optional_string(record.get("actor_id")),
                credential_source=_optional_string(record.get("credential_source")),
                authority_scope=(str(record["authority_scope"]),) if record.get("authority_scope") else (),
                authorization_decision=(
                    TraceAuthorizationDecision(str(record["authorization_decision"]))
                    if record.get("authorization_decision") is not None
                    else None
                ),
                effect_id=(
                    single_effect_id
                    if semantic_key
                    in {"authorization_decided", "archive_generated", "export_job_completed"}
                    else None
                ),
                source_component=str(record["source_component"]),
                source_location=str(record["source_location"]),
                correlation_kind=(
                    TraceCorrelationKind.EXPLICIT_PARENT
                    if parent_event_id
                    else TraceCorrelationKind.CASE_MARKER
                ),
                evidence_refs=(evidence_id,),
                recorded_at_us=int(record["recorded_at_us"]),
            )
        except (KeyError, TypeError, ValueError, ValidationError):
            reasons.add("TRACE_EVENT_INVALID")
            continue
        events.append(event)

    # 缺 parent 时删除该节点及其后继，不插入未知占位节点。
    while True:
        event_ids = {event.event_id for event in events}
        invalid_ids = {
            event.event_id
            for event in events
            if any(parent not in event_ids for parent in event.parent_event_ids)
        }
        if not invalid_ids:
            break
        reasons.add("TRACE_PARENT_MISSING")
        events = [event for event in events if event.event_id not in invalid_ids]

    semantic_keys = {event.semantic_key for event in events}
    decisions = [
        event.authorization_decision
        for event in events
        if event.semantic_key == "authorization_decided"
    ]
    expected_keys = _SEMANTIC_KEYS
    if decisions == [TraceAuthorizationDecision.DENY] and not (semantic_keys & _DOWNSTREAM_KEYS):
        expected_keys = _FIXED_DENY_KEYS
    if len(decisions) != 1 or semantic_keys != expected_keys:
        reasons.add("TRACE_EVENTS_MISSING")

    complete = not reasons
    return ExecutionTrace(
        case_id=case_id,
        action_id=action_id,
        planned_subject_id=planned_subject_id,
        events=tuple(events),
        complete=complete,
        reason_codes=tuple(sorted(reasons)),
    )


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None else None


def _value(value: Any) -> str:
    return str(getattr(value, "value", value)) if value is not None else ""


__all__ = ["build_execution_trace", "build_execution_traces"]
