# 当前检查的独立冻结配置：只保存严格叶模型、受控引用与有限预算，不依赖 backend。
from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated, Literal

from pydantic import Field, model_validator
from product.protocols.codec import encode_json, decode_document
from product.protocols.preparation.proof_sources import FrozenProofSource, proof_fingerprint
from product.protocols.web.response import ResponseExtractor

from product.protocols.checks.execution_request import ActorId, EffectId, Hash, IdentityId, LogicalId, WireModel, content_hash
from product.protocols.observer.config import ObserverSpec
from product.protocols.checks.identity import CheckIdentity, CheckIdentityVerification
from product.protocols.web.identity import BearerIdentityBinding, PreparedCookieSessionIdentityBinding
from product.protocols.web.request import HttpBodyKind, HttpRequestTemplate, ValueSlotConsumer, ValueSlotSource
from product.protocols.web.response import HttpOutcomeClassifier
from product.protocols.web.target import WebTargetScope
from product.protocols.runtime.runtime_identity import ControlledRuntimeReference
from product.protocols.runtime.node_runtime import NodeRuntimeReference

CHECK_DOCUMENT_MAX_BYTES = 1_048_576
ActionId = Annotated[str, Field(pattern=r"^bac_[0-9a-f]{32}$")]
SafeLabel = Annotated[str, Field(min_length=1, max_length=256)]
_SECRET = re.compile(r"(?:\bBearer\s+\S+|\b(?:authorization|cookie|credential|password|passwd|secret|token|api[_-]?key)\s*[:=]\s*\S+)", re.I)


class CheckBudget(WireModel):
    max_requests: int = Field(ge=1, le=500)
    request_timeout_us: int = Field(ge=1, le=30_000_000)
    max_duration_us: int = Field(ge=1, le=3_600_000_000)
    max_response_bytes: int = Field(ge=1, le=4_194_304)
    max_cases: int = Field(ge=1, le=8192)
    max_parallel_cases: Literal[1] = 1
    recovery_reserve_requests: int = Field(ge=0, le=500)

    @model_validator(mode="after")
    def validate_reserve(self):
        if self.recovery_reserve_requests >= self.max_requests:
            raise ValueError("recovery reserve consumes the entire request budget")
        return self

    def fingerprint(self) -> str:
        return content_hash("CheckBudget", self.model_dump(mode="json"))




class CheckFlowStep(WireModel):
    step_id: LogicalId
    purpose: Literal["SETUP", "TARGET"]
    request: HttpRequestTemplate
    classifier: HttpOutcomeClassifier
    depends_on_step_ids: tuple[LogicalId, ...] = Field(max_length=128)


class CheckAuxiliarySource(WireModel):
    observer_id: LogicalId
    descriptor_fingerprint: Hash
    observation_identity_id: IdentityId
    level: Literal["SUPPORTING", "DIAGNOSIS_REQUIRED"]
    source_label: SafeLabel
    source_location: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_./:-]{0,255}$")]
    trace_namespace: LogicalId | None = None

    @model_validator(mode="after")
    def validate_location(self):
        if ".." in self.source_location.split("/") or re.match(r"^[A-Za-z]:", self.source_location):
            raise ValueError("auxiliary source location escaped")
        return self


