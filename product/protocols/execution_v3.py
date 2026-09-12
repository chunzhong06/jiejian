# 独立执行快照 wire：只依赖 Pydantic 与标准库，严格冻结无秘密的权限实验事实。
from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

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

    @model_validator(mode="after")
    def validate_semantics(self):
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
    descriptor_id: Annotated[str, Field(pattern=r"^exp_[0-9a-f]{32}$")]
    descriptor_fingerprint: Hash
    observer_id: LogicalId


class EffectProofRequirement(WireModel):
    effect_id: EffectId
    level: Literal["VERDICT_REQUIRED", "DIAGNOSIS_REQUIRED", "SUPPORTING"]
    rule: Literal["HTTP_RESOURCE_PRESENCE", "REGISTERED_EFFECT", "RECORDED_SUPPORT"]
    binding_fingerprint: Hash
    resource_id: Annotated[str, Field(min_length=1, max_length=256)]
    reference: Annotated[RecordedProofReference | ObserverProofReference, Field(discriminator="kind")]
    proof_fingerprint: Hash

    @model_validator(mode="after")
    def validate_proof(self):
        if self.rule == "REGISTERED_EFFECT" and not isinstance(self.reference, ObserverProofReference):
            raise ValueError("proof reference kind")
        if self.rule != "REGISTERED_EFFECT" and not isinstance(self.reference, RecordedProofReference):
            raise ValueError("proof reference kind")
        if self.rule == "RECORDED_SUPPORT" and self.level != "SUPPORTING":
            raise ValueError("support cannot decide verdict")
        if self.proof_fingerprint != content_hash("EffectProofRequirement", self.model_dump(mode="json", exclude={"proof_fingerprint"})):
            raise ValueError("proof fingerprint")
        return self


class RecoveryReference(WireModel):
    recording_id: Annotated[str, Field(pattern=r"^rec_[0-9a-f]{32}$")]
    draft_revision: int = Field(ge=1)
    draft_sha256: Hash
    step_id: LogicalId
    binding_fingerprint: Hash
    request_template_fingerprint: Hash


class CaseRole(StrEnum):
    ALLOW_REGRESSION = "ALLOW_REGRESSION"
    ALLOW_CONTROL = "ALLOW_CONTROL"
    DENY_CHALLENGE = "DENY_CHALLENGE"


class ExecutionCase(WireModel):
    case_id: Annotated[str, Field(pattern=r"^case_[0-9a-f]{32}$")]
    roles: tuple[CaseRole, ...] = Field(min_length=1, max_length=2)
    permission: FrozenPermission
    subject_test_identity_id: IdentityId
    subject_actor_id: ActorId
    subject_actor_revision: int = Field(ge=1)
    subject_identity_fingerprint: Hash
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
    source_fingerprint: Hash
    config_fingerprint: Hash

    @model_validator(mode="after")
    def validate_case(self):
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
    source_fingerprint: Hash
    config_fingerprint: Hash


class ExecutionTwin(WireModel):
    twin_id: Annotated[str, Field(pattern=r"^twin_[0-9a-f]{32}$")]
    deny_case_id: Annotated[str, Field(pattern=r"^case_[0-9a-f]{32}$")]
    allow_case_id: Annotated[str, Field(pattern=r"^case_[0-9a-f]{32}$")]
    selected_allow_permission: PermissionReference
    protected_effect_ids: tuple[EffectId, ...] = Field(min_length=1, max_length=16)
    invariants: TwinInvariants
    fingerprint: Hash


def case_invariants(case):
    return TwinInvariants(
        resource_id=case.resource_id, resource_owner_test_identity_id=case.resource_owner_test_identity_id,
        owner_identity_fingerprint=case.owner_identity_fingerprint, execution=case.execution,
        proof_fingerprints=tuple(sorted(item.proof_fingerprint for item in case.proof_requirements)),
        recovery_fingerprint=None if case.recovery is None else case.recovery.binding_fingerprint,
        source_fingerprint=case.source_fingerprint, config_fingerprint=case.config_fingerprint,
    )


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
            if case_invariants(deny) != case_invariants(allow) or case_invariants(deny) != twin.invariants:
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


class PersistedExecutionRequestV3(WireModel):
    schema_version: Literal["3"] = "3"
    project_id: LogicalId
    source_fingerprint: Hash
    policy_epoch: int = Field(ge=0)
    engine_version: str = Field(pattern=r"^[a-zA-Z0-9_.-]{1,64}$")
    plan_fingerprint: Hash
    actions: tuple[ExecutionAction, ...] = Field(min_length=1, max_length=512)
    config_fingerprint: Hash
    budget_fingerprint: Hash
    change_context: ChangeContext | None = None
    repair_context: RepairContext | None = None

    @model_validator(mode="after")
    def validate_project(self):
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


class ExecutionV3Error(ValueError):
    code = "RUNNER_PROTOCOL_INVALID"


def canonical_execution_request_v3_bytes(request: PersistedExecutionRequestV3) -> bytes:
    # 重新校验以拒绝 model_copy/model_construct 绕过；字段不允许秘密正文或绝对路径。
    try:
        payload = request.model_dump(mode="json")
        parsed = PersistedExecutionRequestV3.model_validate_json(json.dumps(payload), strict=True)
        payload = parsed.model_dump(mode="json")
        payload["actions"].sort(key=lambda item: item["action_id"])
        for action in payload["actions"]:
            action["cases"].sort(key=lambda item: item["case_id"])
            action["twins"].sort(key=lambda item: item["twin_id"])
            for case in action["cases"]:
                case["proof_requirements"].sort(key=lambda item: (item["effect_id"], item["level"]))
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(raw) > RUNNER_INPUT_MAX_BYTES or re.search(rb"(?i)(?:Bearer\s|password\s*[:=]|token\s*[:=]|<script)", raw):
            raise ValueError("execution boundary")
        return raw
    except (ValueError, TypeError, AttributeError):
        raise ExecutionV3Error("执行快照格式无效") from None


def parse_execution_request_v3(raw: bytes) -> PersistedExecutionRequestV3:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
    try:
        if type(raw) is not bytes or len(raw) > RUNNER_INPUT_MAX_BYTES or raw.startswith(b"\xef\xbb\xbf"):
            raise ValueError("execution bytes")
        json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                   parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
        request = PersistedExecutionRequestV3.model_validate_json(raw, strict=True)
        if canonical_execution_request_v3_bytes(request) != raw:
            raise ValueError("noncanonical")
        return request
    except (ValueError, TypeError, UnicodeError):
        raise ExecutionV3Error("执行快照格式无效") from None
