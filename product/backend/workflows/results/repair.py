# =============================================================================
# 修复要求重建与独立复验
#
# 定位
#   从已发布 BLOCK、Finding、冻结执行请求和 Evidence 重建唯一 RepairContract，并核验后续同考题 Run。
#
# 职责
#   重建修复要求｜校验 Agent repair 引用｜冻结复验上下文｜形成非 Verdict 的复验三态。
#
# 边界
#   不读取 live 权限账本或目标现场，不建议代码补丁，不改变 Finding、Evidence、Verdict 或权限真源。
#
# 调用链
#   Result / MCP / SourceChange / Check → RepairContractService → PublishedResultReader
# =============================================================================

from __future__ import annotations

import hashlib
import json
from typing import Any

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import CaseVerdict, RunVerdict
from product.backend.core.repair import (
    RepairAllowControlIdentity,
    RepairContract,
    RepairContractReference,
    RepairEvidenceStandard,
    RepairIntentIdentity,
    RepairRequirementView,
    RepairVerification,
    RepairVerificationStatus,
    repair_contract_fingerprint,
)
from product.backend.core.verification.continuity import (
    AuthorizationContinuityState,
    assess_authorization_continuity,
)
from product.backend.core.verification.differential import TwinExecutionRole
from product.backend.core.verification.facts import ObservedEffect
from product.backend.core.verification.permissions import PermissionExpectation
from product.backend.workflows.results.presentation import locate_published_breakpoints
from product.backend.workflows.results.trace import build_execution_traces
from product.protocols.execution_request import (
    PermissionPolicySnapshotEntry,
    PersistedExecutionRequest,
    RepairVerificationContext,
)


