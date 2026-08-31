# Web Workflow、基线与重置绑定模型。

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated, Literal, TypeAlias

from pydantic import Field, model_validator
from product.protocols.execution import ProtocolModel
from .request import (
    CASE_SUBJECT_IDENTITY,
    EmptyBody,
    FormUrlEncodedBody,
    HTTP_LITERAL_MAX_LENGTH,
    HTTP_SLOT_MAX_LENGTH,
    HTTP_TEMPLATE_MAX_BYTES,
    HTTP_TEMPLATE_MAX_DEPTH,
    HTTP_TEMPLATE_MAX_FIELDS,
    _IDENTIFIER,
    _PATH,
    HttpParameter,
    HttpBodyKind,
    HttpRequestTemplate,
    JsonBody,
    MultipartBody,
    MultipartPart,
    ValueSlot,
    ValueSlotConsumer,
    ValueSlotSource,
    ValueType,
)
from .response import (
    HttpOutcome,
    HttpOutcomeClassifier,
    HttpPredicate,
    HttpPredicateKind,
    ResponseExtractor,
    ResponseExtractorKind,
)

# HttpRequestTemplate 在 request.py 中先声明了对响应提取器的前向引用；
# 在请求/响应模块均完成装载后重建，保持原有严格模型而不引入旧兼容模块。
HttpRequestTemplate.model_rebuild(_types_namespace={"ResponseExtractor": ResponseExtractor})

class WorkflowStepPurpose(StrEnum):
    SETUP = "SETUP"
    TARGET = "TARGET"
    CLEANUP = "CLEANUP"


class WorkflowFailurePolicy(StrEnum):
    INCONCLUSIVE = "INCONCLUSIVE"
    STOP = "STOP"


class ResetStrategyKind(StrEnum):
    RESET_ENDPOINT = "RESET_ENDPOINT"
    UNIQUE_RESOURCE_WORKFLOW = "UNIQUE_RESOURCE_WORKFLOW"
    SNAPSHOT_PROVIDER = "SNAPSHOT_PROVIDER"
    NOT_REQUIRED = "NOT_REQUIRED"


class BaselineIntegrityMode(StrEnum):
    EXACT_RESTORE = "EXACT_RESTORE"
    NORMALIZED_EQUIVALENCE = "NORMALIZED_EQUIVALENCE"


class LogicalResourceSlot(ProtocolModel):
    slot_id: str = Field(pattern=_IDENTIFIER)
    logical_resource_handle: str = Field(pattern=_IDENTIFIER)
    value_type: ValueType = ValueType.STRING
    max_length: int = Field(default=256, ge=1, le=HTTP_SLOT_MAX_LENGTH)
    secret: Literal[False] = False


class BaselineProjection(ProtocolModel):
    projection_id: str = Field(pattern=_IDENTIFIER)
    logical_resource_handle: str = Field(pattern=_IDENTIFIER)
    normalization_version: str = Field(pattern=r"^[0-9]+(?:\.[0-9]+){0,3}$")
    projection_version: str = Field(pattern=r"^[0-9]+(?:\.[0-9]+){0,3}$")
    required: bool = True
    expected_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    integrity_mode: BaselineIntegrityMode = BaselineIntegrityMode.EXACT_RESTORE


class ResetEndpointStrategy(ProtocolModel):
    kind: Literal[ResetStrategyKind.RESET_ENDPOINT] = ResetStrategyKind.RESET_ENDPOINT
    path: str = Field(pattern=_PATH)


class UniqueResourceWorkflowResetStrategy(ProtocolModel):
    kind: Literal[ResetStrategyKind.UNIQUE_RESOURCE_WORKFLOW] = ResetStrategyKind.UNIQUE_RESOURCE_WORKFLOW
    workflow_id: str = Field(pattern=_IDENTIFIER)


class SnapshotProviderResetStrategy(ProtocolModel):
    kind: Literal[ResetStrategyKind.SNAPSHOT_PROVIDER] = ResetStrategyKind.SNAPSHOT_PROVIDER
    provider_ref: str = Field(pattern=r"^[a-z][a-z0-9_.:-]{0,127}$")


class ResetNotRequiredStrategy(ProtocolModel):
    kind: Literal[ResetStrategyKind.NOT_REQUIRED] = ResetStrategyKind.NOT_REQUIRED


