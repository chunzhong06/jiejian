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
    RepairPathKind,
    RepairPathVerification,
    RepairRegressionControlIdentity,
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
        regression_controls = self._regression_controls(request, result.evidence)
        intent_by_id = {
            item.intent_id: item
            for item in (
                _intent_identity(target_intent),
                _intent_identity(allow_intent),
                *(item.intent for item in regression_controls),
            )
        }
        original_intents = tuple(
            sorted(intent_by_id.values(), key=lambda item: item.intent_id)
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
            "regression_controls": regression_controls,
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
                + "".join(
                    f"{item.subject_display_name}仍然能够执行{item.action_display_name}。"
                    for item in regression_controls
                )
            ),
            "must_not_change": tuple(
                sorted(
                    (
                        f"{target_intent.subject_display_name}原来的拒绝权限",
                        "原本允许的独立合法业务路径",
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
            must_remain_regression_controls=contract.regression_controls,
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
        pair_status, pair_message, pair_reason, pair_paths = _verify_pair(
            context,
            request,
            result.evidence,
            target,
            allow,
        )
        regression_paths = _verify_regression_controls(
            context,
            request,
            result.evidence,
            current,
        )
        path_results = tuple(
            sorted(
                (*pair_paths, *regression_paths),
                key=lambda item: (item.kind.value, item.action_id, item.subject_id),
            )
        )
        if pair_status is not RepairVerificationStatus.VERIFIED:
            return _verification(
                context.reference,
                verification_run_id,
                pair_status,
                pair_message,
                pair_reason,
                path_results,
            )
        broken = next(
            (item for item in regression_paths if item.status is RepairVerificationStatus.NOT_VERIFIED),
            None,
        )
        if broken is not None:
            return _verification(
                context.reference,
                verification_run_id,
                RepairVerificationStatus.NOT_VERIFIED,
                "原违规后果已经消失，但一条原本允许的业务路径被修坏。",
                "REGRESSION_CONTROL_BROKEN",
                path_results,
            )
        incomplete = next(
            (item for item in regression_paths if item.status is RepairVerificationStatus.INCONCLUSIVE),
            None,
        )
        if incomplete is not None:
            return _verification(
                context.reference,
                verification_run_id,
                RepairVerificationStatus.INCONCLUSIVE,
                "原违规后果已经消失，但独立合法业务路径仍缺少充分复验证据。",
                "REGRESSION_CONTROL_INCONCLUSIVE",
                path_results,
            )
        return _verification(
            context.reference,
            verification_run_id,
            RepairVerificationStatus.VERIFIED,
            "原违规业务后果已被完整证明消失，两条合法业务路径保持，权限要求未改变且关键证据标准未降低。",
            "REPAIR_REQUIREMENTS_SATISFIED",
            path_results,
        )

    def _regression_controls(
        self,
        request: PersistedExecutionRequest,
        evidence_items,
    ) -> tuple[RepairRegressionControlIdentity, ...]:
        """只冻结源 Run 已经以正式 SAFE 事实证明的独立 ALLOW 路径。"""

        controls: list[RepairRegressionControlIdentity] = []
        action_map = {item.action_id: item for item in request.project_snapshot.contract.actions}
        for evidence in evidence_items:
            case = evidence.case_snapshot
            if (
                evidence.twin_role is not None
                or evidence.verdict is not CaseVerdict.SAFE
                or not all(item is PermissionExpectation.ALLOW for item in case.expectations)
            ):
                continue
            intent = self._policy_entry(
                request,
                case.action_id,
                case.subject_id,
                PermissionExpectation.ALLOW,
            )
            action = action_map.get(case.action_id)
            if action is None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "独立合法业务路径缺少冻结动作")
            controls.append(
                RepairRegressionControlIdentity(
                    intent=_intent_identity(intent),
                    action_id=case.action_id,
                    subject_id=case.subject_id,
                    subject_display_name=intent.subject_display_name,
                    action_display_name=intent.action_display_name,
                    case_fingerprint=case.fingerprint,
                    protected_effect_ids=tuple(sorted(action.effect_ids)),
                    key_evidence=_control_evidence_standard(evidence),
                )
            )
        return tuple(
            sorted(
                controls,
                key=lambda item: (item.intent.intent_id, item.action_id, item.subject_id),
            )
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


def _control_evidence_standard(
    evidence,
    *,
    requirement_ids: tuple[str, ...] | None = None,
) -> RepairEvidenceStandard:
    available_requirements = tuple(sorted(set(evidence.case_snapshot.required_observations)))
    requirements = available_requirements if requirement_ids is None else requirement_ids
    selected = set(requirements)
    payload = {
        "requirements": requirements,
        "control_bindings": sorted(
            (
                item.model_dump(mode="json")
                for item in evidence.requirement_bindings
                if item.requirement_id in selected
            ),
            key=lambda item: (item["requirement_id"], json.dumps(item, sort_keys=True)),
        ),
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


def _matching_regression_evidence(evidence_items, entry):
    matches = tuple(
        item
        for item in evidence_items
        if item.twin_role is None
        and item.case_snapshot.action_id == entry.action_candidate_id
        and item.case_snapshot.subject_id == entry.subject_test_identity_id
        and all(value is PermissionExpectation.ALLOW for value in item.case_snapshot.expectations)
    )
    return matches[0] if len(matches) == 1 else None


def _path_result(
    kind: RepairPathKind,
    entry,
    status: RepairVerificationStatus,
    message: str,
    reason_code: str,
    evidence=None,
) -> RepairPathVerification:
    return RepairPathVerification(
        kind=kind,
        action_id=entry.action_candidate_id,
        subject_id=entry.subject_test_identity_id,
        subject_display_name=entry.subject_display_name or entry.subject_test_identity_id,
        action_display_name=entry.action_display_name or entry.action_candidate_id,
        status=status,
        message=message,
        evidence_refs=() if evidence is None else (evidence.evidence_id,),
        reason_codes=(reason_code,),
    )


def _pair_failure(target, allow, status, message, reason_code, deny, allow_evidence):
    return (
        status,
        message,
        reason_code,
        (
            _path_result(
                RepairPathKind.DENY_EFFECT_REMOVAL,
                target,
                status,
                message,
                reason_code,
                deny,
            ),
            _path_result(
                RepairPathKind.ALLOW_CONTROL,
                allow,
                status,
                message,
                reason_code,
                allow_evidence,
            ),
        ),
    )


def _verify_pair(context, request, evidence_items, target, allow):
    deny = _matching_evidence(evidence_items, target, TwinExecutionRole.DENY_VARIANT)
    allow_evidence = _matching_evidence(
        evidence_items,
        allow,
        TwinExecutionRole.ALLOW_CONTROL,
    )
    if deny is None or allow_evidence is None:
        return _pair_failure(
            target,
            allow,
            RepairVerificationStatus.INCONCLUSIVE,
            "本次检查没有形成完整的原拒绝考题与合法功能控制证据。",
            "REPAIR_PAIR_EVIDENCE_MISSING",
            deny,
            allow_evidence,
        )
    current_standard = _evidence_standard(allow_evidence, deny)
    if not set(context.original_key_evidence.requirement_ids).issubset(
        current_standard.requirement_ids
    ):
        return _pair_failure(
            target,
            allow,
            RepairVerificationStatus.NOT_VERIFIED,
            "关键证据要求已经降低，不能确认修复。",
            "KEY_EVIDENCE_STANDARD_LOWERED",
            deny,
            allow_evidence,
        )
    original_scope_standard = _evidence_standard(
        allow_evidence,
        deny,
        requirement_ids=context.original_key_evidence.requirement_ids,
    )
    if original_scope_standard.fingerprint != context.original_key_evidence.fingerprint:
        return _pair_failure(
            target,
            allow,
            RepairVerificationStatus.NOT_VERIFIED,
            "关键证据要求已经改变，不能确认修复。",
            "KEY_EVIDENCE_STANDARD_CHANGED",
            deny,
            allow_evidence,
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
        return _pair_failure(
            target,
            allow,
            RepairVerificationStatus.NOT_VERIFIED,
            "原受保护业务后果已经从检查定义中删除，不能确认修复。",
            "PROTECTED_EFFECT_REMOVED",
            deny,
            allow_evidence,
        )
    if allow_evidence.verdict is CaseVerdict.INCONCLUSIVE or deny.verdict is CaseVerdict.INCONCLUSIVE:
        return _pair_failure(
            target,
            allow,
            RepairVerificationStatus.INCONCLUSIVE,
            "本次修复复验的业务后果或合法功能证据不足。",
            "REPAIR_EVIDENCE_INCOMPLETE",
            deny,
            allow_evidence,
        )
    allow_path = _path_result(
        RepairPathKind.ALLOW_CONTROL,
        allow,
        (
            RepairVerificationStatus.VERIFIED
            if allow_evidence.verdict is CaseVerdict.SAFE
            else RepairVerificationStatus.NOT_VERIFIED
        ),
        (
            "合法业务控制仍然正常完成。"
            if allow_evidence.verdict is CaseVerdict.SAFE
            else "违规后果可能消失，但合法功能没有保持。"
        ),
        (
            "ALLOW_CONTROL_PRESERVED"
            if allow_evidence.verdict is CaseVerdict.SAFE
            else "ALLOW_CONTROL_BROKEN"
        ),
        allow_evidence,
    )
    relevant_facts = tuple(
        item
        for item in deny.security_effect_facts
        if item.effect_id in context.must_disappear_effect_ids
    )
    if any(item.state is ObservedEffect.CONFIRMED for item in relevant_facts):
        deny_status = RepairVerificationStatus.NOT_VERIFIED
        deny_message = "原违规业务后果仍然存在。"
        deny_reason = "DENY_EFFECT_STILL_PRESENT"
    elif (
        len({item.effect_id for item in relevant_facts})
        != len(context.must_disappear_effect_ids)
        or deny.verdict is not CaseVerdict.SAFE
    ):
        deny_status = RepairVerificationStatus.INCONCLUSIVE
        deny_message = "原违规业务后果是否完整消失仍缺少充分证据。"
        deny_reason = "DENY_EFFECT_EVIDENCE_INCOMPLETE"
    else:
        deny_status = RepairVerificationStatus.VERIFIED
        deny_message = "原违规业务后果已被完整证明消失。"
        deny_reason = "DENY_EFFECT_REMOVED"
    deny_path = _path_result(
        RepairPathKind.DENY_EFFECT_REMOVAL,
        target,
        deny_status,
        deny_message,
        deny_reason,
        deny,
    )
    if allow_path.status is RepairVerificationStatus.NOT_VERIFIED:
        return (
            RepairVerificationStatus.NOT_VERIFIED,
            "违规后果可能消失，但合法功能没有保持。",
            "ALLOW_CONTROL_BROKEN",
            (deny_path, allow_path),
        )
    if deny_status is not RepairVerificationStatus.VERIFIED:
        return (deny_status, deny_message, deny_reason, (deny_path, allow_path))
    return (
        RepairVerificationStatus.VERIFIED,
        "原违规业务后果已消失且合法功能保持。",
        "REPAIR_PAIR_SATISFIED",
        (deny_path, allow_path),
    )


def _verify_regression_controls(context, request, evidence_items, current):
    action_map = {item.action_id: item for item in request.project_snapshot.contract.actions}
    results: list[RepairPathVerification] = []
    for control in context.must_remain_regression_controls:
        entry = current[control.intent.intent_id]
        evidence = _matching_regression_evidence(evidence_items, entry)
        if evidence is None:
            results.append(
                _path_result(
                    RepairPathKind.REGRESSION_CONTROL,
                    entry,
                    RepairVerificationStatus.INCONCLUSIVE,
                    f"{control.subject_display_name}执行{control.action_display_name}的正式证据缺失。",
                    "REGRESSION_CONTROL_EVIDENCE_MISSING",
                )
            )
            continue
        current_standard = _control_evidence_standard(evidence)
        if not set(control.key_evidence.requirement_ids).issubset(
            current_standard.requirement_ids
        ):
            status = RepairVerificationStatus.NOT_VERIFIED
            message = "独立合法业务路径的关键证据要求已经降低。"
            reason = "REGRESSION_EVIDENCE_STANDARD_LOWERED"
        elif _control_evidence_standard(
            evidence,
            requirement_ids=control.key_evidence.requirement_ids,
        ).fingerprint != control.key_evidence.fingerprint:
            status = RepairVerificationStatus.NOT_VERIFIED
            message = "独立合法业务路径的关键证据要求已经改变。"
            reason = "REGRESSION_EVIDENCE_STANDARD_CHANGED"
        else:
            action = action_map.get(entry.action_candidate_id)
            facts = tuple(
                item
                for item in evidence.security_effect_facts
                if item.effect_id in control.protected_effect_ids
            )
            if action is None or not set(control.protected_effect_ids).issubset(action.effect_ids):
                status = RepairVerificationStatus.NOT_VERIFIED
                message = "独立合法业务路径的受保护后果已从检查定义中删除。"
                reason = "REGRESSION_PROTECTED_EFFECT_REMOVED"
            elif evidence.verdict is CaseVerdict.INCONCLUSIVE:
                status = RepairVerificationStatus.INCONCLUSIVE
                message = "独立合法业务路径仍缺少充分证据。"
                reason = "REGRESSION_CONTROL_EVIDENCE_INCOMPLETE"
            elif (
                evidence.verdict is not CaseVerdict.SAFE
                or {item.effect_id for item in facts} != set(control.protected_effect_ids)
                or any(item.state is not ObservedEffect.CONFIRMED for item in facts)
            ):
                status = RepairVerificationStatus.NOT_VERIFIED
                message = "独立合法业务路径没有保持正常。"
                reason = "REGRESSION_CONTROL_BROKEN"
            else:
                status = RepairVerificationStatus.VERIFIED
                message = "独立合法业务路径仍然正常完成。"
                reason = "REGRESSION_CONTROL_PRESERVED"
        results.append(
            _path_result(
                RepairPathKind.REGRESSION_CONTROL,
                entry,
                status,
                message,
                reason,
                evidence,
            )
        )
    return tuple(results)


def _verification(
    reference,
    run_id,
    status,
    message,
    reason_code,
    path_results=(),
) -> RepairVerification:
    return RepairVerification(
        reference=reference,
        verification_run_id=run_id,
        status=status,
        message=message,
        reason_codes=(reason_code,),
        path_results=path_results,
    )


__all__ = ["RepairContractService"]
