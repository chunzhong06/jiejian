# =============================================================================
# Contract Candidate 合并
#
# 定位
#   不同可信等级来源候选之间的确定性合并算法
#
# 职责
#   规范候选身份｜合并一致规则｜保留冲突和来源证据
#
# 调用链
#   Assessment / contract analysis workflow → merge_candidates → CandidateMergeResult
# =============================================================================

from __future__ import annotations

from collections.abc import Sequence

from product.backend.core.contracts.models import ContractCandidate
from product.backend.core.contracts.analysis.canonical import _issue, _issue_key, contract_analysis_sha256
from product.backend.core.contracts.analysis.models import AnalysisIssue, AnalysisReasonCode, AnalysisSeverity, CandidateMergeResult, MergedCandidate


def merge_candidates(candidates: Sequence[ContractCandidate]) -> CandidateMergeResult:
    """按规则语义稳定合并重复候选，并显式报告同 ID 冲突。"""

    ordered = tuple(sorted(candidates, key=lambda item: item.candidate_id))
    groups: dict[tuple[str, str], list[ContractCandidate]] = {}
    for candidate in ordered:
        groups.setdefault(
            (candidate.project_id, contract_analysis_sha256(candidate.suggestion)),
            [],
        ).append(candidate)
    issues: list[AnalysisIssue] = []
    project_ids = tuple(sorted({candidate.project_id for candidate in ordered}))
    if len(project_ids) > 1:
        issues.append(
            _issue(
                AnalysisReasonCode.CONFLICTING_CANDIDATE,
                AnalysisSeverity.BLOCKING,
                "candidate-projects",
                candidate_ids=tuple(candidate.candidate_id for candidate in ordered),
                detail="candidate_batch_contains_multiple_projects",
            )
        )
    by_rule_id: dict[str, list[ContractCandidate]] = {}
    for candidate in ordered:
        by_rule_id.setdefault(candidate.suggestion.id, []).append(candidate)
    for rule_id, same_id in sorted(by_rule_id.items()):
        if len({contract_analysis_sha256(item.suggestion) for item in same_id}) > 1:
            issues.append(
                _issue(
                    AnalysisReasonCode.CONFLICTING_CANDIDATE,
                    AnalysisSeverity.BLOCKING,
                    rule_id,
                    candidate_ids=tuple(item.candidate_id for item in same_id),
                    detail="same_rule_id_has_different_rules",
                )
            )
    merged: list[MergedCandidate] = []
    for (project_id, rule_fingerprint), group in sorted(groups.items()):
        candidate_ids = tuple(sorted(item.candidate_id for item in group))
        if len(group) > 1:
            issues.append(
                _issue(
                    AnalysisReasonCode.DUPLICATE_CANDIDATE,
                    AnalysisSeverity.WARNING,
                    group[0].suggestion.id,
                    candidate_ids=candidate_ids,
                    requirement_ids=tuple(sorted({rid for item in group for rid in item.requirement_ids})),
                    detail="equivalent_candidates_merged",
                )
            )
        suggestion = min((item.suggestion for item in group), key=lambda item: item.id)
        merged.append(
            MergedCandidate(
                merged_id=f"cand_{contract_analysis_sha256({'project_id': project_id, 'rule': rule_fingerprint})[:32]}",
                project_id=project_id,
                suggestion=suggestion,
                candidate_ids=candidate_ids,
                requirement_ids=tuple(sorted({rid for item in group for rid in item.requirement_ids})),
                sources=tuple(sorted({item.source for item in group}, key=lambda item: (item.source_type.value, item.locator, item.content_sha256))),
                fingerprint_sha256=rule_fingerprint,
            )
        )
    sorted_issues = tuple(sorted(issues, key=_issue_key))
    body = {"candidates": merged, "issues": sorted_issues}
    return CandidateMergeResult(
        candidates=tuple(sorted(merged, key=lambda item: item.merged_id)),
        issues=sorted_issues,
        canonical_sha256=contract_analysis_sha256(body),
    )
