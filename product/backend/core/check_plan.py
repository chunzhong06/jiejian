# 从当前权限和已检查技术事实纯编译有限实验，不读取 Storage、秘密、网络或模型。
from __future__ import annotations

from pydantic import Field
from product.backend.core.business_boundary import BoundaryModel, BusinessActionRevision
from product.backend.core.assurance import ActionAssuranceContract
from product.backend.core.action_preparation import ActionExecutionBinding, ActionResourceBinding, ActionEvidenceBinding, ActionRecoveryBinding
from product.backend.core.permission_intent import PermissionIntentRevision
from product.protocols.execution_v3 import (
    WireModel, Hash, LogicalId, ActorId, EffectId, IdentityId, CaseRole, FrozenPermission,
    PermissionReference, ExecutionAssetReference, RecordedProofReference, ObserverProofReference,
    EffectProofRequirement, RecoveryReference, ExecutionCase, ExecutionTwin, case_invariants, content_hash,
)
from typing import Literal
from urllib.parse import parse_qsl, urlsplit


class RegisteredEffectProofCapability(WireModel):
    descriptor_id: str = Field(pattern=r"^exp_[0-9a-f]{32}$")
    descriptor_fingerprint: Hash
    observer_id: LogicalId
    effect_id: EffectId
    states: tuple[Literal["CONFIRMED"], Literal["ABSENT"], Literal["UNKNOWN"]] = ("CONFIRMED", "ABSENT", "UNKNOWN")
    closure_supported: bool
    resource_correlation_supported: bool


class PreparedIdentityAssignment(WireModel):
    slot_id: str = Field(pattern=r"^isl_[0-9a-f]{32}$")
    identity_id: IdentityId
    actor_id: ActorId
    actor_revision: int = Field(ge=1)
    identity_fingerprint: Hash


class CheckPlanGap(WireModel):
    action_id: str = Field(pattern=r"^bac_[0-9a-f]{32}$")
    action_revision: int = Field(ge=1)
    reason: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,127}$")
    intent_id: str | None = Field(default=None, pattern=r"^pin_[0-9a-f]{32}$")
    effect_id: EffectId | None = None


class CheckCase(ExecutionCase):
    pass


class CheckTwin(ExecutionTwin):
    pass


class ActionCheckPlan(WireModel):
    action_id: str = Field(pattern=r"^bac_[0-9a-f]{32}$")
    action_revision: int = Field(ge=1)
    action_semantic_fingerprint: Hash
    cases: tuple[CheckCase, ...]
    twins: tuple[CheckTwin, ...]
    gaps: tuple[CheckPlanGap, ...]


class ProjectCheckPlan(WireModel):
    project_id: LogicalId
    source_fingerprint: Hash
    policy_epoch: int = Field(ge=0)
    engine_version: str
    actions: tuple[ActionCheckPlan, ...]
    gaps: tuple[CheckPlanGap, ...]
    plan_fingerprint: Hash


class PreparedActionInput(BoundaryModel):
    action: BusinessActionRevision
    permissions: tuple[PermissionIntentRevision, ...]
    assurance: ActionAssuranceContract
    identities: tuple[PreparedIdentityAssignment, ...]
    execution: ActionExecutionBinding | None = None
    resources: tuple[ActionResourceBinding, ...] = ()
    evidence: tuple[ActionEvidenceBinding, ...] = ()
    recovery: ActionRecoveryBinding | None = None
    observer_capabilities: tuple[RegisteredEffectProofCapability, ...] = ()
    reason_codes: tuple[str, ...] = ()


def classify_http_resource_presence(status: int | None, *, same_resource: bool, same_run: bool, redirected: bool = False):
    """只解释窄资源存在事实；任何关联不明或重定向均不能证明存在或不存在。"""
    if not same_resource or not same_run or redirected or type(status) is not int:
        return "UNKNOWN", "OPEN"
    if 200 <= status <= 299:
        return "CONFIRMED", "CLOSED"
    if status in (404, 410):
        return "ABSENT", "CLOSED"
    return "UNKNOWN", "OPEN"


