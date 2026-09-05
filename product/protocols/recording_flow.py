# =============================================================================
# 已确认 Recording Flow 协议
#
# 定位
# 人工确认的录制步骤进入后续执行绑定前的稳定、不可变协议。
#
# 职责
# 表达动作步骤与变量来源｜校验唯一 TARGET｜约束主体和资源运行时 slot
#
# 边界
# 来源绑定正式业务动作版本与录制身份；步骤只保留运行时 slot，不携带秘密或观察/恢复实现。
#
# 调用链
# FlowDraftReviewer → Flow → Contract candidate / replay boundaries
# =============================================================================

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from product.backend.core.identifiers import PROJECT_ID_PATTERN, TEST_IDENTITY_ID_PATTERN
from product.backend.core.business_boundary import ACTION_ID_PATTERN
from product.protocols.web.workflow import (
    HttpOutcomeClassifier,
    HttpRequestTemplate,
    ValueSlotConsumer,
    ValueSlotSource,
    ValueType,
    WorkflowStepPurpose,
)


class RecordingFlowModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )



class FlowVariableSource(RecordingFlowModel):
    name: str = Field(pattern=PROJECT_ID_PATTERN)
    source_step_id: str = Field(pattern=PROJECT_ID_PATTERN)
    source_event_sequence: int = Field(ge=1)
    json_path: str = Field(min_length=1, max_length=512)
    consumer: ValueSlotConsumer = ValueSlotConsumer.JSON_BODY
    value_type: ValueType = ValueType.STRING
    max_length: int = Field(default=256, ge=1, le=4096)
    secret: bool = False


class FlowStep(RecordingFlowModel):
    id: str = Field(pattern=PROJECT_ID_PATTERN)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    purpose: WorkflowStepPurpose
    request_template: HttpRequestTemplate
    classifier: HttpOutcomeClassifier
    depends_on_step_ids: tuple[str, ...] = Field(default=(), max_length=128)
    variable_sources: tuple[FlowVariableSource, ...] = Field(default=(), max_length=128)
    sensitive_fields: tuple[str, ...] = Field(default=(), max_length=256)

    @model_validator(mode="after")
    def validate_metadata(self) -> FlowStep:
        if len(set(self.depends_on_step_ids)) != len(self.depends_on_step_ids):
            raise ValueError("flow step dependencies must be unique")
        if len({source.name for source in self.variable_sources}) != len(self.variable_sources):
            raise ValueError("flow variable sources must be unique")
        if len(set(self.sensitive_fields)) != len(self.sensitive_fields):
            raise ValueError("flow sensitive fields must be unique")
        return self


# 已确认、无环且不含秘密的录制流程；变量只能引用先前步骤。
class Flow(RecordingFlowModel):
    schema_version: Literal["2"] = "2"
    id: str = Field(pattern=PROJECT_ID_PATTERN)
    business_action_id: str = Field(pattern=ACTION_ID_PATTERN)
    action_revision: int = Field(ge=1)
    test_identity_id: str = Field(pattern=TEST_IDENTITY_ID_PATTERN)
    target_step_id: str = Field(pattern=PROJECT_ID_PATTERN)
    steps: tuple[FlowStep, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dependency_graph(self) -> Flow:
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


__all__ = ["Flow", "FlowStep", "FlowVariableSource"]
