# 原题修复的纯语义身份、证据标准和只读复验投影；不执行目标或改写已发布 Verdict。
from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from product.backend.core.lifecycle import CaseVerdict, RunVerdict
from product.backend.core.verification.breakpoints import BreakpointResult
from product.backend.core.verification.checks import project_check_effect_facts
from product.protocols.execution_v3 import (
    ActorId, EffectId, FrozenPermission, Hash, IdentityId, LogicalId, PermissionReference,
    RepairContext, WireModel, content_hash,
)


class CurrentRepairReference(WireModel):
    source_run_id: LogicalId
    source_case_id: LogicalId
    repair_fingerprint: Hash


class RepairCaseIdentity(WireModel):
    action_id: LogicalId
    action_revision: int = Field(ge=1)
    action_semantic_fingerprint: Hash
    permission: FrozenPermission
    subject_test_identity_id: IdentityId
    subject_actor_id: ActorId
    subject_actor_revision: int = Field(ge=1)
    subject_identity_fingerprint: Hash
    resource_owner_test_identity_id: IdentityId
    resource_owner_actor_id: ActorId
    resource_owner_actor_revision: int = Field(ge=1)
    owner_identity_fingerprint: Hash
    resource_id: str = Field(min_length=1, max_length=256)
    protected_effect_ids: tuple[EffectId, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def validate_effect_set(self):
        if tuple(sorted(set(self.protected_effect_ids))) != self.protected_effect_ids:
            raise ValueError("repair effect set")
        return self

    def fingerprint(self) -> str:
        return content_hash("RepairCaseIdentity", self.model_dump(mode="json"))


def repair_case_identity(action, case) -> RepairCaseIdentity:
    """技术重录与源码变化不改变原题；账号、归属、权限及效果变化必须改变身份。"""
    values = {name: getattr(case, name) for name in RepairCaseIdentity.model_fields
        if name not in {"action_id", "action_revision", "action_semantic_fingerprint"}}
    return RepairCaseIdentity(action_id=action.action_id, action_revision=action.action_revision,
        action_semantic_fingerprint=action.action_semantic_fingerprint, **values)


def repair_evidence_standards(action, case, bundle) -> tuple[str, ...]:
    """每条必需证明单独冻结真实读取语义；技术绑定和展示标签不参与等价。"""
    configured = next(item for item in bundle.actions if item.action_id == action.action_id)
    proofs = {item.binding_fingerprint: item for item in configured.proofs}
    identities = {item.identity_id: item for item in bundle.identities}
    observers = {item.observer_id: item for item in bundle.observers}
    standards = []
    for requirement in case.proof_requirements:
        if requirement.level != "VERDICT_REQUIRED":
            continue
        proof = proofs[requirement.binding_fingerprint]
        identity = identities[proof.observation_identity_id]
        verification = identity.verification
        if verification is None or proof.rule == "RECORDED_SUPPORT":
            raise ValueError("repair requires independently verified decisive standard")
        payload = {name:getattr(proof,name) for name in (
            "effect_id", "effect_kind", "expected_state", "protected_projection", "rule",
            "observation_identity_id", "exclusive_resource_window", "descriptor_fingerprint")}
        payload["identity_verification"] = verification.model_dump(mode="json")
        payload["request"] = None if proof.request is None else proof.request.model_dump(mode="json")
        payload["observer"] = None if proof.observer_id is None else observers[proof.observer_id].model_dump(mode="json")
        standards.append(content_hash("RepairEvidenceStandard", payload))
    if not standards or len(set(standards)) != len(standards):
        raise ValueError("repair decisive standards missing or duplicated")
    return tuple(sorted(standards))


class RepairCaseRequirement(WireModel):
    source_case_id: LogicalId
    identity: RepairCaseIdentity
    evidence_standard_fingerprints: tuple[Hash, ...] = Field(min_length=1, max_length=48)
    evidence_refs: tuple[str, ...] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def validate_sets(self):
        if tuple(sorted(set(self.evidence_standard_fingerprints))) != self.evidence_standard_fingerprints:
            raise ValueError("repair standards must be sorted and unique")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("repair evidence refs must be unique")
        return self


class CurrentRepairContract(WireModel):
    project_id: LogicalId
    source_run_id: LogicalId
    source_case_id: LogicalId
    original_policy_epoch: int = Field(ge=0)
    original_intents: tuple[PermissionReference, ...] = Field(min_length=1, max_length=4096)
    deny: RepairCaseRequirement
    selected_control: RepairCaseRequirement
    regressions: tuple[RepairCaseRequirement, ...] = Field(max_length=4096)
    breakpoint: BreakpointResult | None
    repair_fingerprint: Hash

    @model_validator(mode="after")
    def validate_contract(self):
        if self.source_case_id != self.deny.source_case_id or self.deny.identity.permission.expectation != "DENY":
            raise ValueError("repair source must be the frozen deny case")
        if self.selected_control.identity.permission.expectation != "ALLOW":
            raise ValueError("repair requires selected allow control")
        keys = tuple(item.identity.fingerprint() for item in self.regressions)
        if keys != tuple(sorted(set(keys))) or any(item.identity.permission.expectation != "ALLOW" for item in self.regressions):
            raise ValueError("repair regression set")
        refs = tuple((item.intent_id,item.revision,item.intent_hash) for item in self.original_intents)
        if refs != tuple(sorted(set(refs))):
            raise ValueError("repair permission set")
        payload = self.model_dump(mode="json",exclude={"repair_fingerprint"})
        if self.repair_fingerprint != content_hash("CurrentRepairContract",payload):
            raise ValueError("repair contract identity")
        if len(self.model_dump_json().encode("utf-8")) > 1_048_576:
            raise ValueError("repair contract exceeds byte budget")
        return self

    def reference(self) -> CurrentRepairReference:
        return CurrentRepairReference(source_run_id=self.source_run_id,source_case_id=self.source_case_id,
            repair_fingerprint=self.repair_fingerprint)


def repair_context(contract: CurrentRepairContract) -> RepairContext:
    identity = contract.deny.identity
    permission = contract.selected_control.identity.permission
    return RepairContext(repair_reference=contract.repair_fingerprint,source_run_id=contract.source_run_id,
        original_policy_epoch=contract.original_policy_epoch,original_intents=contract.original_intents,
        selected_allow_permission=PermissionReference(intent_id=permission.intent_id,revision=permission.revision,intent_hash=permission.intent_hash),
        resource_id=identity.resource_id,resource_owner_test_identity_id=identity.resource_owner_test_identity_id,
        owner_identity_fingerprint=identity.owner_identity_fingerprint,must_disappear_effect_ids=identity.protected_effect_ids,
        original_evidence_standard_fingerprints=contract.deny.evidence_standard_fingerprints,
        allow_regression_case_fingerprints=tuple(item.identity.fingerprint() for item in contract.regressions))


def current_request_permissions(request) -> tuple[PermissionReference, ...]:
    values = {(case.permission.intent_id,case.permission.revision,case.permission.intent_hash)
        for action in request.actions for case in action.cases}
    return tuple(PermissionReference(intent_id=identity,revision=revision,intent_hash=digest)
        for identity,revision,digest in sorted(values))


class CurrentRepairVerification(WireModel):
    repair_reference: Hash
    source_run_id: LogicalId
    run_id: LogicalId
    status: Literal["VERIFIED", "NOT_VERIFIED", "INCONCLUSIVE", "STALE"]
    reason_codes: tuple[str, ...] = Field(max_length=16)


def verify_current_repair(contract, *, request, bundle, result, evidence, expected_change_context) -> CurrentRepairVerification:
    """只派生修复事实；两份发布包完整性由调用方 Reader 检验，不在此重算 Verdict。"""
    def answer(status, reason):
        return CurrentRepairVerification(repair_reference=contract.repair_fingerprint,
            source_run_id=contract.source_run_id,run_id=result.run_id,status=status,reason_codes=(reason,))
    if request.policy_epoch != contract.original_policy_epoch or current_request_permissions(request) != contract.original_intents:
        return answer("STALE","REPAIR_POLICY_CHANGED")
    if (result.run_id == contract.source_run_id or request.project_id != contract.project_id
        or request.repair_context != repair_context(contract) or expected_change_context is None
        or request.change_context != expected_change_context):
        return answer("INCONCLUSIVE","REPAIR_CONTEXT_MISMATCH")
    candidates = {}
    for action in request.actions:
        for case in action.cases:
            candidates.setdefault(repair_case_identity(action,case).fingerprint(),[]).append((action,case))
    results = {item.case_id:item for item in result.case_results}
    documents = {item.evidence_id:item for item in evidence}
    matches = candidates.get(contract.deny.identity.fingerprint(),[])
    # 禁止效果仍出现优先于其他路径观察缺口，但身份与原题匹配仍需可信。
    if len(matches) == 1:
        _, case = matches[0]
        case_result = results.get(case.case_id)
        if case_result is not None:
            outcome = case_result.outcome
            observations = tuple(observation for ref in case_result.evidence_ids if ref in documents
                for observation in documents[ref].observations)
            facts = project_check_effect_facts(case,observations)
            if (outcome.actual_identity_status == "MATCH" and outcome.run_correlated and outcome.resource_correlated
                and any(fact.state == "CONFIRMED" and fact.complete and fact.reliable and fact.correlated and fact.authoritative for fact in facts)):
                return answer("NOT_VERIFIED","REPAIR_FORBIDDEN_EFFECT_REMAINS")
    for requirement in (contract.deny,contract.selected_control,*contract.regressions):
        matches = candidates.get(requirement.identity.fingerprint(),[])
        if len(matches) != 1:
            return answer("INCONCLUSIVE","REPAIR_CASE_NOT_UNIQUELY_MATCHED")
        action,case = matches[0]
        current = results.get(case.case_id)
        if current is None or current.verdict is not CaseVerdict.SAFE:
            return answer("INCONCLUSIVE","REPAIR_REQUIRED_CASE_NOT_SAFE")
        outcome = current.outcome
        if not (outcome.actual_identity_status == "MATCH" and outcome.baseline_trusted and outcome.recovery_verified
            and outcome.run_correlated and outcome.resource_correlated):
            return answer("INCONCLUSIVE","REPAIR_ATTRIBUTION_INCOMPLETE")
        try:
            standards = repair_evidence_standards(action,case,bundle)
        except (KeyError,ValueError,StopIteration):
            return answer("INCONCLUSIVE","REPAIR_STANDARD_UNAVAILABLE")
        if standards != requirement.evidence_standard_fingerprints:
            return answer("INCONCLUSIVE","REPAIR_STANDARD_CHANGED")
    if result.verdict is not RunVerdict.PASS:
        return answer("INCONCLUSIVE","REPAIR_CURRENT_RUN_NOT_PASS")
    return answer("VERIFIED","REPAIR_ORIGINAL_REQUIREMENTS_VERIFIED")