def derive_effect_proof(effect, binding, resource_id, capabilities=()):
    """只有已绑定 descriptor 精确能力或资源形成的只读 GET 可以作为裁决证明。"""
    if binding.kind.value == "REGISTERED_OBSERVER":
        ref = binding.observer_reference
        capability = next((item for item in capabilities
            if (item.descriptor_id, item.descriptor_fingerprint, item.observer_id, item.effect_id)
            == (ref.descriptor_id, ref.descriptor_fingerprint, ref.observer_id, effect.effect_id)), None)
        level = "VERDICT_REQUIRED" if capability is not None and capability.closure_supported and capability.resource_correlation_supported else "SUPPORTING"
        reference = ObserverProofReference(**ref.model_dump())
        rule = "REGISTERED_EFFECT"
    else:
        template = binding.request_template
        parsed = urlsplit(template.relative_path)
        exact_slots = sum(part == "{case_resource_id}" for part in parsed.path.split("/"))
        exact_slots += sum(value == "{case_resource_id}" for _, value in parse_qsl(parsed.query, keep_blank_values=True))
        sufficient = (effect.effect_kind.value == "OBJECT_CREATION" and template.method == "GET"
                      and not template.json_body and exact_slots == 1
                      and template.relative_path.count("{case_resource_id}") == 1)
        level = "VERDICT_REQUIRED" if sufficient else "SUPPORTING"
        rule = "HTTP_RESOURCE_PRESENCE" if sufficient else "RECORDED_SUPPORT"
        reference = RecordedProofReference(
            recording_id=binding.source_recording_id, draft_revision=binding.source_draft_revision,
            draft_sha256=binding.source_draft_sha256, step_id=binding.step_id,
            request_template_fingerprint=content_hash("RecordedRequestTemplate", template.model_dump(mode="json")),
        )
    payload = dict(effect_id=effect.effect_id, level=level, rule=rule,
                   binding_fingerprint=binding.binding_fingerprint, resource_id=resource_id, reference=reference)
    raw = {**payload, "reference": reference.model_dump(mode="json")}
    return EffectProofRequirement(**payload, proof_fingerprint=content_hash("EffectProofRequirement", raw))


def compile_project_check_plan(project_id, *, source_fingerprint, policy_epoch, engine_version,
                               config_fingerprint, actions: tuple[PreparedActionInput, ...]):
    """保留全部 current Action 及其具名缺口；不以丢弃未准备动作伪造完整计划。"""
    compiled = tuple(_compile_action(item, source_fingerprint, config_fingerprint)
                     for item in sorted(actions, key=lambda item: (item.action.action_id, item.action.revision)))
    payload = dict(project_id=project_id, source_fingerprint=source_fingerprint, policy_epoch=policy_epoch,
                   engine_version=engine_version, actions=compiled,
                   gaps=tuple(gap for action in compiled for gap in action.gaps))
    raw = {**payload, "actions": [item.model_dump(mode="json") for item in compiled],
           "gaps": [item.model_dump(mode="json") for item in payload["gaps"]]}
    return ProjectCheckPlan(**payload, plan_fingerprint=content_hash("ProjectCheckPlan", raw))


