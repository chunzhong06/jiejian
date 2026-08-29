# 验证 TraceBuilder 只从已发布 Audit Evidence 还原合法、漏洞、修复与 partial 路径。

from __future__ import annotations

from types import SimpleNamespace

import pytest

from product.backend.core.verification.trace import TraceAuthorizationDecision
from product.backend.workflows.results.trace import build_execution_trace
from product.protocols import ObservationCompleteness, ObserverType


SEMANTIC_KEYS = (
    "request_received",
    "server_identity_resolved",
    "export_request_created",
    "authorization_decided",
    "export_message_sent",
    "export_job_started",
    "archive_generated",
    "export_job_completed",
)


def _record(key: str, sequence: int, subject: str, decision: str | None = None) -> dict:
    event_id = f"event-{sequence}"
    return {
        "event_id": event_id,
        "parent_event_id": f"event-{sequence - 1}" if sequence > 1 else None,
        "case_tag": "request-marker",
        "task_id": "task-export" if sequence >= 3 else "",
        "event_type": key,
        "semantic_key": key,
        "sequence": sequence,
        "resource_id": "project-package",
        "kind": "authorization" if key == "authorization_decided" else "event",
        "subject_id": subject,
        "actor_id": "export-worker" if sequence >= 6 else subject,
        "credential_source": "session-cookie" if sequence <= 2 else None,
        "authority_scope": "project-export",
        "authorization_decision": decision,
        "source_component": "export-worker" if sequence >= 6 else "collaboration-server",
        "source_location": "export-background" if sequence >= 6 else "export-endpoint",
        "recorded_at_us": 1_000 + sequence,
    }


def _trace(
    subject: str,
    keys: tuple[str, ...],
    decision: str,
    *,
    completeness: ObservationCompleteness = ObservationCompleteness.COMPLETE,
):
    records = [
        _record(key, index, subject, decision if key == "authorization_decided" else None)
        for index, key in enumerate(keys, start=1)
    ]
    evidence = SimpleNamespace(
        evidence_id="ev_" + "b" * 20,
        case_snapshot=SimpleNamespace(
            case_id=f"case-{subject}",
            action_id="export-package",
            subject_id="member-subject" if subject == "bob" else "owner-subject",
        ),
        observations=(
            SimpleNamespace(
                observer_type=ObserverType.STRUCTURED_AUDIT_LOG,
                completeness=completeness,
                state=SimpleNamespace(canonical_data={"records": records}),
            ),
        ),
    )
    snapshot = SimpleNamespace(
        contract=SimpleNamespace(
            actions=(SimpleNamespace(action_id="export-package", effect_ids=("archive-created",)),),
        ),
    )
    return build_execution_trace(snapshot, evidence)


@pytest.mark.parametrize(
    ("subject", "decision"),
    [("alice", "ALLOW"), ("bob", "DENY")],
)
def test_builder_forms_complete_allow_and_vulnerable_paths(subject: str, decision: str) -> None:
    trace = _trace(subject, SEMANTIC_KEYS, decision)

    assert trace.complete is True
    assert tuple(event.semantic_key for event in trace.events) == SEMANTIC_KEYS
    assert next(
        event for event in trace.events if event.semantic_key == "authorization_decided"
    ).authorization_decision is TraceAuthorizationDecision(decision)
    if subject == "bob":
        assert trace.events[0].actor_id == "bob"
        assert trace.events[-1].actor_id == "export-worker"


def test_builder_forms_complete_fixed_deny_without_fake_downstream_events() -> None:
    trace = _trace("bob", SEMANTIC_KEYS[:2] + ("authorization_decided",), "DENY")

    assert trace.complete is True
    assert tuple(event.semantic_key for event in trace.events) == (
        "request_received",
        "server_identity_resolved",
        "authorization_decided",
    )


def test_builder_marks_incomplete_publication_partial() -> None:
    trace = _trace(
        "bob",
        SEMANTIC_KEYS[:4],
        "DENY",
        completeness=ObservationCompleteness.PARTIAL,
    )

    assert trace.complete is False
    assert set(trace.reason_codes) == {"TRACE_AUDIT_INCOMPLETE", "TRACE_EVENTS_MISSING"}
    assert all(event.semantic_key != "export_message_sent" for event in trace.events)
