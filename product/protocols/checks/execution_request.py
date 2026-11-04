# 独立执行快照 wire：只依赖 Pydantic 与标准库，严格冻结无秘密的权限实验事实。
from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Annotated, Literal
from product.protocols.codec import encode_json, decode_document, decode_json

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator
from product.protocols.checks.conditions import PermissionConditions
from product.protocols.web.environment import FrozenEnvironment

RUNNER_INPUT_MAX_BYTES = 1_048_576
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
LogicalId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
ActorId = Annotated[str, Field(pattern=r"^bar_[0-9a-f]{32}$")]
EffectId = Annotated[str, Field(pattern=r"^bef_[0-9a-f]{32}$")]
IdentityId = Annotated[str, Field(pattern=r"^tid_[0-9a-f]{32}$")]
IntentId = Annotated[str, Field(pattern=r"^pin_[0-9a-f]{32}$")]


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)

    @model_validator(mode="after")
    def validate_resource_identifier(self):
        value = getattr(self, "resource_id", None)
        if value is not None and (value in {".", ".."} or re.fullmatch(r"[\w.-]{1,256}", value) is None):
            raise ValueError("resource identifier")
        return self


def content_hash(domain: str, value) -> str:
    return hashlib.sha256(json.dumps({"kind": domain, "facts": value}, ensure_ascii=False,
        sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


class PermissionReference(WireModel):
    intent_id: IntentId
    revision: int = Field(ge=1)
    intent_hash: Hash


class FrozenPermission(PermissionReference):
    expectation: Literal["ALLOW", "DENY"]
    relation: Literal["OWNS", "SAME_ROLE_OTHER_ACCOUNT", "OTHER_ROLE"]
    subject_actor_id: ActorId
    subject_actor_revision: int = Field(ge=1)
    resource_owner_actor_id: ActorId
    resource_owner_actor_revision: int = Field(ge=1)
    protected_effect_ids: tuple[EffectId, ...] = Field(min_length=1, max_length=16)
    conditions: PermissionConditions | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def validate_semantics(self):
        if self.conditions is not None:
            if self.conditions.principal == 'ANONYMOUS' and self.relation != 'OTHER_ROLE':
                raise ValueError('anonymous permission actor relation')
            if self.conditions.tenant == 'DIFFERENT' and self.relation == 'OWNS':
                raise ValueError('cross-tenant permission actor relation')
        same = (self.subject_actor_id, self.subject_actor_revision) == (self.resource_owner_actor_id, self.resource_owner_actor_revision)
        if self.relation in ("OWNS", "SAME_ROLE_OTHER_ACCOUNT") and not same:
            raise ValueError("permission actor relation")
        if self.relation == "OTHER_ROLE" and self.subject_actor_id == self.resource_owner_actor_id:
            raise ValueError("permission actor relation")
        if tuple(sorted(set(self.protected_effect_ids))) != self.protected_effect_ids:
            raise ValueError("permission effects must be unique and sorted")
        return self


class ExecutionAssetReference(WireModel):
    flow_id: LogicalId
    flow_sha256: Hash
    execution_binding_fingerprint: Hash


class RecordedProofReference(WireModel):
    kind: Literal["RECORDED_OBSERVATION"] = "RECORDED_OBSERVATION"
    recording_id: Annotated[str, Field(pattern=r"^rec_[0-9a-f]{32}$")]
    draft_revision: int = Field(ge=1)
    draft_sha256: Hash
    step_id: LogicalId
    request_template_fingerprint: Hash


class ObserverProofReference(WireModel):
    kind: Literal["REGISTERED_OBSERVER"] = "REGISTERED_OBSERVER"
    descriptor_id: Annotated[str, Field(pattern=r"^(exp|psr)_[0-9a-f]{32}$")]
    descriptor_fingerprint: Hash
    observer_id: LogicalId


class OperationProofReference(WireModel):
    kind: Literal['OPERATION_HTTP_ENTITY'] = 'OPERATION_HTTP_ENTITY'
    flow_id: str = Field(pattern=r'^ofl_[0-9a-f]{32}$')
    revision: int = Field(ge=1)
    query_fingerprint: Hash


class EffectProofRequirement(WireModel):
    effect_id: EffectId
    level: Literal["VERDICT_REQUIRED", "DIAGNOSIS_REQUIRED", "SUPPORTING"]
    rule: Literal["HTTP_RESOURCE_PRESENCE", "REGISTERED_EFFECT", "RECORDED_SUPPORT", "HTTP_ENTITY_QUERY"]
    binding_fingerprint: Hash
    resource_id: Annotated[str, Field(min_length=1, max_length=256)]
    reference: Annotated[RecordedProofReference | ObserverProofReference | OperationProofReference, Field(discriminator="kind")]
    proof_fingerprint: Hash

    @model_validator(mode="after")
    def validate_proof(self):
        if self.rule == "REGISTERED_EFFECT" and not isinstance(self.reference, ObserverProofReference):
            raise ValueError("proof reference kind")
        if self.rule == 'HTTP_ENTITY_QUERY' and not isinstance(self.reference,OperationProofReference):
            raise ValueError('entity query proof reference kind')
        if self.rule not in {"REGISTERED_EFFECT", 'HTTP_ENTITY_QUERY'} and not isinstance(self.reference, RecordedProofReference):
            raise ValueError("proof reference kind")
        if self.rule == "RECORDED_SUPPORT" and self.level != "SUPPORTING":
            raise ValueError("support cannot decide verdict")
        if self.proof_fingerprint != content_hash("EffectProofRequirement", self.model_dump(mode="json", exclude={"proof_fingerprint"})):
            raise ValueError("proof fingerprint")
        return self


class RecoveryReference(WireModel):
    recording_id: Annotated[str, Field(pattern=r"^rec_[0-9a-f]{32}$")] | None = Field(default=None, exclude_if=lambda value:value is None)
    draft_revision: int | None = Field(default=None, ge=1, exclude_if=lambda value:value is None)
    draft_sha256: Hash | None = Field(default=None, exclude_if=lambda value:value is None)
    operation_flow_id: Annotated[str, Field(pattern=r"^ofl_[0-9a-f]{32}$")] | None = Field(default=None, exclude_if=lambda value:value is None)
    operation_flow_revision: int | None = Field(default=None, ge=1, exclude_if=lambda value:value is None)
    step_id: LogicalId
    binding_fingerprint: Hash
    request_template_fingerprint: Hash

    @model_validator(mode='after')
    def validate_origin(self):
        recorded=(self.recording_id,self.draft_revision,self.draft_sha256)
        edited=(self.operation_flow_id,self.operation_flow_revision)
        if not ((all(value is not None for value in recorded) and all(value is None for value in edited))
            or (all(value is None for value in recorded) and all(value is not None for value in edited))):
            raise ValueError('recovery requires one complete material origin')
        return self


class CaseRole(StrEnum):
    ALLOW_REGRESSION = "ALLOW_REGRESSION"
    ALLOW_CONTROL = "ALLOW_CONTROL"
    DENY_CHALLENGE = "DENY_CHALLENGE"


class ExecutionCase(WireModel):
    case_id: Annotated[str, Field(pattern=r"^case_[0-9a-f]{32}$")]
    roles: tuple[CaseRole, ...] = Field(min_length=1, max_length=2)
    permission: FrozenPermission
    subject_test_identity_id: IdentityId | None
    subject_actor_id: ActorId
    subject_actor_revision: int = Field(ge=1)
    subject_identity_fingerprint: Hash | None
    resource_owner_test_identity_id: IdentityId
    resource_owner_actor_id: ActorId
    resource_owner_actor_revision: int = Field(ge=1)
    owner_identity_fingerprint: Hash
    resource_id: Annotated[str, Field(min_length=1, max_length=256)]
    resource_binding_fingerprint: Hash
    execution: ExecutionAssetReference
    protected_effect_ids: tuple[EffectId, ...] = Field(min_length=1, max_length=16)
    proof_requirements: tuple[EffectProofRequirement, ...] = Field(min_length=1, max_length=48)
    recovery: RecoveryReference | None
    source_fingerprint: Hash | None
    config_fingerprint: Hash

    @model_validator(mode="after")
    def validate_case(self):
        anonymous = self.permission.conditions is not None and self.permission.conditions.principal == 'ANONYMOUS'
        if anonymous != (self.subject_test_identity_id is None and self.subject_identity_fingerprint is None):
            raise ValueError('case principal requires either a real identity or an explicit anonymous condition')
        if not anonymous and (self.subject_test_identity_id is None or self.subject_identity_fingerprint is None):
            raise ValueError('authenticated case identity missing')
        if len(set(self.roles)) != len(self.roles) or tuple(sorted(self.roles)) != self.roles:
            raise ValueError("case roles must be unique and sorted")
        if (self.permission.expectation == "DENY") != (self.roles == (CaseRole.DENY_CHALLENGE,)):
            raise ValueError("case roles contradict permission")
        for name in ("subject_actor_id", "subject_actor_revision", "resource_owner_actor_id", "resource_owner_actor_revision"):
            if getattr(self, name) != getattr(self.permission, name):
                raise ValueError("case permission actor")
        same = self.subject_test_identity_id == self.resource_owner_test_identity_id
        if same != (self.permission.relation == "OWNS"):
            raise ValueError("case identity relation")
        if same and self.subject_identity_fingerprint != self.owner_identity_fingerprint:
            raise ValueError("same identity fingerprint")
        if tuple(sorted(set(self.protected_effect_ids))) != self.protected_effect_ids or not set(self.protected_effect_ids) <= set(self.permission.protected_effect_ids):
            raise ValueError("case effect set")
        if CaseRole.ALLOW_REGRESSION in self.roles and self.protected_effect_ids != self.permission.protected_effect_ids:
            raise ValueError("regression must protect all permission effects")
        if any(item.resource_id != self.resource_id or item.effect_id not in self.protected_effect_ids for item in self.proof_requirements):
            raise ValueError("proof case resource")
        if len({(item.effect_id, item.level) for item in self.proof_requirements}) != len(self.proof_requirements):
            raise ValueError("duplicate case proof")
        if {item.effect_id for item in self.proof_requirements if item.level == "VERDICT_REQUIRED"} != set(self.protected_effect_ids):
            raise ValueError("case lacks verdict proof")
        return self


class TwinInvariants(WireModel):
    resource_id: str = Field(min_length=1, max_length=256)
    resource_owner_test_identity_id: IdentityId
    owner_identity_fingerprint: Hash
    execution: ExecutionAssetReference
    proof_fingerprints: tuple[Hash, ...] = Field(min_length=1, max_length=48)
    recovery_fingerprint: Hash | None
    source_fingerprint: Hash | None
    config_fingerprint: Hash


class ExecutionTwin(WireModel):
    twin_id: Annotated[str, Field(pattern=r"^twin_[0-9a-f]{32}$")]
    deny_case_id: Annotated[str, Field(pattern=r"^case_[0-9a-f]{32}$")]
    allow_case_id: Annotated[str, Field(pattern=r"^case_[0-9a-f]{32}$")]
    selected_allow_permission: PermissionReference
    protected_effect_ids: tuple[EffectId, ...] = Field(min_length=1, max_length=16)
    invariants: TwinInvariants
    fingerprint: Hash
    condition_difference: Literal['RESOURCE_STATE'] | None = Field(default=None, exclude_if=lambda value: value is None)


def case_invariants(case):
    return TwinInvariants(
        resource_id=case.resource_id, resource_owner_test_identity_id=case.resource_owner_test_identity_id,
        owner_identity_fingerprint=case.owner_identity_fingerprint, execution=case.execution,
        proof_fingerprints=tuple(sorted(item.proof_fingerprint for item in case.proof_requirements)),
        recovery_fingerprint=None if case.recovery is None else case.recovery.binding_fingerprint,
        source_fingerprint=case.source_fingerprint, config_fingerprint=case.config_fingerprint,
    )


def conditional_resource_twin(deny, allow):
    """仅资源前置状态允许使用不同测试数据；归属、执行及证明方法仍精确对应。"""
    left, right = deny.permission.conditions, allow.permission.conditions
    if (left is None or right is None or not left.resource_states or not right.resource_states
            or set(left.resource_states).intersection(right.resource_states) or deny.resource_id == allow.resource_id):
        return False
    a, b = case_invariants(deny), case_invariants(allow)
    if a.model_dump(exclude={'resource_id','proof_fingerprints'}) != b.model_dump(exclude={'resource_id','proof_fingerprints'}):
        return False
    def methods(case):
        return sorted((proof.model_dump(mode='json', exclude={'resource_id','proof_fingerprint'})
                       for proof in case.proof_requirements), key=lambda proof:(proof['effect_id'],proof['level']))
    return methods(deny) == methods(allow)


class ExecutionAction(WireModel):
    action_id: Annotated[str, Field(pattern=r"^bac_[0-9a-f]{32}$")]
    action_revision: int = Field(ge=1)
    action_semantic_fingerprint: Hash
    cases: tuple[ExecutionCase, ...] = Field(min_length=1, max_length=4096)
    twins: tuple[ExecutionTwin, ...] = Field(max_length=4096)

    @model_validator(mode="after")
    def validate_twins(self):
        cases = {item.case_id: item for item in self.cases}
        if len(cases) != len(self.cases) or len({item.twin_id for item in self.twins}) != len(self.twins):
            raise ValueError("duplicate case or twin")
        for case in self.cases:
            facts = case.model_dump(mode="json", exclude={"case_id", "roles"})
            facts["proof_requirements"].sort(key=lambda item: (item["effect_id"], item["level"]))
            identity = content_hash("CheckCase", {"action_id": self.action_id, "revision": self.action_revision,
                "facts": facts})
            if case.case_id != "case_" + identity[:32]:
                raise ValueError("case content identity")
        for twin in self.twins:
            deny, allow = cases.get(twin.deny_case_id), cases.get(twin.allow_case_id)
            if deny is None or allow is None or deny.permission.expectation != "DENY" or CaseRole.ALLOW_CONTROL not in allow.roles:
                raise ValueError("invalid twin case reference")
            if tuple(getattr(allow.permission, key) for key in ("intent_id", "revision", "intent_hash")) != tuple(getattr(twin.selected_allow_permission, key) for key in ("intent_id", "revision", "intent_hash")):
                raise ValueError("twin selected permission")
            if deny.protected_effect_ids != allow.protected_effect_ids or deny.protected_effect_ids != twin.protected_effect_ids:
                raise ValueError("twin effect mismatch")
            if (case_invariants(deny) != twin.invariants or
                    (not conditional_resource_twin(deny, allow) if twin.condition_difference == 'RESOURCE_STATE'
                     else case_invariants(deny) != case_invariants(allow))):
                raise ValueError("twin invariant mismatch")
            if twin.fingerprint != content_hash("CheckTwin", twin.model_dump(mode="json", exclude={"fingerprint"})):
                raise ValueError("twin fingerprint")
        deny_ids = {item.case_id for item in self.cases if item.permission.expectation == "DENY"}
        if len(self.twins) != len(deny_ids) or {item.deny_case_id for item in self.twins} != deny_ids:
            raise ValueError("deny requires exactly one complete control")
        controls = {item.case_id for item in self.cases if CaseRole.ALLOW_CONTROL in item.roles}
        if controls != {item.allow_case_id for item in self.twins}:
            raise ValueError("orphan allow control")
        return self


class ChangeContext(WireModel):
    change_id: LogicalId
    impact_fingerprint: Hash
    required_intent_ids: tuple[IntentId, ...] = Field(min_length=1, max_length=4096)

    @model_validator(mode="after")
    def validate_sets(self):
        if tuple(sorted(set(self.required_intent_ids))) != self.required_intent_ids:
            raise ValueError("change intent set")
        return self


class RepairContext(WireModel):
    # 引用完整合同内容指纹，不加前缀或截断；业务逻辑 ID 的约束不因修复放宽。
    repair_reference: Hash
    source_run_id: LogicalId
    original_policy_epoch: int = Field(ge=0)
    original_intents: tuple[PermissionReference, ...] = Field(min_length=1, max_length=4096)
    selected_allow_permission: PermissionReference
    resource_id: str = Field(min_length=1, max_length=256)
    resource_owner_test_identity_id: IdentityId
    owner_identity_fingerprint: Hash
    must_disappear_effect_ids: tuple[EffectId, ...] = Field(min_length=1, max_length=16)
    original_evidence_standard_fingerprints: tuple[Hash, ...] = Field(min_length=1, max_length=48)
    # 源 BLOCK 可以没有已通过的正常回归；selected control 仍单独冻结且必须在复验中通过。
    allow_regression_case_fingerprints: tuple[Hash, ...] = Field(max_length=4096)

    @model_validator(mode="after")
    def validate_sets(self):
        for name in ("must_disappear_effect_ids", "original_evidence_standard_fingerprints", "allow_regression_case_fingerprints"):
            values = getattr(self, name)
            if tuple(sorted(set(values))) != values:
                raise ValueError("repair reference set")
        keys = tuple((item.intent_id, item.revision, item.intent_hash) for item in self.original_intents)
        if tuple(sorted(set(keys))) != keys:
            raise ValueError("repair intent set")
        return self


class ExternalRecheckContext(WireModel):
    source_environment_fingerprint: Hash
    deployment_statement: str = Field(min_length=1,max_length=256)


class FrozenRequirement(WireModel):
    requirement_id: str = Field(pattern=r'^req_[0-9a-f]{16}$')
    requirement: str = Field(min_length=1, max_length=1024)
    disposition: Literal['IN_SCOPE', 'PREPARATION', 'OUT_OF_SCOPE']
    time_scope: Literal['CHECK_WINDOW', 'HISTORY', 'NOT_APPLICABLE']
    permissions: tuple[PermissionReference, ...] = Field(max_length=200)

class FrozenRequirementScope(WireModel):
    candidate_id: str = Field(pattern=r'^rcd_[0-9a-f]{32}$')
    revision: int = Field(ge=1)
    requirements: tuple[FrozenRequirement, ...] = Field(min_length=1, max_length=100)


class FrozenCheckSelection(WireModel):
    selected: tuple[PermissionReference, ...] = Field(min_length=1, max_length=4096)
    added_controls: tuple[PermissionReference, ...] = Field(max_length=4096)
    omitted: tuple[PermissionReference, ...] = Field(max_length=4096)
    uncovered_requirements: tuple[str, ...] = Field(max_length=20000)
    pending_review_ids: tuple[str, ...] = Field(max_length=20000)

    @model_validator(mode="after")
    def distinct_sets(self):
        seen = set()
        for name in ("selected", "added_controls", "omitted"):
            keys = tuple((item.intent_id, item.revision, item.intent_hash) for item in getattr(self, name))
            if tuple(sorted(set(keys))) != keys or seen.intersection(keys):
                raise ValueError("selection references must be sorted, distinct and disjoint")
            seen.update(keys)
        for name in ("uncovered_requirements", "pending_review_ids"):
            values = getattr(self, name)
            if tuple(sorted(set(values))) != values:
                raise ValueError("selection omissions must be sorted and unique")
        return self


class ExecutionRequest(WireModel):
    document_type: Literal["jiejian.execution-request"] = "jiejian.execution-request"
    schema_version: Literal["1", "2"] = "1"
    environment: FrozenEnvironment | None = Field(default=None, exclude_if=lambda value: value is None)
    requirement_scope: tuple[FrozenRequirementScope, ...] = Field(default=(), max_length=200)
    selection: FrozenCheckSelection | None = None
    project_id: LogicalId
    source_fingerprint: Hash | None
    policy_epoch: int = Field(ge=0)
    engine_version: str = Field(pattern=r"^[a-zA-Z0-9_.-]{1,64}$")
    plan_fingerprint: Hash
    actions: tuple[ExecutionAction, ...] = Field(min_length=1, max_length=512)
    config_fingerprint: Hash
    budget_fingerprint: Hash
    change_context: ChangeContext | None = None
    repair_context: RepairContext | None = None
    external_recheck: ExternalRecheckContext | None = Field(default=None,exclude_if=lambda value:value is None)

    @model_serializer(mode="wrap")
    def preserve_full_request_encoding(self, handler):
        values = handler(self)
        # 完整检查没有新增选择事实；保留已有请求字节和历史内容摘要。
        if self.selection is None:
            values.pop("selection", None)
        return values

    @model_validator(mode="after")
    def validate_project(self):
        if (self.schema_version == '2') != (self.environment is not None):
            raise ValueError('environment snapshot requires execution request version 2')
        if self.source_fingerprint is None and self.environment is None:
            raise ValueError('source-free execution requires a frozen environment')
        if self.external_recheck is not None and (self.environment is None or self.source_fingerprint is not None
            or self.repair_context is None or self.change_context is not None or self.selection is not None):
            raise ValueError('external recheck requires its original contract and external environment')
        if self.environment is None and any(proof.rule == 'HTTP_ENTITY_QUERY'
            for action in self.actions for case in action.cases for proof in case.proof_requirements):
            raise ValueError('entity proof requires a frozen environment')
        if len({item.action_id for item in self.actions}) != len(self.actions):
            raise ValueError("duplicate action")
        ids = [case.case_id for action in self.actions for case in action.cases]
        if len(set(ids)) != len(ids):
            raise ValueError("cross action case identity")
        identities = {}
        for action in self.actions:
            for case in action.cases:
                if (case.source_fingerprint, case.config_fingerprint) != (self.source_fingerprint, self.config_fingerprint):
                    raise ValueError("case source configuration")
                for identity_id, facts in (
                    (case.subject_test_identity_id, (case.subject_actor_id, case.subject_actor_revision, case.subject_identity_fingerprint)),
                    (case.resource_owner_test_identity_id, (case.resource_owner_actor_id, case.resource_owner_actor_revision, case.owner_identity_fingerprint)),
                ):
                    if identity_id is None:
                        continue
                    if identities.setdefault(identity_id, facts) != facts:
                        raise ValueError("cross case identity facts")
        # 完整执行快照只来自无 gap 的纯计划；独立重算内容身份，不依赖 backend 编译器。
        actions = [action.model_dump(mode="json") | {"gaps": []} for action in self.actions]
        actions.sort(key=lambda item: item["action_id"])
        for action in actions:
            action["cases"].sort(key=lambda item: item["case_id"])
            action["twins"].sort(key=lambda item: item["twin_id"])
            for case in action["cases"]:
                case["proof_requirements"].sort(key=lambda item: (item["effect_id"], item["level"]))
        plan = dict(project_id=self.project_id, source_fingerprint=self.source_fingerprint,
                    policy_epoch=self.policy_epoch, engine_version=self.engine_version, actions=actions, gaps=[])
        if self.plan_fingerprint != content_hash("ProjectCheckPlan", plan):
            raise ValueError("plan content identity")
        return self

    @model_validator(mode='after')
    def requirements_match_cases(self):
        facts = {(case.permission.intent_id, case.permission.revision, case.permission.intent_hash) for action in self.actions for case in action.cases}
        uncovered = []
        for scope in self.requirement_scope:
            for item in scope.requirements:
                linked = {(ref.intent_id, ref.revision, ref.intent_hash) for ref in item.permissions}
                if item.disposition == 'IN_SCOPE' and (not linked or not linked <= facts or item.time_scope == 'HISTORY'):
                    uncovered.append(f"{scope.candidate_id}@{scope.revision}/{item.requirement_id}")
                if item.disposition != 'IN_SCOPE' and linked:
                    raise ValueError('outside requirement must not claim checked rules')
        if self.selection is None:
            if uncovered:
                raise ValueError('frozen requirement is not covered by current cases')
        else:
            selection = self.selection
            keys = lambda values: {(item.intent_id, item.revision, item.intent_hash) for item in values}
            if self.change_context is not None or self.repair_context is not None:
                raise ValueError("original-case revalidation cannot narrow its scope")
            if keys(selection.selected) | keys(selection.added_controls) != facts:
                raise ValueError("selected scope does not match executed cases")
            controls = {(case.permission.intent_id, case.permission.revision, case.permission.intent_hash)
                        for action in self.actions for case in action.cases if CaseRole.ALLOW_CONTROL in case.roles}
            if not keys(selection.added_controls) <= controls:
                raise ValueError("automatically added rules must be normal controls")
            if tuple(sorted(uncovered)) != selection.uncovered_requirements:
                raise ValueError("uncovered business requirements must remain explicit")
        return self


class ExecutionRequestError(ValueError):
    code = "RUNNER_PROTOCOL_INVALID"


def canonical_execution_request_bytes(request: ExecutionRequest) -> bytes:
    try:
        if type(request) is not ExecutionRequest:
            raise ValueError("unsupported execution root")
        # 模型由构造或入口 reader 接受；编码只确定字节与顺序，不再次解析同一对象。
        payload = request.model_dump(mode="json")
        payload["actions"].sort(key=lambda item: item["action_id"])
        for action in payload["actions"]:
            action["cases"].sort(key=lambda item: item["case_id"])
            action["twins"].sort(key=lambda item: item["twin_id"])
            for case in action["cases"]:
                case["proof_requirements"].sort(key=lambda item: (item["effect_id"], item["level"]))
        raw = encode_json(payload)
        if len(raw) > RUNNER_INPUT_MAX_BYTES or re.search(rb"(?i)(?:Bearer\s|password\s*[:=]|token\s*[:=]|<script)", raw):
            raise ValueError("execution boundary")
        return raw
    except (ValueError, TypeError, AttributeError):
        raise ExecutionRequestError("执行快照格式无效") from None


def parse_execution_request(raw: bytes) -> ExecutionRequest:
    try:
        version = decode_json(raw, limit=RUNNER_INPUT_MAX_BYTES).get('schema_version')
        if version not in {'1', '2'}:
            raise ValueError('unsupported execution request version')
        decode_document(raw, document_type="jiejian.execution-request", version=version, limit=RUNNER_INPUT_MAX_BYTES)
        request = ExecutionRequest.model_validate_json(raw, strict=True)
        if canonical_execution_request_bytes(request) != raw:
            raise ValueError("noncanonical execution order")
        return request
    except (ValueError, TypeError, UnicodeError):
        raise ExecutionRequestError("执行快照格式无效") from None