ResetStrategy: TypeAlias = Annotated[
    ResetEndpointStrategy
    | UniqueResourceWorkflowResetStrategy
    | SnapshotProviderResetStrategy
    | ResetNotRequiredStrategy,
    Field(discriminator="kind"),
]


class BaselineFingerprint(ProtocolModel):
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    logical_resource_handle: str = Field(pattern=_IDENTIFIER)
    normalized_resource_state: str = Field(min_length=1, max_length=4096)
    workflow_state: str = Field(min_length=1, max_length=1024)
    relationship_projection: str = Field(min_length=1, max_length=4096)
    effect_projection: str = Field(min_length=1, max_length=4096)
    normalization_version: str = Field(pattern=r"^[0-9]+(?:\.[0-9]+){0,3}$")
    projection_version: str = Field(pattern=r"^[0-9]+(?:\.[0-9]+){0,3}$")


class BaselineIntegrity(ProtocolModel):
    mode: BaselineIntegrityMode
    expected_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    observed_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    valid: bool
    reason_codes: tuple[str, ...] = Field(default=(), max_length=16)


class HttpWorkflowStep(ProtocolModel):
    id: str = Field(pattern=_IDENTIFIER)
    purpose: WorkflowStepPurpose
    identity_id: str = Field(min_length=1, max_length=64)
    request_template: HttpRequestTemplate
    classifier: HttpOutcomeClassifier = Field(default_factory=HttpOutcomeClassifier)
    input_slots: tuple[ValueSlot, ...] = Field(default=(), max_length=HTTP_TEMPLATE_MAX_FIELDS)
    output_extractors: tuple[ResponseExtractor, ...] = Field(default=(), max_length=HTTP_TEMPLATE_MAX_FIELDS)
    depends_on_step_ids: tuple[str, ...] = Field(default=(), max_length=HTTP_TEMPLATE_MAX_FIELDS)
    failure_policy: WorkflowFailurePolicy = WorkflowFailurePolicy.INCONCLUSIVE

    @model_validator(mode="after")
    def validate_step(self) -> HttpWorkflowStep:
        if self.identity_id != CASE_SUBJECT_IDENTITY and re.fullmatch(_IDENTIFIER, self.identity_id) is None:
            raise ValueError("workflow step identity must be CASE_SUBJECT or a declared identity ID")
        if len(set(self.depends_on_step_ids)) != len(self.depends_on_step_ids):
            raise ValueError("workflow step dependencies must be unique")
        template_slots = {item.slot_id: item for item in self.request_template.input_slots}
        step_slots = {item.slot_id: item for item in self.input_slots}
        if step_slots and template_slots and step_slots != template_slots:
            raise ValueError("step input slots must match request template slots")
        if not template_slots and step_slots:
            object.__setattr__(self, "request_template", self.request_template.model_copy(update={"input_slots": self.input_slots}))
        elif template_slots:
            object.__setattr__(self, "input_slots", tuple(template_slots.values()))
        template_extractors = {item.extractor_id: item for item in self.request_template.response_extractors}
        step_extractors = {item.extractor_id: item for item in self.output_extractors}
        if step_extractors and template_extractors and step_extractors != template_extractors:
            raise ValueError("step output extractors must match request template extractors")
        if not template_extractors and step_extractors:
            object.__setattr__(self, "request_template", self.request_template.model_copy(update={"response_extractors": self.output_extractors}))
        elif template_extractors:
            object.__setattr__(self, "output_extractors", tuple(template_extractors.values()))
        return self


