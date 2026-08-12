from __future__ import annotations

import json
from pathlib import Path

import pytest

from jiejian.errors import JiejianError
from jiejian.protocols import (
    ConfirmFlowDraftVariableV1,
    DeleteFlowDraftStepV1,
    FlowDraftV1,
    FlowDraftVariableStatus,
    MergeFlowDraftStepsV1,
    RecordingEventKind,
    RecordingEventV1,
    RecordingHeaderV1,
    RenameFlowDraftStepV1,
    canonical_flow_draft_json_bytes,
    flow_draft_review_command_schema,
    parse_flow_draft,
)
from jiejian.recording.processing import FlowDraftProcessor
from jiejian.recording.review import FlowDraftReviewer

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def recorded_events() -> tuple[RecordingEventV1, ...]:
    common = {
        "schema_version": "1",
        "identity_id": "owner",
        "page_id": "page_000001",
        "frame_id": "frame_000001",
    }
    return (
        RecordingEventV1(
            **common,
            sequence=1,
            occurred_at_us=1,
            kind=RecordingEventKind.UI_INPUT_CHANGE,
            action_id="action_000001",
            element_locator='input[name="password"]',
            field_name="password",
            input_type="password",
        ),
        RecordingEventV1(
            **common,
            sequence=2,
            occurred_at_us=2,
            kind=RecordingEventKind.UI_INPUT_CHANGE,
            action_id="action_000002",
            element_locator='input[name="password"]',
            field_name="password",
            input_type="password",
        ),
        RecordingEventV1(
            **common,
            sequence=3,
            occurred_at_us=3,
            kind=RecordingEventKind.UI_SUBMIT,
            action_id="action_000003",
            element_locator="form#resource-form",
        ),
        RecordingEventV1(
            **common,
            sequence=4,
            occurred_at_us=4,
            kind=RecordingEventKind.REQUEST,
            request_id="request_000001",
            caused_by_action_id="action_000003",
            url="http://127.0.0.1:8080/resources",
            method="POST",
            resource_type="fetch",
            headers=(
                RecordingHeaderV1(
                    schema_version="1",
                    name="authorization",
                    value="[REDACTED]",
                ),
                RecordingHeaderV1(
                    schema_version="1",
                    name="content-type",
                    value="application/json",
                ),
            ),
            body='{"password":"[REDACTED]","value":"draft"}',
        ),
        RecordingEventV1(
            **common,
            sequence=5,
            occurred_at_us=5,
            kind=RecordingEventKind.RESPONSE,
            request_id="request_000001",
            url="http://127.0.0.1:8080/resources",
            status_code=201,
            headers=(
                RecordingHeaderV1(
                    schema_version="1",
                    name="location",
                    value="/resources/resource-42",
                ),
            ),
            body='{"id":"resource-42","token":"[REDACTED]"}',
        ),
        RecordingEventV1(
            **common,
            sequence=6,
            occurred_at_us=6,
            kind=RecordingEventKind.UI_CLICK,
            action_id="action_000004",
            element_locator='a[data-testid="resource-link"]',
        ),
        RecordingEventV1(
            **common,
            sequence=7,
            occurred_at_us=7,
            kind=RecordingEventKind.REQUEST,
            request_id="request_000002",
            caused_by_action_id="action_000004",
            url="http://127.0.0.1:8080/resources/resource-42",
            method="GET",
            resource_type="fetch",
        ),
        RecordingEventV1(
            **common,
            sequence=8,
            occurred_at_us=8,
            kind=RecordingEventKind.RESPONSE,
            request_id="request_000002",
            url="http://127.0.0.1:8080/resources/resource-42",
            status_code=200,
            body='{"id":"resource-42"}',
        ),
        RecordingEventV1(
            **common,
            sequence=9,
            occurred_at_us=9,
            kind=RecordingEventKind.UI_CLICK,
            action_id="action_000005",
            element_locator='button[data-testid="unused"]',
        ),
    )


def build_draft() -> FlowDraftV1:
    return FlowDraftProcessor().build(
        recording_id="rec_0123456789abcdef0123456789abcdef",
        flow_id="recorded-flow",
        events=recorded_events(),
        alternate_identities={"owner": "attacker"},
        resource_bindings={
            "request_000001": ("owner-resource", "attacker-resource"),
            "request_000002": ("owner-resource", "attacker-resource"),
        },
    )


