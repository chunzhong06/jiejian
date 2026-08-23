# =============================================================================
# Contract 审阅评估
#
# 定位
#   Candidate 合并结果进入治理版本前的可观察性与冲突门禁
#
# 职责
#   识别冲突｜检查 observer 覆盖｜生成确定性审阅结论
#
# 调用链
#   ContractGovernance → assess_contract → ContractReviewAssessment
# =============================================================================

from __future__ import annotations

from collections.abc import Sequence

from product.backend.core.contracts.models import ContractCandidate, ContractSourceType, ContractVersion
from product.backend.core.contracts.analysis.canonical import _issue, _issue_key, contract_analysis_sha256
from product.backend.core.contracts.analysis.merge import merge_candidates
from product.backend.core.contracts.analysis.models import AnalysisIssue, AnalysisReasonCode, AnalysisSeverity, ContractReviewAssessment


def assess_contract(
    contract: ContractVersion,
    *,
    candidates: Sequence[ContractCandidate] = (),
    source_issues: Sequence[AnalysisIssue] = (),
    available_observations: Sequence[str] = ("resource_state",),
    unexecutable_rule_ids: Sequence[str] = (),
) -> ContractReviewAssessment:
    """统一确定性审阅门禁；不产生 Finding/Verdict。"""

    merge = merge_candidates(candidates)
    issues = list(source_issues) + list(merge.issues)
    for candidate in candidates:
        if candidate.project_id != contract.project_id:
            issues.append(
                _issue(
                    AnalysisReasonCode.CONFLICTING_CANDIDATE,
                    AnalysisSeverity.BLOCKING,
                    candidate.candidate_id,
                    candidate_ids=(candidate.candidate_id,),
                    detail="candidate_project_mismatch",
                )
            )
    observation_set = set(available_observations)
    for rule in contract.snapshot.rules:
        missing = tuple(sorted(set(rule.required_observations) - observation_set))
        if missing:
            issues.append(
                _issue(
                    AnalysisReasonCode.OBSERVER_UNAVAILABLE,
                    AnalysisSeverity.BLOCKING,
                    rule.rule_id,
                    detail="required_observer_unavailable:" + ",".join(missing),
                )
            )
    for rule_id in sorted(set(unexecutable_rule_ids)):
        issues.append(
            _issue(
                AnalysisReasonCode.RULE_UNEXECUTABLE,
                AnalysisSeverity.BLOCKING,
                rule_id,
                detail="rule_marked_unexecutable",
            )
        )
    explicit = [item for item in candidates if item.source.source_type is not ContractSourceType.LLM]
    for llm in (item for item in candidates if item.source.source_type is ContractSourceType.LLM):
        for other in explicit:
            if set(llm.requirement_ids) & set(other.requirement_ids) and llm.suggestion != other.suggestion:
                issues.append(
                    _issue(
                        AnalysisReasonCode.LLM_REQUIREMENT_CONFLICT,
                        AnalysisSeverity.BLOCKING,
                        llm.suggestion.id,
                        candidate_ids=(llm.candidate_id, other.candidate_id),
                        requirement_ids=tuple(sorted(set(llm.requirement_ids) & set(other.requirement_ids))),
                        detail="llm_candidate_conflicts_with_explicit_requirement",
                    )
                )
    ordered = tuple(sorted(set(issues), key=_issue_key))
    blocking = tuple(item for item in ordered if item.severity is AnalysisSeverity.BLOCKING)
    warnings = tuple(item for item in ordered if item.severity is AnalysisSeverity.WARNING)
    body = {
        "project_id": contract.project_id,
        "contract_id": contract.contract_id,
        "version": contract.version,
        "status": contract.status,
        "blocking_issues": blocking,
        "warnings": warnings,
        "available_observations": tuple(sorted(observation_set)),
    }
    return ContractReviewAssessment(
        project_id=contract.project_id,
        contract_id=contract.contract_id,
        version=contract.version,
        status=contract.status,
        eligible=not blocking,
        blocking_issues=blocking,
        warnings=warnings,
        canonical_sha256=contract_analysis_sha256(body),
    )
