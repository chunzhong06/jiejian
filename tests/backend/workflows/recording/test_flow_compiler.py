# 验证确认后的 Flow 编译与 binding 语义。

from __future__ import annotations
import json
from pathlib import Path
import pytest
from product.backend.core.errors import JiejianError
from product.backend.workflows.recording.processing import FlowDraftProcessor
from product.backend.workflows.recording.flow_compiler import FlowDraftCompiler
from product.backend.workflows.recording.review import FlowDraftReviewer
from product.protocols import (
    ConfirmFlowDraftResource,
    ConfirmFlowDraftTarget,
    DeleteFlowDraftStep,
    FlowDraft,
    FlowDraftResourceCandidate,
    FlowDraftStep,
    FlowDraftVariable,
    FlowDraftVariableSource,
    FlowDraftVariableStatus,
    MergeFlowDraftSteps,
    RecordingEvent,
    RecordingEventKind,
    RecordingHeader,
    RenameFlowDraftStep,
    canonical_flow_draft_json_bytes,
    flow_draft_review_command_schema,
    parse_flow_draft,
)
from product.protocols.web.workflow import ValueSlotConsumer, ValueSlotSource, WorkflowStepPurpose
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

def test_review_requires_explicit_target_and_recorded_resource_confirmation() -> None:
    draft = build_draft()
    reviewer = FlowDraftReviewer()
    compiler = FlowDraftCompiler()
    with pytest.raises(JiejianError):
        compiler.compile(draft)

    renamed = reviewer.apply(
        draft,
        RenameFlowDraftStep(
            schema_version="1",
            operation="RENAME_STEP",
            step_id="step-000001",
            name="准备资源",
        ),
    )
    merged = reviewer.apply(
        renamed,
        MergeFlowDraftSteps(
            schema_version="1",
            operation="MERGE_ADJACENT_STEPS",
            left_step_id="step-000001",
            right_step_id="step-000002",
        ),
    )
    reviewed = reviewer.apply(
        merged,
        DeleteFlowDraftStep(
            schema_version="1",
            operation="DELETE_STEP",
            step_id="step-000004",
        ),
    )
    reviewed = reviewer.apply(
        reviewed,
        ConfirmFlowDraftTarget(
            schema_version="1",
            operation="CONFIRM_TARGET_STEP",
            step_id="step-000003",
        ),
    )
    resource = next(
        item
        for item in reviewed.steps[1].resource_candidates
        if item.location == "path[1]"
    )
    ready = reviewer.apply(
        reviewed,
        ConfirmFlowDraftResource(
            schema_version="1",
            operation="CONFIRM_RESOURCE_SLOT",
            candidate_id=resource.candidate_id,
        ),
    )

    assert draft.revision == 1
    assert ready.revision == 6
    assert ready.variables == ()
    flow = compiler.compile(ready)
    assert flow.schema_version == "1"
    assert flow.action_candidate_id == ACTION_CANDIDATE_ID
    assert flow.target_step_id == "step-000003"
    assert tuple(step.purpose for step in flow.steps) == (WorkflowStepPurpose.TARGET,)
    assert flow.steps[0].request_template.path == "/resources/{case_resource_id}"
    resource_slots = tuple(
        slot
        for slot in flow.steps[0].request_template.input_slots
        if slot.source is ValueSlotSource.CASE_RESOURCE_ID
    )
    assert len(resource_slots) == 1
    assert json.loads(
        (
            PROJECT_ROOT
            / "product"
            / "protocols"
            / "schemas"
            / "recording"
            / "flow.schema.json"
        ).read_text(encoding="utf-8")
    ) == type(flow).model_json_schema()


def test_compile_drops_extractors_used_only_by_steps_after_target() -> None:
    setup_source = FlowDraftVariableSource(
        source_step_id="setup-step",
        source_event_sequence=2,
        json_path="$.session_id",
    )
    target_source = FlowDraftVariableSource(
        source_step_id="target-step",
        source_event_sequence=4,
        json_path="$.request_marker",
    )
    resource = FlowDraftResourceCandidate(
        candidate_id="resource-0123456789abcdef",
        consumer=ValueSlotConsumer.JSON_BODY,
        location="$.project_id",
        label="项目",
    )
    draft = FlowDraft(
        recording_id="rec_0123456789abcdef0123456789abcdef",
        flow_id="recorded-flow",
        action_candidate_id=ACTION_CANDIDATE_ID,
        revision=1,
        steps=(
            FlowDraftStep(
                id="setup-step",
                name="准备会话",
                method="GET",
                path="/session",
                expected_statuses=(200,),
                request_id="request_000001",
                source_event_sequences=(1, 2),
            ),
            FlowDraftStep(
                id="target-step",
                name="生成资料包",
                method="POST",
                path="/exports",
                json_body={
                    "project_id": "project-1",
                    "session_id": "{session_id}",
                },
                expected_statuses=(201,),
                request_id="request_000002",
                source_event_sequences=(3, 4),
                depends_on_step_ids=("setup-step",),
                resource_candidates=(resource,),
            ),
            FlowDraftStep(
                id="poll-step",
                name="查询资料包",
                method="GET",
                path="/exports/{request_marker}",
                expected_statuses=(200,),
                request_id="request_000003",
                source_event_sequences=(5, 6),
                depends_on_step_ids=("target-step",),
            ),
        ),
        variables=(
            FlowDraftVariable(
                name="session_id",
                placeholder="{session_id}",
                status=FlowDraftVariableStatus.CONFIRMED,
                candidate_sources=(setup_source,),
                confirmed_source=setup_source,
                consumer_step_ids=("target-step",),
            ),
            FlowDraftVariable(
                name="request_marker",
                placeholder="{request_marker}",
                status=FlowDraftVariableStatus.CONFIRMED,
                candidate_sources=(target_source,),
                confirmed_source=target_source,
                consumer_step_ids=("poll-step",),
            ),
        ),
        recommended_target_step_id="target-step",
        target_step_id="target-step",
        resource_candidate_id=resource.candidate_id,
    )

    flow = FlowDraftCompiler().compile(draft)

    assert tuple(step.id for step in flow.steps) == ("setup-step", "target-step")
    assert tuple(
        extractor.extractor_id
        for extractor in flow.steps[0].request_template.response_extractors
    ) == ("session_id",)
    assert flow.steps[1].request_template.response_extractors == ()
    assert tuple(source.name for source in flow.steps[1].variable_sources) == (
        "session_id",
    )