class CheckProofConfig(WireModel):
    effect_id: EffectId
    business_label: SafeLabel
    resource_concept: SafeLabel
    effect_kind: Literal["STATE_MUTATION", "DATA_DISCLOSURE", "OBJECT_CREATION", "EXTERNAL_DISPATCH", "RESTRICTED_FUNCTION_INVOCATION", "CREDENTIAL_ACCESS", "FILE_CONTENT_DELIVERY"]
    expected_state: str | None = Field(default=None, min_length=1, max_length=512)
    protected_projection: tuple[Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")], ...] = Field(default=(), max_length=64)
    binding_fingerprint: Hash
    rule: Literal["HTTP_RESOURCE_PRESENCE", "REGISTERED_EFFECT", "RECORDED_SUPPORT"]
    observation_identity_id: IdentityId
    request: HttpRequestTemplate | None = None
    observer_id: LogicalId | None = None
    descriptor_fingerprint: Hash | None = None
    source_label: SafeLabel
    # 仅保留受控相对位置或 provider 逻辑名，不输出绝对文件路径。
    source_location: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_./:-]{0,255}$")]
    exclusive_resource_window: bool = False
    auxiliary_sources: tuple[CheckAuxiliarySource, ...] = Field(default=(), max_length=5)

    @model_validator(mode="after")
    def validate_source(self):
        source_ids = [source.observer_id for source in self.auxiliary_sources]
        if len(set(source_ids)) != len(source_ids) or self.observer_id in source_ids:
            raise ValueError("duplicate proof source")
        if self.rule == "REGISTERED_EFFECT":
            if self.request is not None or self.observer_id is None or self.descriptor_fingerprint is None:
                raise ValueError("registered proof requires a frozen observer")
        elif self.request is None or self.request.method != "GET" or self.observer_id is not None:
            raise ValueError("recorded proof requires a readonly request")
        if ".." in self.source_location.split("/") or re.match(r"^[A-Za-z]:", self.source_location):
            raise ValueError("source location must not escape the controlled source")
        if self.rule == "HTTP_RESOURCE_PRESENCE":
            slots = self.request.input_slots
            if self.effect_kind != "OBJECT_CREATION" or len(slots) != 1 or slots[0].source is not ValueSlotSource.CASE_RESOURCE_ID:
                raise ValueError("resource presence requires one exact case resource slot")
            slot = slots[0]
            marker = "{" + slot.slot_id + "}"
            path_matches = self.request.path.split("/").count(marker)
            query_matches = sum(item.slot_id == slot.slot_id for item in self.request.query)
            if self.request.body.kind is not HttpBodyKind.EMPTY or path_matches + query_matches != 1:
                raise ValueError("resource presence requires a whole path segment or query value")
            if (slot.consumer is ValueSlotConsumer.PATH and path_matches != 1) or (
                slot.consumer is ValueSlotConsumer.QUERY and query_matches != 1
            ) or slot.consumer not in (ValueSlotConsumer.PATH, ValueSlotConsumer.QUERY):
                raise ValueError("resource presence slot consumer mismatch")
        if bool(self.protected_projection) != (self.effect_kind == "DATA_DISCLOSURE"):
            raise ValueError("protected projection belongs only to disclosure effects")
        return self


