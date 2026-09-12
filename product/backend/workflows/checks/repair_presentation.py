# 从已验证的冻结包投影原题义务与本轮结果；不判定修复状态、不访问当前业务数据。
from __future__ import annotations

from typing import Literal

from product.backend.core.check_repair import CurrentRepairContract, repair_case_identity, repair_context
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import CaseVerdict
from product.protocols.execution_v3 import WireModel


class RepairComparisonRow(WireModel):
    role: Literal["DENY", "SELECTED_ALLOW", "REGRESSION"]
    source_case_id: str
    action_label: str
    subject_label: str | None
    resource_owner_label: str | None
    resource_id: str
    effect_labels: tuple[str, ...]
    before_verdict: CaseVerdict
    before_evidence_refs: tuple[str, ...]
    after_run_id: str | None = None
    after_case_id: str | None = None
    after_verdict: CaseVerdict | None = None
    after_evidence_refs: tuple[str, ...] = ()
    match_status: Literal["NOT_AVAILABLE", "MATCHED", "NOT_FOUND", "AMBIGUOUS"]


def build_repair_comparison(contract: CurrentRepairContract, source, current=None) -> tuple[RepairComparisonRow, ...]:
    """调用者先通过严格 Reader；关联诊断只复制结果，不替代原题复验与证据标准核验。"""
    if source.result.run_id != contract.source_run_id or source.request.project_id != contract.project_id:
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "原题修复要求无法从已发布事实重建")
    source_cases = {case.case_id: (action, case) for action in source.request.actions for case in action.cases}
    source_results = {item.case_id: item for item in source.result.case_results}
    configs = {item.action_id: item for item in source.bundle.actions}
    identities = {item.identity_id: item for item in source.bundle.identities}
    available = current is not None and (
        current.result.run_id != contract.source_run_id
        and current.request.project_id == contract.project_id
        and current.request.change_context is not None
        and current.request.repair_context == repair_context(contract)
    )
    candidates, current_results = {}, {}
    if available:
        for action in current.request.actions:
            for case in action.cases:
                candidates.setdefault(repair_case_identity(action, case).fingerprint(), []).append(case)
        current_results = {item.case_id: item for item in current.result.case_results}
    rows = []
    # 每项义务独立保留；同一 Case 同时承担控制与回归时不能隐式合并角色。
    requirements = (("DENY", contract.deny), ("SELECTED_ALLOW", contract.selected_control),
                    *(("REGRESSION", item) for item in contract.regressions))
    for role, requirement in requirements:
        try:
            action, case = source_cases[requirement.source_case_id]
            before = source_results[requirement.source_case_id]
            config = configs[action.action_id]
            subject = identities[case.subject_test_identity_id]
            owner = identities[case.resource_owner_test_identity_id]
        except KeyError:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "原题修复要求无法从已发布事实重建") from None
        labels = []
        for effect_id in requirement.identity.protected_effect_ids:
            # 同一 Effect 的重复证明只去重相同标签；缺失标签不从 live 配置或名称补全。
            labels.extend(dict.fromkeys(proof.business_label for proof in config.proofs if proof.effect_id == effect_id))
        matches = candidates.get(requirement.identity.fingerprint(), [])
        after = current_results.get(matches[0].case_id) if len(matches) == 1 else None
        match_status = ("NOT_AVAILABLE" if not available else "AMBIGUOUS" if len(matches) > 1
                        else "MATCHED" if after is not None else "NOT_FOUND")
        rows.append(RepairComparisonRow(role=role, source_case_id=case.case_id,
            action_label=config.display_name, subject_label=subject.label, resource_owner_label=owner.label,
            resource_id=case.resource_id, effect_labels=tuple(labels), before_verdict=before.verdict,
            before_evidence_refs=before.evidence_ids, after_run_id=current.result.run_id if available else None,
            after_case_id=None if after is None else after.case_id,
            after_verdict=None if after is None else after.verdict,
            after_evidence_refs=() if after is None else after.evidence_ids, match_status=match_status))
    return tuple(rows)
