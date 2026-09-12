# 严格保存已发布 v2 根文档的读取语义；禁止作为 current Worker 输入。
from __future__ import annotations
from product.protocols.flow_draft import _reject_cycles
import hashlib
import json
from typing import Literal
from pydantic import Field, model_validator, ValidationError
from product.backend.core.identifiers import PROJECT_ID_PATTERN, RECORDING_ID_PATTERN, TEST_IDENTITY_ID_PATTERN
from product.backend.core.business_boundary import ACTION_ID_PATTERN, EFFECT_ID_PATTERN
from product.backend.core.recording import RecordingPurpose
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols.recording import RecordingProtocolModel, RecordingSessionRef, RecordingBudget, WebTargetScope, _reject_inline_secret_material
from product.protocols.flow_draft import FlowDraftProtocolModel, FlowDraftStep, FlowDraftVariable, _reject_unredacted_sensitive_values, _strict_json, FLOW_DRAFT_MAX_BYTES
from product.protocols.recording_flow import RecordingFlowModel, FlowStep
from product.protocols.web.workflow import WorkflowStepPurpose, ValueSlotSource


class LegacyRecordingRunnerRequest(RecordingProtocolModel):
    schema_version: Literal["2"] = "2"
    recording_id: str = Field(pattern=RECORDING_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    business_action_id: str = Field(pattern=ACTION_ID_PATTERN)
    action_revision: int = Field(ge=1)
    test_identity_id: str = Field(pattern=TEST_IDENTITY_ID_PATTERN)
    preparation_source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    purpose: RecordingPurpose = RecordingPurpose.TARGET
    parent_recording_id: str | None = Field(default=None, pattern=RECORDING_ID_PATTERN)
    effect_id: str | None = Field(default=None, pattern=EFFECT_ID_PATTERN)
    created_at_us: int = Field(ge=0)
    target_scope: WebTargetScope
    sessions: tuple[RecordingSessionRef, ...] = Field(min_length=1, max_length=1)
    budget: RecordingBudget
    headless: bool = True
    trace_enabled: Literal[False] = False

    @property
    def subject_test_identity_id(self):
        return self.test_identity_id

    @property
    def resource_owner_test_identity_id(self):
        return self.test_identity_id

    @model_validator(mode="after")
    def validate_request_boundary(self) -> LegacyRecordingRunnerRequest:
        if (self.purpose is RecordingPurpose.TARGET) != (self.parent_recording_id is None):
            raise ValueError("supplemental recording request requires its target parent")
        if self.parent_recording_id == self.recording_id:
            raise ValueError("recording request cannot reference itself")
        if (self.purpose is RecordingPurpose.OBSERVATION) != (self.effect_id is not None):
            raise ValueError("observation request must bind a confirmed business effect")
        identity_ids = {session.test_identity_id for session in self.sessions}
        if identity_ids != {self.test_identity_id}:
            raise ValueError("recording source identity must match its single session")
        session_refs = {session.session_ref for session in self.sessions}
        if len(identity_ids) != len(self.sessions):
            raise ValueError("recording identity IDs must be unique")
        if len(session_refs) != len(self.sessions):
            raise ValueError("recording session references must be unique")
        if len(self.sessions) > self.budget.max_contexts:
            raise ValueError("recording sessions exceed context budget")
        if any(session.expires_at_us <= self.created_at_us for session in self.sessions):
            raise ValueError("recording session reference must be short-lived and active")
        _reject_inline_secret_material(self.model_dump(mode="python"))
        return self


class LegacyFlowDraft(FlowDraftProtocolModel):
    schema_version: Literal["2"] = "2"
    recording_id: str = Field(pattern=RECORDING_ID_PATTERN)
    flow_id: str = Field(pattern=PROJECT_ID_PATTERN)
    business_action_id: str = Field(pattern=ACTION_ID_PATTERN)
    action_revision: int = Field(ge=1)
    test_identity_id: str = Field(pattern=TEST_IDENTITY_ID_PATTERN)
    purpose: RecordingPurpose = RecordingPurpose.TARGET
    parent_recording_id: str | None = Field(default=None, pattern=RECORDING_ID_PATTERN)
    effect_id: str | None = Field(default=None, pattern=EFFECT_ID_PATTERN)
    revision: int = Field(ge=1)
    steps: tuple[FlowDraftStep, ...] = Field(min_length=1, max_length=2_000)
    variables: tuple[FlowDraftVariable, ...] = Field(default=(), max_length=2_000)
    recommended_target_step_id: str | None = Field(
        default=None,
        pattern=PROJECT_ID_PATTERN,
    )
    target_step_id: str | None = Field(default=None, pattern=PROJECT_ID_PATTERN)
    resource_candidate_id: str | None = Field(
        default=None,
        pattern=r"^resource-[0-9a-f]{16}$",
    )

    @model_validator(mode="after")
    def validate_draft_graph(self) -> LegacyFlowDraft:
        if (self.purpose is RecordingPurpose.TARGET) != (self.parent_recording_id is None):
            raise ValueError("supplemental draft requires its target recording parent")
        if self.parent_recording_id == self.recording_id:
            raise ValueError("draft cannot reference itself as parent")
        if (self.purpose is RecordingPurpose.OBSERVATION) != (self.effect_id is not None):
            raise ValueError("observation draft must bind a confirmed business effect")
        step_ids = tuple(step.id for step in self.steps)
        if len(set(step_ids)) != len(step_ids):
            raise ValueError("flow draft step IDs must be unique")
        known = set(step_ids)
        request_ids = tuple(
            step.request_id for step in self.steps if step.request_id is not None
        )
        if len(set(request_ids)) != len(request_ids):
            raise ValueError("flow draft causal IDs must be unique")
        graph = {step.id: set(step.depends_on_step_ids) for step in self.steps}
        if any(
            dependency not in known or dependency == step_id
            for step_id, dependencies in graph.items()
            for dependency in dependencies
        ):
            raise ValueError("flow draft dependency reference is invalid")
        variable_names = {variable.name for variable in self.variables}
        if len(variable_names) != len(self.variables):
            raise ValueError("flow draft variable names must be unique")
        if any(
            source.source_step_id not in known
            for variable in self.variables
            for source in variable.candidate_sources
        ) or any(
            consumer not in known
            for variable in self.variables
            for consumer in variable.consumer_step_ids
        ):
            raise ValueError("flow draft variable reference is invalid")
        if self.recommended_target_step_id is not None:
            recommended = next(
                (step for step in self.steps if step.id == self.recommended_target_step_id),
                None,
            )
            if recommended is None or recommended.method is None:
                raise ValueError("flow draft target recommendation is invalid")
        if self.target_step_id is None:
            if self.resource_candidate_id is not None:
                raise ValueError("flow draft resource cannot precede target confirmation")
        else:
            target = next((step for step in self.steps if step.id == self.target_step_id), None)
            if target is None or target.method is None:
                raise ValueError("flow draft confirmed target is invalid")
            candidate_ids = {item.candidate_id for item in target.resource_candidates}
            if (
                self.resource_candidate_id is not None
                and self.resource_candidate_id not in candidate_ids
            ):
                raise ValueError("flow draft resource candidate does not belong to target")
        _reject_cycles(graph)
        return self


class LegacyFlow(RecordingFlowModel):
    schema_version: Literal["2"] = "2"
    id: str = Field(pattern=PROJECT_ID_PATTERN)
    business_action_id: str = Field(pattern=ACTION_ID_PATTERN)
    action_revision: int = Field(ge=1)
    test_identity_id: str = Field(pattern=TEST_IDENTITY_ID_PATTERN)
    target_step_id: str = Field(pattern=PROJECT_ID_PATTERN)
    steps: tuple[FlowStep, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dependency_graph(self) -> LegacyFlow:
        step_ids = tuple(step.id for step in self.steps)
        if len(set(step_ids)) != len(step_ids):
            raise ValueError("flow step IDs must be unique")
        known = set(step_ids)
        targets = tuple(step for step in self.steps if step.purpose is WorkflowStepPurpose.TARGET)
        if len(targets) != 1 or targets[0].id != self.target_step_id:
            raise ValueError("flow must bind exactly one declared target step")
        if any(step.purpose is WorkflowStepPurpose.CLEANUP for step in self.steps):
            raise ValueError("recorded business flow may contain only setup and target steps")
        resource_slots = tuple(
            (step.id, slot)
            for step in self.steps
            for slot in step.request_template.input_slots
            if slot.source is ValueSlotSource.CASE_RESOURCE_ID
        )
        if len(resource_slots) != 1 or resource_slots[0][0] != self.target_step_id:
            raise ValueError("flow target must bind exactly one case resource slot")
        graph = {step.id: set(step.depends_on_step_ids) for step in self.steps}
        if any(
            dependency not in known or dependency == step_id
            for step_id, dependencies in graph.items()
            for dependency in dependencies
        ):
            raise ValueError("flow step dependency reference is invalid")
        if any(
            source.source_step_id not in known or source.source_step_id not in graph[step.id]
            for step in self.steps
            for source in step.variable_sources
        ):
            raise ValueError("flow variable source must be a declared dependency")
        step_map = {step.id: step for step in self.steps}
        for step in self.steps:
            slot_map = {slot.slot_id: slot for slot in step.request_template.input_slots}
            for source in step.variable_sources:
                slot = slot_map.get(source.name)
                producer = step_map[source.source_step_id]
                extractor_ids = {item.extractor_id for item in producer.request_template.response_extractors}
                if (
                    slot is None
                    or slot.producer_step_id != source.source_step_id
                    or slot.consumer_step_id != step.id
                    or slot.source_path != source.json_path
                    or source.name not in extractor_ids
                ):
                    raise ValueError("flow variable source must match the compiled slot and producer extractor")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(step_id: str) -> None:
            if step_id in visiting:
                raise ValueError("flow dependencies must be acyclic")
            if step_id in visited:
                return
            visiting.add(step_id)
            for dependency in graph[step_id]:
                visit(dependency)
            visiting.remove(step_id)
            visited.add(step_id)

        for step_id in step_ids:
            visit(step_id)
        return self


def read_legacy_document(raw: bytes, kind: str, *, expected_hash: str | None = None):
    """先验原始 v2 canonical/hash，再返回内存 v3 投影和原始来源；不重写历史字节。"""
    from product.protocols.flow_draft import FlowDraft
    from product.protocols.recording_flow import Flow
    from product.protocols.recording import RECORDING_REQUEST_MAX_BYTES
    maximum = RECORDING_REQUEST_MAX_BYTES if kind == "request" else FLOW_DRAFT_MAX_BYTES
    try:
        payload = _strict_json(raw, maximum, ())
        if not isinstance(payload, dict) or payload.get("schema_version") != "2":
            raise ValueError("legacy version")
        model = {"request": LegacyRecordingRunnerRequest, "draft": LegacyFlowDraft, "flow": LegacyFlow}[kind]
        document = model.model_validate_json(raw, strict=True)
        canonical = json.dumps(document.model_dump(mode="json"), ensure_ascii=False, sort_keys=True,
                               separators=(",", ":"), allow_nan=False).encode("utf-8")
        if canonical != raw or expected_hash is not None and hashlib.sha256(raw).hexdigest() != expected_hash:
            raise ValueError("legacy content identity")
        if kind == "request":
            return document
        projected = document.model_dump(mode="json")
        identity = projected.pop("test_identity_id")
        projected.update(schema_version="3", subject_test_identity_id=identity, resource_owner_test_identity_id=identity)
        target = FlowDraft if kind == "draft" else Flow
        return target.model_validate_json(json.dumps(projected, ensure_ascii=False), strict=True)
    except (ValueError, KeyError, TypeError):
        raise JiejianError(ErrorCode.RECORD_PROTOCOL_INVALID, "历史录制协议无效") from None