class CheckRecoveryConfig(WireModel):
    binding_fingerprint: Hash
    source_subject_identity_id: IdentityId
    request: HttpRequestTemplate
    projection_fields: tuple[Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")], ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def validate_resource_binding(self):
        slots = [slot for slot in self.request.input_slots if slot.source is ValueSlotSource.CASE_RESOURCE_ID]
        if len(slots) != 1:
            raise ValueError("recovery requires one exact case resource slot")
        slot = slots[0]
        marker = "{" + slot.slot_id + "}"
        if slot.consumer is ValueSlotConsumer.PATH:
            used = self.request.path.split("/").count(marker) == 1
        elif slot.consumer is ValueSlotConsumer.QUERY:
            used = sum(item.slot_id == slot.slot_id for item in self.request.query) == 1
        else:
            body = self.request.body.model_dump(mode="json")
            # JSON 槽与表单槽均为结构引用；不按字符串包含或固定资源字面量猜测关联。
            def references(value):
                if isinstance(value, dict):
                    return int(value.get("$slot") == slot.slot_id or value.get("slot_id") == slot.slot_id) + sum(
                        references(child) for child in value.values())
                return sum(references(child) for child in value) if isinstance(value, list) else 0
            used = slot.consumer in (ValueSlotConsumer.JSON_BODY, ValueSlotConsumer.FORM_FIELD,
                ValueSlotConsumer.MULTIPART_FIELD) and references(body) == 1
        if not used:
            raise ValueError("recovery resource slot must address the exact case resource")
        return self


class CheckActionConfig(WireModel):
    action_id: ActionId
    action_revision: int = Field(ge=1)
    action_semantic_fingerprint: Hash
    display_name: SafeLabel
    primary_resource_concept: SafeLabel
    state_changing: bool
    flow_id: LogicalId
    flow_sha256: Hash
    execution_binding_fingerprint: Hash
    steps: tuple[CheckFlowStep, ...] = Field(min_length=1, max_length=128)
    proofs: tuple[CheckProofConfig, ...] = Field(min_length=1, max_length=48)
    recovery: CheckRecoveryConfig | None = None
    created_resource: ResponseExtractor | None = None

    @model_validator(mode="after")
    def validate_flow(self):
        # 输出对象必须明确冻结提取方式和独立创建来源。
        if (any(source.extractor_id == "created_resource_id" for step in self.steps for source in step.request.response_extractors)
                and not any(slot.source is ValueSlotSource.CASE_RESOURCE_ID for step in self.steps for slot in step.request.input_slots)
                and getattr(self, 'created_resource', None) is None):
            raise ValueError("CREATED_RESOURCE_CONTRACT_REQUIRED")
        by_id = {step.step_id: step for step in self.steps}
        if len(by_id) != len(self.steps) or sum(step.purpose == "TARGET" for step in self.steps) != 1:
            raise ValueError("flow requires unique steps and exactly one target")
        visited: set[str] = set()
        for step in self.steps:
            if len(set(step.depends_on_step_ids)) != len(step.depends_on_step_ids) or not set(step.depends_on_step_ids) <= visited:
                raise ValueError("flow must be in a valid dependency order")
            for slot in step.request.input_slots:
                if slot.producer_step_id is not None and slot.producer_step_id not in visited:
                    raise ValueError("flow slot must refer to a preceding producer")
            visited.add(step.step_id)
        if self.steps[-1].purpose != "TARGET":
            raise ValueError("all setup must precede the unique target")
        if self.state_changing and self.recovery is None:
            raise ValueError("state changing flow requires confirmed recovery")
        if len({proof.binding_fingerprint for proof in self.proofs}) != len(self.proofs):
            raise ValueError("duplicate action proof binding")
        return self


    @model_validator(mode='after')
    def output_resource(self):
        if self.created_resource is None:
            return self
        target=next(step for step in self.steps if step.purpose=='TARGET')
        if (not self.state_changing or self.recovery is None
                or self.created_resource not in target.request.response_extractors
                or self.created_resource.extractor_id!='created_resource_id'
                or self.created_resource.kind not in {'JSON_PATH','LOCATION'} or self.created_resource.secret
                or any(slot.source is ValueSlotSource.CASE_RESOURCE_ID for step in self.steps for slot in step.request.input_slots)
                or any(proof.effect_kind!='OBJECT_CREATION' or proof.rule!='REGISTERED_EFFECT' or proof.auxiliary_sources for proof in self.proofs)):
            raise ValueError('creation flow requires exact output, creation proof and recovery')
        return self


def async_completion_candidates(action: CheckActionConfig, observers: dict[str, ObserverSpec],
                                verified_identity_ids: set[str]) -> dict[str, CheckAuxiliarySource]:
    """只收集同动作正式 proof 的终态辅助来源，重复来源必须具有同一身份和描述引用。"""
    candidates, seen = {}, {}
    for proof in action.proofs:
        if proof.rule != "REGISTERED_EFFECT":
            continue
        for source in proof.auxiliary_sources:
            spec = observers.get(source.observer_id)
            if spec is None or spec.observer_type != "ASYNC_TASK_STATUS" or "EVENTUAL" not in spec.phases:
                continue
            facts = (source.descriptor_fingerprint, source.observation_identity_id, spec)
            if source.observer_id in seen and seen[source.observer_id] != facts:
                raise ValueError("ASYNC_COMPLETION_CONFLICT")
            seen[source.observer_id] = facts
            if source.observation_identity_id in verified_identity_ids:
                candidates[source.observer_id] = source
    return candidates


class ExternalWebRuntime(WireModel):
    kind: Literal["EXTERNAL_WEB"] = "EXTERNAL_WEB"


class PythonRuntime(WireModel):
    kind: Literal["MANAGED_PYTHON"] = "MANAGED_PYTHON"
    reference: ControlledRuntimeReference


class NodeRuntime(WireModel):
    kind: Literal["MANAGED_NODE"] = "MANAGED_NODE"
    reference: NodeRuntimeReference


RuntimeSpec = Annotated[ExternalWebRuntime | PythonRuntime | NodeRuntime, Field(discriminator="kind")]


class CheckRuntimeCorrespondence(WireModel):
    runtime: Annotated[PythonRuntime | NodeRuntime, Field(discriminator="kind")]
    before: Literal["MATCHED", "UNCONFIRMED"]
    after: Literal["MATCHED", "UNCONFIRMED"]


class CheckRuntimeBundle(WireModel):
    document_type: Literal["jiejian.check-runtime"] = "jiejian.check-runtime"
    runtime: RuntimeSpec = Field(default_factory=ExternalWebRuntime)
    proof_sources: tuple[FrozenProofSource, ...] = Field(default=(), max_length=256)
    schema_version: Literal["1"] = "1"
    project_id: LogicalId
    source_fingerprint: Hash
    target_type: Literal["WEB"] = "WEB"
    target: WebTargetScope
    budget: CheckBudget
    identities: tuple[CheckIdentity, ...] = Field(min_length=1, max_length=4096)
    actions: tuple[CheckActionConfig, ...] = Field(min_length=1, max_length=512)
    observers: tuple[ObserverSpec, ...] = Field(default=(), max_length=256)

    @model_validator(mode="after")
    def validate_references_and_limits(self):
        identities = {item.identity_id for item in self.identities}
        observers = {item.observer_id for item in self.observers}
        observer_specs = {item.observer_id: item for item in self.observers}
        trace_namespaces = {}
        if len(identities) != len(self.identities) or len(observers) != len(self.observers):
            raise ValueError("duplicate runtime identity or observer")
        if len({action.action_id for action in self.actions}) != len(self.actions):
            raise ValueError("duplicate runtime action")
        if self.target.max_requests > self.budget.max_requests or self.target.max_response_bytes > self.budget.max_response_bytes:
            raise ValueError("target budget exceeds the frozen check budget")
        if self.target.timeout_seconds * 1_000_000 > self.budget.request_timeout_us:
            raise ValueError("target timeout exceeds the frozen check budget")
        for action in self.actions:
            completion_bindings = tuple(step.classifier.completion_binding for step in action.steps
                                        if step.classifier.completion_binding is not None)
            if completion_bindings:
                candidates = async_completion_candidates(action, observer_specs,
                    {item.identity_id for item in self.identities if item.verification is not None})
                if any(binding not in candidates for binding in completion_bindings):
                    raise ValueError("ASYNC_COMPLETION_BINDING_INVALID")
            if action.recovery is not None and action.recovery.source_subject_identity_id not in identities:
                raise ValueError("recovery identity missing")
            for proof in action.proofs:
                if proof.observation_identity_id not in identities or (proof.observer_id is not None and proof.observer_id not in observers):
                    raise ValueError("proof identity or observer missing")
                for source in proof.auxiliary_sources:
                    if source.observation_identity_id not in identities or source.observer_id not in observers:
                        raise ValueError("auxiliary identity or observer missing")
                    if source.trace_namespace is not None:
                        if observer_specs[source.observer_id].observer_type != "STRUCTURED_AUDIT_LOG":
                            raise ValueError("trace requires a structured audit source")
                        if trace_namespaces.setdefault(source.observer_id, source.trace_namespace) != source.trace_namespace:
                            raise ValueError("one trace source cannot claim multiple namespaces")
        return self


    @model_validator(mode='after')
    def proof_coverage(self):
        if len({source.source_id for source in self.proof_sources})!=len(self.proof_sources):
            raise ValueError('duplicate proof source')
        proofs={(action.action_id,proof.effect_id):proof for action in self.actions for proof in action.proofs}
        actions={action.action_id:action for action in self.actions}
        identities={item.identity_id:item for item in self.identities}
        for source in self.proof_sources:
            config=source.config
            proof=proofs.get((config.action_id,config.effect_id))
            if (source.source_fingerprint!=proof_fingerprint(config) or proof is None
                or actions[config.action_id].action_revision!=config.action_revision
                or proof.rule!='REGISTERED_EFFECT' or proof.descriptor_fingerprint!=source.source_fingerprint
                or proof.observer_id!='json_'+source.source_id[4:]
                or proof.observation_identity_id!=config.observation_identity_id
                or proof.effect_kind!=source.contract.approved_effect_kind
                or source.contract.contract_id!=config.source_contract_id
                or set(source.identity_roles)!={claim.identity_id for claim in config.identity_claims}
                or not set(source.identity_roles)<=set(identities)):
                raise ValueError('proof association mismatch')
            for claim in config.identity_claims:
                identity=identities.get(claim.identity_id)
                if (identity is None or identity.verification is None
                    or identity.verification.expected_application_subject_id!=claim.application_subject_id):
                    raise ValueError('proof identity association mismatch')
        return self

    @model_validator(mode='after')
    def creation_sources(self):
        sources={'json_'+source.source_id[4:]:source for source in self.proof_sources}
        for action in self.actions:
            for proof in action.proofs:
                source=sources.get(proof.observer_id)
                created=source is not None and source.config.source_kind=='CREATED_OBJECT_RECORDS'
                if (action.created_resource is not None)!=created:
                    raise ValueError('creation action requires adopted collection proof')
        return self

    @model_validator(mode="after")
    def runtime_matches_source(self):
        if isinstance(self.runtime, ExternalWebRuntime):
            return self
        reference = self.runtime.reference
        if reference.source_fingerprint != self.source_fingerprint:
            raise ValueError("runtime source differs from frozen check source")
        if isinstance(self.runtime, NodeRuntime) and (reference.project_id != self.project_id
                or self.target.base_url != f"http://127.0.0.1:{reference.port}"):
            raise ValueError("Node instance differs from frozen project or target")
        return self


class CheckRuntimeProtocolError(ValueError):
    code = "RUNNER_PROTOCOL_INVALID"


def check_payload_contains_secret(value, known_secrets: tuple[str, ...]) -> bool:
    """在 JSON 转义前检查字符串叶值，避免引号或换行使已知秘密漏过字节扫描。"""
    if isinstance(value, str):
        return any(secret and secret in value for secret in known_secrets)
    if isinstance(value, dict):
        return any(check_payload_contains_secret(key, known_secrets) or check_payload_contains_secret(child, known_secrets)
            for key, child in value.items())
    if isinstance(value, (tuple, list)):
        return any(check_payload_contains_secret(child, known_secrets) for child in value)
    return False


def canonical_check_runtime_bytes(bundle: CheckRuntimeBundle) -> bytes:
    try:
        if type(bundle) is not CheckRuntimeBundle:
            raise ValueError("unsupported runtime document")
        parsed = CheckRuntimeBundle.model_validate_json(bundle.model_dump_json(), strict=True)
        raw = encode_json(parsed.model_dump(mode="json"))
        if len(raw) > CHECK_DOCUMENT_MAX_BYTES or _SECRET.search(raw.decode()):
            raise ValueError("unsafe or oversized check runtime")
        return raw
    except (ValueError, TypeError, AttributeError):
        raise CheckRuntimeProtocolError("执行快照格式无效") from None


def check_runtime_fingerprint(bundle: CheckRuntimeBundle) -> str:
    return hashlib.sha256(canonical_check_runtime_bytes(bundle)).hexdigest()


def parse_check_runtime(raw: bytes) -> CheckRuntimeBundle:
    try:
        decode_document(raw, document_type="jiejian.check-runtime", version="1", limit=CHECK_DOCUMENT_MAX_BYTES)
        bundle = CheckRuntimeBundle.model_validate_json(raw, strict=True)
        if canonical_check_runtime_bytes(bundle) != raw:
            raise ValueError("noncanonical runtime")
        return bundle
    except (ValueError, TypeError, UnicodeError):
        raise CheckRuntimeProtocolError("执行快照格式无效") from None