def test_events_build_deterministic_redacted_draft_with_dynamic_dag() -> None:
    first = build_draft()
    second = build_draft()

    assert first == second
    assert len(first.steps) == 4
    assert first.steps[0].action_ids == ("action_000001", "action_000002")
    assert first.steps[2].request_id == "request_000002"
    assert first.steps[2].path == "/resources/{resource_id}"
    assert first.steps[2].depends_on_step_ids == ()
    assert first.variables[0].name == "resource_id"
    assert first.variables[0].status is FlowDraftVariableStatus.UNCONFIRMED
    assert len(first.variables[0].candidate_sources) == 2
    assert "$.password" in first.steps[1].sensitive_fields
    assert "headers.authorization" in first.steps[1].sensitive_fields
    encoded = canonical_flow_draft_json_bytes(first)
    assert b"resource-42" not in encoded
    assert parse_flow_draft(encoded) == first

    schema_root = PROJECT_ROOT / "schemas" / "recording"
    assert json.loads((schema_root / "flow-draft-v1.schema.json").read_text()) == (
        FlowDraftV1.model_json_schema()
    )
    assert json.loads(
        (schema_root / "flow-draft-review-command-v1.schema.json").read_text()
    ) == flow_draft_review_command_schema()


def test_review_commands_are_immutable_and_compile_confirmed_flow() -> None:
    draft = build_draft()
    reviewer = FlowDraftReviewer()
    with pytest.raises(JiejianError) as nonadjacent:
        reviewer.apply(
            draft,
            MergeFlowDraftStepsV1(
                schema_version="1",
                operation="MERGE_ADJACENT_STEPS",
                left_step_id="step-000001",
                right_step_id="step-000003",
            ),
        )
    assert nonadjacent.value.code == "RECORD_DRAFT_NOT_ADJACENT"
    with pytest.raises(JiejianError) as reference:
        reviewer.apply(
            draft,
            DeleteFlowDraftStepV1(
                schema_version="1",
                operation="DELETE_STEP",
                step_id="step-000002",
            ),
        )
    assert reference.value.code == "RECORD_DRAFT_REFERENCE"

    renamed = reviewer.apply(
        draft,
        RenameFlowDraftStepV1(
            schema_version="1",
            operation="RENAME_STEP",
            step_id="step-000001",
            name="create resource",
        ),
    )
    merged = reviewer.apply(
        renamed,
        MergeFlowDraftStepsV1(
            schema_version="1",
            operation="MERGE_ADJACENT_STEPS",
            left_step_id="step-000001",
            right_step_id="step-000002",
        ),
    )
    deleted = reviewer.apply(
        merged,
        DeleteFlowDraftStepV1(
            schema_version="1",
            operation="DELETE_STEP",
            step_id="step-000004",
        ),
    )
    confirmed = reviewer.apply(
        deleted,
        ConfirmFlowDraftVariableV1(
            schema_version="1",
            operation="CONFIRM_VARIABLE_SOURCE",
            variable_name="resource_id",
            source_event_sequence=5,
            source_json_path="$.id",
        ),
    )

    assert draft.revision == 1
    assert (renamed.revision, merged.revision, deleted.revision, confirmed.revision) == (
        2,
        3,
        4,
        5,
    )
    assert confirmed.steps[0].name == "create resource"
    assert confirmed.variables[0].status is FlowDraftVariableStatus.CONFIRMED
    flow = reviewer.compile(confirmed)
    assert len(flow.steps) == 2
    assert flow.steps[1].path == "/resources/{resource_id}"
    assert flow.steps[1].depends_on_step_ids == ("step-000001",)
    assert flow.steps[1].variable_sources[0].json_path == "$.id"

    cycle_steps = tuple(
        step.model_copy(
            update={
                "depends_on_step_ids": (
                    ("step-000003",)
                    if step.id == "step-000002"
                    else ()
                    if step.id == "step-000003"
                    else step.depends_on_step_ids
                )
            }
        )
        for step in draft.steps
    )
    cycle_data = draft.model_dump(mode="python")
    cycle_data["steps"] = cycle_steps
    cycle_draft = FlowDraftV1.model_validate(cycle_data)
    with pytest.raises(JiejianError) as cycle:
        reviewer.apply(
            cycle_draft,
            ConfirmFlowDraftVariableV1(
                schema_version="1",
                operation="CONFIRM_VARIABLE_SOURCE",
                variable_name="resource_id",
                source_event_sequence=5,
                source_json_path="$.id",
            ),
        )
    assert cycle.value.code == "RECORD_DRAFT_CYCLE"
