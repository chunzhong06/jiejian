# 验证 FlowDraft 构造、审阅修订与目标/资源确认边界。

from __future__ import annotations
import json
from pathlib import Path
import pytest
from product.backend.core.errors import JiejianError
from product.backend.workflows.recording.processing import FlowDraftProcessor
from product.protocols import (
    FlowDraft,
    FlowDraftVariableStatus,
    RecordingEvent,
    RecordingEventKind,
    RecordingHeader,
    canonical_flow_draft_json_bytes,
    flow_draft_review_command_schema,
    parse_flow_draft,
)
PROJECT_ROOT = Path(__file__).resolve().parents[4]
ACTION_CANDIDATE_ID = "action_0123456789abcdef0123456789abcdef"

def recorded_events() -> tuple[RecordingEvent, ...]:
    common = {
        "schema_version": "1",
        "identity_id": "recording-subject",
        "page_id": "page_000001",
        "frame_id": "frame_000001",
    }
    return (
        RecordingEvent(
            **common,
            sequence=1,
            occurred_at_us=1,
            kind=RecordingEventKind.UI_INPUT_CHANGE,
            action_id="action_000001",
            element_locator='input[name="password"]',
            field_name="password",
            input_type="password",
        ),
        RecordingEvent(
            **common,
            sequence=2,
            occurred_at_us=2,
            kind=RecordingEventKind.UI_SUBMIT,
            action_id="action_000002",
            element_locator="form#resource-form",
        ),
        RecordingEvent(
            **common,
            sequence=3,
            occurred_at_us=3,
            kind=RecordingEventKind.REQUEST,
            request_id="request_000001",
            caused_by_action_id="action_000002",
            url="http://127.0.0.1:8080/resources",
            method="POST",
            resource_type="fetch",
            headers=(
                RecordingHeader(name="authorization", value="[REDACTED]"),
                RecordingHeader(name="content-type", value="application/json"),
            ),
            body='{"password":"[REDACTED]","value":"draft"}',
        ),
        RecordingEvent(
            **common,
            sequence=4,
            occurred_at_us=4,
            kind=RecordingEventKind.RESPONSE,
            request_id="request_000001",
            url="http://127.0.0.1:8080/resources",
            status_code=201,
            headers=(RecordingHeader(name="location", value="/resources/resource-42"),),
            body='{"id":"resource-42","token":"[REDACTED]"}',
        ),
        RecordingEvent(
            **common,
            sequence=5,
            occurred_at_us=5,
            kind=RecordingEventKind.UI_CLICK,
            action_id="action_000003",
            element_locator='button[data-testid="modify-resource"]',
        ),
        RecordingEvent(
            **common,
            sequence=6,
            occurred_at_us=6,
            kind=RecordingEventKind.REQUEST,
            request_id="request_000002",
            caused_by_action_id="action_000003",
            url="http://127.0.0.1:8080/resources/resource-42",
            method="PATCH",
            resource_type="fetch",
            body='{"name":"updated"}',
        ),
        RecordingEvent(
            **common,
            sequence=7,
            occurred_at_us=7,
            kind=RecordingEventKind.RESPONSE,
            request_id="request_000002",
            url="http://127.0.0.1:8080/resources/resource-42",
            status_code=200,
            body='{"id":"resource-42"}',
        ),
        RecordingEvent(
            **common,
            sequence=8,
            occurred_at_us=8,
            kind=RecordingEventKind.UI_CLICK,
            action_id="action_000004",
            element_locator='button[data-testid="unused"]',
        ),
    )

def build_draft() -> FlowDraft:
    return FlowDraftProcessor().build(
        recording_id="rec_0123456789abcdef0123456789abcdef",
        flow_id="recorded-flow",
        action_candidate_id=ACTION_CANDIDATE_ID,
        events=recorded_events(),
    )

def test_events_build_action_centered_draft_and_current_schemas() -> None:
    first = build_draft()
    second = build_draft()

    assert first == second
    assert first.schema_version == "1"
    assert first.action_candidate_id == ACTION_CANDIDATE_ID
    assert first.recommended_target_step_id == "step-000002"
    assert first.target_step_id is None
    assert first.steps[1].path == "/resources/{resource_id}"
    assert any(item.location == "path[1]" for item in first.steps[1].resource_candidates)
    assert any(item.label.startswith("updated ·") for item in first.steps[1].resource_candidates)
    assert all(
        "path[" not in item.label and "$." not in item.label
        for item in first.steps[1].resource_candidates
    )
    assert first.variables[0].status is FlowDraftVariableStatus.UNCONFIRMED
    assert "$.password" in first.steps[0].sensitive_fields
    assert "headers.authorization" in first.steps[0].sensitive_fields
    encoded = canonical_flow_draft_json_bytes(first)
    assert b"resource-42" not in encoded
    assert parse_flow_draft(encoded) == first

    schema_root = PROJECT_ROOT / "product" / "protocols" / "schemas" / "recording"
    assert json.loads((schema_root / "flow-draft.schema.json").read_text()) == FlowDraft.model_json_schema()
    assert json.loads((schema_root / "flow-draft-review-command.schema.json").read_text()) == flow_draft_review_command_schema()

def test_direct_user_request_outranks_later_automatic_recovery() -> None:
    common = {
        "schema_version": "1",
        "identity_id": "recording-subject",
        "page_id": "page_000001",
        "frame_id": "frame_000001",
    }
    events = (
        RecordingEvent(
            **common,
            sequence=1,
            occurred_at_us=1,
            kind=RecordingEventKind.UI_CLICK,
            action_id="action_000001",
            element_locator="#modify-resource",
        ),
        RecordingEvent(
            **common,
            sequence=2,
            occurred_at_us=2,
            kind=RecordingEventKind.REQUEST,
            request_id="request_000001",
            caused_by_action_id="action_000001",
            url="http://127.0.0.1:8080/resources/owner-resource",
            method="PATCH",
            resource_type="fetch",
            body='{"value":"changed"}',
        ),
        RecordingEvent(
            **common,
            sequence=3,
            occurred_at_us=3,
            kind=RecordingEventKind.RESPONSE,
            request_id="request_000001",
            url="http://127.0.0.1:8080/resources/owner-resource",
            status_code=200,
            body='{"value":"changed"}',
        ),
        RecordingEvent(
            **common,
            sequence=4,
            occurred_at_us=4,
            kind=RecordingEventKind.REQUEST,
            request_id="request_000002",
            url="http://127.0.0.1:8080/resources/owner-resource",
            method="PATCH",
            resource_type="fetch",
            body='{"value":"initial"}',
        ),
        RecordingEvent(
            **common,
            sequence=5,
            occurred_at_us=5,
            kind=RecordingEventKind.RESPONSE,
            request_id="request_000002",
            url="http://127.0.0.1:8080/resources/owner-resource",
            status_code=200,
            body='{"value":"initial"}',
        ),
    )

    draft = FlowDraftProcessor().build(
        recording_id="rec_abcdefabcdefabcdefabcdefabcdefab",
        flow_id="recorded-flow",
        action_candidate_id=ACTION_CANDIDATE_ID,
        events=events,
    )

    assert draft.recommended_target_step_id == "step-000001"
