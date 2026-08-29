# 验证 ExecutionTrace 的稳定 DAG、父引用、环检测与秘密拒绝边界。

from __future__ import annotations

import pytest
from pydantic import ValidationError

from product.backend.core.verification.trace import (
    ExecutionTrace,
    TraceAuthorityScope,
    TraceCorrelationKind,
    TraceEvent,
    TraceEventKind,
)


CASE_ID = "case-trace"
ACTION_ID = "export-package"
EVIDENCE_ID = "ev_" + "a" * 20


def _event(
    event_id: str,
    *,
    parent: str | None = None,
    recorded_at_us: int,
    source_location: str = "export-endpoint",
) -> TraceEvent:
    return TraceEvent(
        event_id=event_id,
        parent_event_ids=(parent,) if parent else (),
        case_id=CASE_ID,
        action_id=ACTION_ID,
        resource_ids=("project-package",),
        kind=TraceEventKind.ENTRY,
        semantic_key="request_received",
        subject_id="bob",
        actor_id="bob",
        credential_source="session-cookie",
        authority_scope=TraceAuthorityScope(
            allowed_action_ids=(ACTION_ID,),
            allowed_resource_ids=("project-package",),
        ),
        source_component="collaboration-server",
        source_location=source_location,
        correlation_kind=(
            TraceCorrelationKind.EXPLICIT_PARENT if parent else TraceCorrelationKind.CASE_MARKER
        ),
        evidence_refs=(EVIDENCE_ID,),
        recorded_at_us=recorded_at_us,
    )


def test_trace_stably_sorts_events_without_breaking_parent_order() -> None:
    trace = ExecutionTrace(
        case_id=CASE_ID,
        action_id=ACTION_ID,
        planned_subject_id="member-subject",
        events=(
            _event("child", parent="root-b", recorded_at_us=1),
            _event("root-b", recorded_at_us=3),
            _event("root-a", recorded_at_us=2),
        ),
        complete=True,
    )

    assert [event.event_id for event in trace.events] == ["root-a", "root-b", "child"]
    assert trace.events[0].kind is TraceEventKind.ENTRY
    assert trace.events[0].authority_scope.allowed_action_ids == (ACTION_ID,)


@pytest.mark.parametrize(
    "events",
    [
        (_event("child", parent="missing", recorded_at_us=2),),
        (
            _event("event-a", parent="event-b", recorded_at_us=1),
            _event("event-b", parent="event-a", recorded_at_us=2),
        ),
    ],
)
def test_trace_rejects_missing_parents_and_cycles(events: tuple[TraceEvent, ...]) -> None:
    with pytest.raises(ValidationError):
        ExecutionTrace(
            case_id=CASE_ID,
            action_id=ACTION_ID,
            planned_subject_id="member-subject",
            events=events,
            complete=False,
            reason_codes=("TRACE_PARTIAL",),
        )


def test_trace_rejects_inline_secret_material() -> None:
    with pytest.raises(ValidationError):
        _event(
            "secret-event",
            recorded_at_us=1,
            source_location="token=private-value",
        )


def test_trace_rejects_secret_or_missing_authority_references() -> None:
    with pytest.raises(ValidationError):
        TraceAuthorityScope(allowed_action_ids=("token=private-value",))

    event = _event("scoped-event", recorded_at_us=1).model_copy(
        update={
            "authority_scope": TraceAuthorityScope(
                allowed_action_ids=(ACTION_ID,),
                allowed_resource_ids=("project-package",),
                origin_authorization_event_id="missing-authorization",
            )
        }
    )
    with pytest.raises(ValidationError):
        ExecutionTrace(
            case_id=CASE_ID,
            action_id=ACTION_ID,
            planned_subject_id="member-subject",
            events=(event,),
            complete=True,
        )