def _compile_action(prepared, source_fingerprint, config_fingerprint):
    action = prepared.action
    gaps = []
    cases = {}
    twins = []
    permissions = {item.intent_id: item for item in prepared.permissions}
    positions = {item.permission.intent_id: item for item in prepared.assurance.identity_requirements.permissions}
    identities = {item.slot_id: item for item in prepared.identities}

    def gap(reason, permission=None, effect_id=None):
        item = CheckPlanGap(action_id=action.action_id, action_revision=action.revision, reason=reason,
                            intent_id=None if permission is None else permission.intent_id, effect_id=effect_id)
        if item not in gaps:
            gaps.append(item)

    for reason in sorted(set((*prepared.reason_codes, *prepared.assurance.reason_codes))):
        gap(reason)

    def make_case(permission, effects, role):
        position = positions.get(permission.intent_id)
        subject = None if position is None else identities.get(position.subject_slot_id)
        owner = None if position is None else identities.get(position.resource_owner_slot_id)
        if subject is None or owner is None:
            gap("TEST_IDENTITY_REQUIRED", permission)
            return None
        resource = next((item for item in prepared.resources if item.resource_owner_test_identity_id == owner.identity_id), None)
        if resource is None or resource.owner_identity_fingerprint != owner.identity_fingerprint:
            gap("ACTION_RESOURCE_REQUIRED", permission)
            return None
        execution = prepared.execution
        if execution is None or resource.resource_injection != execution.resource_injection:
            gap("ACTION_EXECUTION_REQUIRED", permission)
            return None
        if action.state_changing and prepared.recovery is None:
            gap("ACTION_RECOVERY_REQUIRED", permission)
            return None
        proofs = []
        for effect_id in effects:
            binding = next((item for item in prepared.evidence if item.effect_id == effect_id), None)
            effect = next((item for item in action.effect_catalog if item.effect_id == effect_id), None)
            # Binding 的双身份是经 Workflow 检查的采集来源；参数化证明按当前 case 资源重建。
            # 将来源 owner 当成模板适用范围，会令同动作的其他合法 owner 永远缺证明。
            if binding is None or effect is None:
                gap("EFFECT_VERDICT_PROOF_REQUIRED", permission, effect_id)
                continue
            proof = derive_effect_proof(effect, binding, resource.actual_resource_id, prepared.observer_capabilities)
            if proof.level != "VERDICT_REQUIRED":
                gap("EFFECT_VERDICT_PROOF_REQUIRED", permission, effect_id)
            proofs.append(proof)
        if {item.effect_id for item in proofs if item.level == "VERDICT_REQUIRED"} != set(effects):
            return None
        recovery = None
        if prepared.recovery is not None:
            binding = prepared.recovery
            # 恢复模板含 case_resource_id，实际恢复仍需由执行器按当前资源核实基线。
            recovery = RecoveryReference(recording_id=binding.source_recording_id,
                draft_revision=binding.source_draft_revision, draft_sha256=binding.source_draft_sha256,
                step_id=binding.step_id, binding_fingerprint=binding.binding_fingerprint,
                request_template_fingerprint=content_hash("RecordedRequestTemplate", binding.request_template.model_dump(mode="json")))
        frozen = FrozenPermission.model_validate_json(permission.model_dump_json(include=set(FrozenPermission.model_fields)), strict=True)
        payload = dict(permission=frozen, subject_test_identity_id=subject.identity_id,
            subject_actor_id=subject.actor_id, subject_actor_revision=subject.actor_revision,
            subject_identity_fingerprint=subject.identity_fingerprint, resource_owner_test_identity_id=owner.identity_id,
            resource_owner_actor_id=owner.actor_id, resource_owner_actor_revision=owner.actor_revision,
            owner_identity_fingerprint=owner.identity_fingerprint, resource_id=resource.actual_resource_id,
            resource_binding_fingerprint=resource.binding_fingerprint,
            execution=ExecutionAssetReference(flow_id=execution.flow_id, flow_sha256=execution.flow_sha256,
                                               execution_binding_fingerprint=execution.binding_fingerprint),
            protected_effect_ids=tuple(sorted(effects)), proof_requirements=tuple(proofs), recovery=recovery,
            source_fingerprint=source_fingerprint, config_fingerprint=config_fingerprint)
        raw = {key: value.model_dump(mode="json") if isinstance(value, WireModel) else
               [item.model_dump(mode="json") for item in value] if key == "proof_requirements" else value
               for key, value in payload.items()}
        case_id = "case_" + content_hash("CheckCase", {"action_id": action.action_id, "revision": action.revision, "facts": raw})[:32]
        roles = tuple(sorted(set((role, *(() if case_id not in cases else cases[case_id].roles)))))
        try:
            case = CheckCase(case_id=case_id, roles=roles, **payload)
        except ValueError:
            gap("CHECK_TWIN_INVARIANT_REQUIRED", permission)
            return None
        cases[case_id] = case
        return case

    for permission in sorted(prepared.permissions, key=lambda item: item.intent_id):
        if permission.expectation.value == "ALLOW":
            make_case(permission, permission.protected_effect_ids, CaseRole.ALLOW_REGRESSION)
    for control in prepared.assurance.allow_controls:
        deny_permission = permissions[control.deny_permission.intent_id]
        deny = make_case(deny_permission, control.protected_effect_ids, CaseRole.DENY_CHALLENGE)
        if control.resolved_allow_permission is None:
            continue
        allow_permission = permissions[control.resolved_allow_permission.intent_id]
        allow = make_case(allow_permission, control.protected_effect_ids, CaseRole.ALLOW_CONTROL)
        if deny is None or allow is None:
            continue
        if case_invariants(deny) != case_invariants(allow):
            gap("CHECK_TWIN_INVARIANT_REQUIRED", deny_permission)
            continue
        raw = dict(deny_case_id=deny.case_id, allow_case_id=allow.case_id,
            selected_allow_permission=control.resolved_allow_permission.model_dump(mode="json"),
            protected_effect_ids=control.protected_effect_ids, invariants=case_invariants(deny).model_dump(mode="json"))
        raw["twin_id"] = "twin_" + content_hash("CheckTwinIdentity", raw)[:32]
        raw["fingerprint"] = content_hash("CheckTwin", raw)
        import json
        twins.append(CheckTwin.model_validate_json(json.dumps(raw), strict=True))
    return ActionCheckPlan(action_id=action.action_id, action_revision=action.revision,
        action_semantic_fingerprint=action.semantic_fingerprint,
        cases=tuple(cases[key] for key in sorted(cases)), twins=tuple(sorted(twins, key=lambda item: item.twin_id)),
        gaps=tuple(sorted(gaps, key=lambda item: (item.reason, item.intent_id or "", item.effect_id or ""))))