class RepairContractService:
    """RepairContract 只重建冻结事实；调用顺序不能赋予 Agent 审批权。"""

    def __init__(self, reader, findings) -> None:
        self._reader = reader
        self._findings = findings

    def get(self, source_run_id: str, source_finding_id: str) -> RepairContract:
        view = self._reader.read(source_run_id)
        request = self._reader.execution_request(view)
        finding = self._finding(source_run_id, source_finding_id)
        result = view.publication.result
        if result.verdict is not RunVerdict.BLOCK:
            raise JiejianError(
                ErrorCode.STATE_PRECONDITION,
                "只有已发布且完整性通过的权限问题结果才能形成修复要求",
            )
        occurrence = finding["occurrence"]
        if occurrence["verdict"] != CaseVerdict.VULNERABLE.value:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "当前 Finding 不是已确认权限问题")
        evidence_refs = set(occurrence["evidence_refs"])
        deny_candidates = tuple(
            item
            for item in result.evidence
            if item.evidence_id in evidence_refs
            and item.verdict is CaseVerdict.VULNERABLE
            and item.twin_role is TwinExecutionRole.DENY_VARIANT
            and item.twin_snapshot is not None
        )
        if len(deny_candidates) != 1:
            raise JiejianError(
                ErrorCode.STATE_PRECONDITION,
                "当前 Finding 无法唯一对应一个冻结拒绝考题",
            )
        deny_evidence = deny_candidates[0]
        twin = deny_evidence.twin_snapshot
        assert twin is not None
        allow_candidates = tuple(
            item
            for item in result.evidence
            if item.twin_role is TwinExecutionRole.ALLOW_CONTROL
            and item.twin_snapshot == twin
        )
        if len(allow_candidates) != 1 or allow_candidates[0].verdict is not CaseVerdict.SAFE:
            raise JiejianError(
                ErrorCode.STATE_PRECONDITION,
                "原检查缺少成功的合法功能控制，不能形成修复要求",
            )
        allow_evidence = allow_candidates[0]
        target_intent = self._policy_entry(
            request,
            twin.deny_case.action_id,
            twin.deny_case.subject_id,
            PermissionExpectation.DENY,
        )
        allow_intent = self._policy_entry(
            request,
            twin.allow_case.action_id,
            twin.allow_case.subject_id,
            PermissionExpectation.ALLOW,
        )
        contract = request.project_snapshot.contract
        action = next(
            item for item in contract.actions if item.action_id == twin.invariant.action_id
        )
        continuity = assess_authorization_continuity(
            contract,
            twin,
            tuple(deny_evidence.security_effect_facts),
        )
        if continuity.state is not AuthorizationContinuityState.ORPHAN_EFFECT_CONFIRMED:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "当前 Finding 没有已确认的孤儿业务后果")
        evidence_items = tuple(result.evidence)
        traces = build_execution_traces(request.project_snapshot, evidence_items)
        breakpoints = locate_published_breakpoints(
            request.project_snapshot,
            evidence_items,
            {(item.case_id, item.action_id): item for item in traces},
        )
        breakpoint = breakpoints.get((twin.deny_case.case_id, twin.deny_case.action_id))
        if breakpoint is None:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "当前 Finding 缺少可冻结的断裂诊断")
        original_intents = tuple(
            sorted(
                (
                    _intent_identity(target_intent),
                    _intent_identity(allow_intent),
                ),
                key=lambda item: item.intent_id,
            )
        )
        key_evidence = _evidence_standard(allow_evidence, deny_evidence)
        fields: dict[str, Any] = {
            "source_run_id": source_run_id,
            "source_finding_id": source_finding_id,
            "project_id": view.run.project_id,
            "original_policy_epoch": request.permission_policy.policy_epoch,
            "intent": _intent_identity(target_intent),
            "original_intents": original_intents,
            "deny_action_id": twin.deny_case.action_id,
            "deny_subject_id": twin.deny_case.subject_id,
            "resource_ids": tuple(sorted(twin.deny_case.resource_ids)),
            "resource_relation": tuple(sorted(finding["finding"]["identity"]["resource_relation"])),
            "protected_effect_ids": tuple(sorted(action.effect_ids)),
            "allow_control": RepairAllowControlIdentity(
                intent=_intent_identity(allow_intent),
                action_id=twin.allow_case.action_id,
                subject_id=twin.allow_case.subject_id,
                case_fingerprint=twin.allow_case.fingerprint,
            ),
            "key_evidence": key_evidence,
            "authorization_continuity_state": continuity.state.value,
            "orphan_effect_ids": tuple(
                sorted({item.effect_id for item in continuity.confirmed_effects})
            ),
            "primary_breakpoint": (
                None if breakpoint.breakpoint_type is None else breakpoint.breakpoint_type.value
            ),
            "breakpoint_precision": breakpoint.precision.value,
            "amplifier_types": tuple(sorted(item.value for item in breakpoint.amplifier_types)),
            "must_disappear": (
                f"{target_intent.subject_display_name}不得再对"
                f"{target_intent.resource_owner_display_name}的资源执行"
                f"{target_intent.action_display_name}并产生受保护业务后果。"
            ),
            "must_remain": (
                f"{allow_intent.subject_display_name}仍然能够对"
                f"{allow_intent.resource_owner_display_name}的资源执行"
                f"{allow_intent.action_display_name}。"
            ),
            "must_not_change": tuple(
                sorted(
                    (
                        f"{target_intent.subject_display_name}原来的拒绝权限",
                        "用于确认最终业务后果的关键证据要求",
                    )
                )
            ),
        }
        fields["repair_fingerprint"] = repair_contract_fingerprint(fields)
        return RepairContract(**fields)

    def for_run(self, source_run_id: str) -> RepairContract:
        findings = self._findings.findings_for_run(source_run_id)
        vulnerable = tuple(
            item
            for item in findings
            if item["occurrence"]["verdict"] == CaseVerdict.VULNERABLE.value
        )
        if len(vulnerable) != 1:
            raise JiejianError(
                ErrorCode.STATE_PRECONDITION,
                "当前结果必须唯一对应一个可验证的修复要求",
            )
        return self.get(source_run_id, vulnerable[0]["finding"]["finding_id"])

    def verify_reference(
        self,
        project_id: str,
        reference: RepairContractReference,
    ) -> RepairContract:
        contract = self.get(reference.source_run_id, reference.source_finding_id)
        if contract.project_id != project_id or contract.reference != reference:
            raise JiejianError(
                ErrorCode.STATE_PRECONDITION,
                "修复要求引用已经失效，请重新读取权威修复要求",
            )
        return contract

    def context(
        self,
        project_id: str,
        reference: RepairContractReference,
        permission_policy,
    ) -> RepairVerificationContext:
        contract = self.verify_reference(project_id, reference)
        current = {
            item.intent_id: (item.revision, item.intent_hash)
            for item in permission_policy.entries
        }
        if permission_policy.policy_epoch != contract.original_policy_epoch or any(
            item.intent_id not in current
            or current[item.intent_id] != (item.revision, item.intent_hash)
            for item in contract.original_intents
        ):
            raise JiejianError(
                ErrorCode.STATE_PRECONDITION,
                "原权限要求已经改变，请按新权限重新形成检查。",
            )
        return RepairVerificationContext(
            reference=contract.reference,
            original_policy_epoch=contract.original_policy_epoch,
            target_intent=contract.intent,
            original_intents=contract.original_intents,
            must_disappear_effect_ids=contract.protected_effect_ids,
            must_remain_allow_control=contract.allow_control,
            original_key_evidence=contract.key_evidence,
        )

    def requirement(self, source_run_id: str, source_finding_id: str) -> RepairRequirementView:
        contract = self.get(source_run_id, source_finding_id)
        return RepairRequirementView(
            reference=contract.reference,
            must_disappear=contract.must_disappear,
            must_remain=contract.must_remain,
            must_not_change=contract.must_not_change,
        )

    def verify_run(self, verification_run_id: str) -> RepairVerification | None:
        view = self._reader.read(verification_run_id)
        request = self._reader.execution_request(view)
        context = request.repair_context
        if context is None:
            return None
        self.verify_reference(view.run.project_id, context.reference)
        current = {item.intent_id: item for item in request.permission_policy.entries}
        if request.permission_policy.policy_epoch != context.original_policy_epoch or any(
            (item.intent_id not in current)
            or current[item.intent_id].revision != item.revision
            or current[item.intent_id].intent_hash != item.intent_hash
            for item in context.original_intents
        ):
            return _verification(
                context.reference,
                verification_run_id,
                RepairVerificationStatus.INCONCLUSIVE,
                "原权限要求已经改变，请按新权限重新形成检查。",
                "ORIGINAL_PERMISSION_INTENT_CHANGED",
            )
        target = current[context.target_intent.intent_id]
        allow = current[context.must_remain_allow_control.intent.intent_id]
        result = view.publication.result
        deny_evidence = _matching_evidence(
            result.evidence,
            target,
            TwinExecutionRole.DENY_VARIANT,
        )
        allow_evidence = _matching_evidence(
            result.evidence,
            allow,
            TwinExecutionRole.ALLOW_CONTROL,
        )
        if deny_evidence is None or allow_evidence is None:
            return _verification(
                context.reference,
                verification_run_id,
                RepairVerificationStatus.INCONCLUSIVE,
                "本次检查没有形成完整的原拒绝考题与合法功能控制证据。",
                "REPAIR_PAIR_EVIDENCE_MISSING",
            )
        current_standard = _evidence_standard(allow_evidence, deny_evidence)
        if not set(context.original_key_evidence.requirement_ids).issubset(
            current_standard.requirement_ids
        ):
            return _verification(
                context.reference,
                verification_run_id,
                RepairVerificationStatus.NOT_VERIFIED,
                "关键证据要求已经降低，不能确认修复。",
                "KEY_EVIDENCE_STANDARD_LOWERED",
            )
        original_scope_standard = _evidence_standard(
            allow_evidence,
            deny_evidence,
            requirement_ids=context.original_key_evidence.requirement_ids,
        )
        if original_scope_standard.fingerprint != context.original_key_evidence.fingerprint:
            return _verification(
                context.reference,
                verification_run_id,
                RepairVerificationStatus.NOT_VERIFIED,
                "关键证据要求已经改变，不能确认修复。",
                "KEY_EVIDENCE_STANDARD_CHANGED",
            )
        action = next(
            (
                item
                for item in request.project_snapshot.contract.actions
                if item.action_id == target.action_candidate_id
            ),
            None,
        )
        if action is None or not set(context.must_disappear_effect_ids).issubset(action.effect_ids):
            return _verification(
                context.reference,
                verification_run_id,
                RepairVerificationStatus.NOT_VERIFIED,
                "原受保护业务后果已经从检查定义中删除，不能确认修复。",
                "PROTECTED_EFFECT_REMOVED",
            )
        if allow_evidence.verdict is CaseVerdict.INCONCLUSIVE or deny_evidence.verdict is CaseVerdict.INCONCLUSIVE:
            return _verification(
                context.reference,
                verification_run_id,
                RepairVerificationStatus.INCONCLUSIVE,
                "本次修复复验的业务后果或合法功能证据不足。",
                "REPAIR_EVIDENCE_INCOMPLETE",
            )
        if allow_evidence.verdict is not CaseVerdict.SAFE:
            return _verification(
                context.reference,
                verification_run_id,
                RepairVerificationStatus.NOT_VERIFIED,
                "违规后果可能消失，但合法功能没有保持。",
                "ALLOW_CONTROL_BROKEN",
            )
        relevant_facts = tuple(
            item
            for item in deny_evidence.security_effect_facts
            if item.effect_id in context.must_disappear_effect_ids
        )
        if any(item.state is ObservedEffect.CONFIRMED for item in relevant_facts):
            return _verification(
                context.reference,
                verification_run_id,
                RepairVerificationStatus.NOT_VERIFIED,
                "原违规业务后果仍然存在。",
                "DENY_EFFECT_STILL_PRESENT",
            )
        if (
            len({item.effect_id for item in relevant_facts})
            != len(context.must_disappear_effect_ids)
            or deny_evidence.verdict is not CaseVerdict.SAFE
        ):
            return _verification(
                context.reference,
                verification_run_id,
                RepairVerificationStatus.INCONCLUSIVE,
                "原违规业务后果是否完整消失仍缺少充分证据。",
                "DENY_EFFECT_EVIDENCE_INCOMPLETE",
            )
        return _verification(
            context.reference,
            verification_run_id,
            RepairVerificationStatus.VERIFIED,
            "原违规业务后果已被完整证明消失，合法功能保持，权限要求未改变且关键证据标准未降低。",
            "REPAIR_REQUIREMENTS_SATISFIED",
        )

    def _finding(self, run_id: str, finding_id: str) -> dict[str, Any]:
        matches = tuple(
            item
            for item in self._findings.findings_for_run(run_id)
            if item["finding"]["finding_id"] == finding_id
        )
        if len(matches) != 1:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "当前 Run 中不存在该 Finding")
        return matches[0]

    @staticmethod
    def _policy_entry(
        request: PersistedExecutionRequest,
        action_id: str,
        subject_id: str,
        expectation: PermissionExpectation,
    ) -> PermissionPolicySnapshotEntry:
        matches = tuple(
            item
            for item in request.permission_policy.entries
            if item.action_candidate_id == action_id
            and item.subject_test_identity_id == subject_id
            and item.expectation is expectation
            and item.relation is not None
            and item.subject_display_name is not None
            and item.action_display_name is not None
            and item.resource_owner_display_name is not None
        )
        if len(matches) != 1:
            raise JiejianError(
                ErrorCode.STATE_PRECONDITION,
                "冻结结果无法唯一关联原权限要求",
            )
        return matches[0]


