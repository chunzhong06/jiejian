# =============================================================================
# Requirement Contract 来源适配
#
# 定位
#   显式 Requirement 受限语法到 Candidate 的确定性解析器
#
# 职责
#   解析允许的声明｜拒绝未知语法｜保留诊断和来源摘要
#
# 调用链
#   Contract analysis workflow → parse_requirement → CandidateBatch
# =============================================================================

from __future__ import annotations

import shlex

from pydantic import ValidationError

from product.backend.core.contracts.models import CandidateRiskKind, CandidateSuggestion
from product.backend.core.contracts.analysis.models import ContractCandidate, ContractSourceType, Requirement
from product.backend.core.contracts.analysis.models import AnalysisIssue, AnalysisReasonCode, AnalysisSeverity, CandidateBatch
from product.backend.core.contracts.analysis.canonical import _candidate, _issue, _issue_key, contract_analysis_sha256


def parse_requirement(requirement: Requirement) -> CandidateBatch:
    """解析受控建议模板：suggestion id=... kind=... observations=... severity=...。"""

    candidates: list[ContractCandidate] = []
    issues: list[AnalysisIssue] = []
    for line_number, raw_line in enumerate(requirement.text.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            tokens = shlex.split(line)
        except ValueError:
            issues.append(
                _issue(
                    AnalysisReasonCode.AMBIGUOUS_SOURCE,
                    AnalysisSeverity.BLOCKING,
                    f"{requirement.requirement_id}:line:{line_number}",
                    detail="invalid_template_quoting",
                    requirement_ids=(requirement.requirement_id,),
                )
            )
            continue
        if not tokens or tokens[0].lower() != "suggestion":
            issues.append(
                _issue(
                    AnalysisReasonCode.AMBIGUOUS_SOURCE,
                    AnalysisSeverity.BLOCKING,
                    f"{requirement.requirement_id}:line:{line_number}",
                    detail="unsupported_requirement_template",
                    requirement_ids=(requirement.requirement_id,),
                )
            )
            continue
        fields: dict[str, str] = {}
        malformed = False
        for token in tokens[1:]:
            if "=" not in token:
                malformed = True
                break
            key, value = token.split("=", 1)
            if key in fields or not value:
                malformed = True
                break
            fields[key] = value
        required = {"id", "kind", "observations", "severity"}
        if malformed or set(fields) != required:
            issues.append(
                _issue(
                    AnalysisReasonCode.AMBIGUOUS_SOURCE,
                    AnalysisSeverity.BLOCKING,
                    f"{requirement.requirement_id}:line:{line_number}",
                    detail="requirement_template_fields_invalid",
                    requirement_ids=(requirement.requirement_id,),
                )
            )
            continue
        try:
            rule = CandidateSuggestion(
                id=fields["id"],
                kind=CandidateRiskKind(fields["kind"]),
                required_observations=tuple(
                    observation for observation in fields["observations"].split(",") if observation
                ),
                severity=fields["severity"],
            )
        except (TypeError, ValueError, ValidationError):
            issues.append(
                _issue(
                    AnalysisReasonCode.AMBIGUOUS_SOURCE,
                    AnalysisSeverity.BLOCKING,
                    f"{requirement.requirement_id}:line:{line_number}",
                    detail="requirement_template_rule_invalid",
                    requirement_ids=(requirement.requirement_id,),
                )
            )
            continue
        locator = f"{requirement.source.locator}#line:{line_number}"
        candidates.append(
            _candidate(
                requirement.project_id,
                ContractSourceType.REQUIREMENT_TEXT,
                locator,
                requirement.source.content_sha256,
                rule,
                requirement_ids=(requirement.requirement_id,),
            )
        )
    if not candidates and not issues:
        issues.append(
            _issue(
                AnalysisReasonCode.AMBIGUOUS_SOURCE,
                AnalysisSeverity.BLOCKING,
                requirement.requirement_id,
                detail="requirement_has_no_supported_rule",
                requirement_ids=(requirement.requirement_id,),
            )
        )
    return CandidateBatch(
        adapter="requirement_template",
        candidates=tuple(sorted(candidates, key=lambda item: item.candidate_id)),
        issues=tuple(sorted(issues, key=_issue_key)),
        input_sha256=contract_analysis_sha256(requirement),
    )