class HttpWorkflowBinding(ProtocolModel):
    workflow_id: str = Field(pattern=_IDENTIFIER)
    source_flow_id: str = Field(pattern=_IDENTIFIER)
    action_id: str = Field(pattern=_IDENTIFIER)
    steps: tuple[HttpWorkflowStep, ...] = Field(min_length=1, max_length=256)
    target_step_id: str = Field(pattern=_IDENTIFIER)
    logical_resource_slots: tuple[LogicalResourceSlot, ...] = Field(default=(), max_length=128)
    baseline_projections: tuple[BaselineProjection, ...] = Field(default=(), max_length=128)
    reset_strategy: ResetStrategy = Field(default_factory=lambda: ResetEndpointStrategy(path="/reset"), discriminator="kind")
    workflow_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_workflow(self) -> HttpWorkflowBinding:
        step_ids = tuple(step.id for step in self.steps)
        if len(set(step_ids)) != len(step_ids) or self.target_step_id not in set(step_ids):
            raise ValueError("workflow step IDs and target_step_id are inconsistent")
        targets = [step for step in self.steps if step.purpose is WorkflowStepPurpose.TARGET]
        if len(targets) != 1 or targets[0].id != self.target_step_id:
            raise ValueError("workflow must contain exactly one TARGET step")
        if len({slot.slot_id for slot in self.logical_resource_slots}) != len(self.logical_resource_slots):
            raise ValueError("logical resource slots must be unique")
        if len({item.projection_id for item in self.baseline_projections}) != len(self.baseline_projections):
            raise ValueError("baseline projections must be unique")
        if self.reset_strategy.kind is ResetStrategyKind.NOT_REQUIRED:
            if any(step.purpose is WorkflowStepPurpose.CLEANUP for step in self.steps):
                raise ValueError("NOT_REQUIRED reset strategy cannot contain cleanup steps")
            if any(step.request_template.method not in {"GET", "HEAD"} for step in self.steps):
                raise ValueError("NOT_REQUIRED reset strategy only supports read-only workflow steps")
        graph = {step.id: set(step.depends_on_step_ids) for step in self.steps}
        if any(dependency not in graph or dependency == step_id for step_id, dependencies in graph.items() for dependency in dependencies):
            raise ValueError("workflow dependency reference is invalid")
        visiting: set[str] = set()
        visited: set[str] = set()
        def visit(step_id: str) -> None:
            if step_id in visiting:
                raise ValueError("workflow dependencies must be acyclic")
            if step_id in visited:
                return
            visiting.add(step_id)
            for dependency in graph[step_id]:
                visit(dependency)
            visiting.remove(step_id)
            visited.add(step_id)
        for step_id in step_ids:
            visit(step_id)
        for step in self.steps:
            for slot in step.input_slots:
                if slot.producer_step_id is not None:
                    if slot.producer_step_id not in graph or slot.producer_step_id not in _transitive_dependencies(graph, step.id):
                        raise ValueError("slot producer must be a declared prior dependency")
                    if slot.secret and graph[slot.producer_step_id] is not None:
                        producer = next(item for item in self.steps if item.id == slot.producer_step_id)
                        if producer.identity_id != step.identity_id:
                            raise ValueError("secret slots cannot cross identities")
        fingerprint = _workflow_fingerprint(self)
        if self.workflow_fingerprint is not None and self.workflow_fingerprint != fingerprint:
            raise ValueError("workflow fingerprint does not match frozen binding")
        object.__setattr__(self, "workflow_fingerprint", fingerprint)
        return self


def _transitive_dependencies(graph: Mapping[str, set[str]], step_id: str) -> set[str]:
    found: set[str] = set()
    pending = list(graph[step_id])
    while pending:
        dependency = pending.pop()
        if dependency in found:
            continue
        found.add(dependency)
        pending.extend(graph[dependency])
    return found


def _workflow_fingerprint(binding: HttpWorkflowBinding) -> str:
    payload = binding.model_dump(mode="json", exclude={"workflow_fingerprint"})
    # 请求模板的根版本描述协议格式，不参与业务工作流语义指纹，避免版本迁移改变既有绑定事实。
    for step in payload.get("steps", ()):
        if isinstance(step, dict) and isinstance(step.get("request_template"), dict):
            step["request_template"].pop("schema_version", None)
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def build_baseline_fingerprint(
    *,
    logical_resource_handle: str,
    normalized_resource_state: str,
    workflow_state: str,
    relationship_projection: str,
    effect_projection: str,
    normalization_version: str,
    projection_version: str,
) -> BaselineFingerprint:
    payload = {
        "logical_resource_handle": logical_resource_handle,
        "normalized_resource_state": normalized_resource_state,
        "workflow_state": workflow_state,
        "relationship_projection": relationship_projection,
        "effect_projection": effect_projection,
        "normalization_version": normalization_version,
        "projection_version": projection_version,
    }
    fingerprint = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return BaselineFingerprint(fingerprint=fingerprint, **payload)