def _intent_identity(entry: PermissionPolicySnapshotEntry) -> RepairIntentIdentity:
    return RepairIntentIdentity(
        intent_id=entry.intent_id,
        revision=entry.revision,
        intent_hash=entry.intent_hash,
    )


def _evidence_standard(
    allow_evidence,
    deny_evidence,
    *,
    requirement_ids: tuple[str, ...] | None = None,
) -> RepairEvidenceStandard:
    available_requirements = tuple(
        sorted(
            set(allow_evidence.case_snapshot.required_observations)
            | set(deny_evidence.case_snapshot.required_observations)
        )
    )
    requirements = available_requirements if requirement_ids is None else requirement_ids
    selected = set(requirements)

    def bindings(evidence) -> list[dict[str, Any]]:
        return sorted(
            (
                item.model_dump(mode="json")
                for item in evidence.requirement_bindings
                if item.requirement_id in selected
            ),
            key=lambda item: (item["requirement_id"], json.dumps(item, sort_keys=True)),
        )

    payload = {
        "requirements": requirements,
        "allow_bindings": bindings(allow_evidence),
        "deny_bindings": bindings(deny_evidence),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return RepairEvidenceStandard(
        requirement_ids=requirements,
        fingerprint=hashlib.sha256(encoded).hexdigest(),
    )


def _matching_evidence(evidence_items, entry, role):
    matches = tuple(
        item
        for item in evidence_items
        if item.twin_role is role
        and item.case_snapshot.action_id == entry.action_candidate_id
        and item.case_snapshot.subject_id == entry.subject_test_identity_id
        and all(value is entry.expectation for value in item.case_snapshot.expectations)
    )
    return matches[0] if len(matches) == 1 else None


def _verification(reference, run_id, status, message, reason_code) -> RepairVerification:
    return RepairVerification(
        reference=reference,
        verification_run_id=run_id,
        status=status,
        message=message,
        reason_codes=(reason_code,),
    )


__all__ = ["RepairContractService"]
