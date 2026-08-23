# =============================================================================
# Contract Drift 分析
#
# 定位
#   当前候选、治理版本与已验证行为之间的纯派生差异算法
#
# 职责
#   计算六类 Drift｜保留确定性排序｜拒绝不一致的历史指纹
#
# 调用链
#   ContractAnalysis → build_drift_report → DriftReport
# =============================================================================

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.contracts.analysis.models import AnalysisIssue, AnalysisModel, AnalysisReasonCode, AnalysisSeverity
from product.backend.core.contracts.analysis.canonical import contract_analysis_sha256
from product.backend.core.contracts.models import ContractCandidate, ContractSourceType, ContractVersion, Requirement
from product.backend.core.identifiers import LONG_SLUG_ID_PATTERN, PROJECT_ID_PATTERN, RUN_ID_PATTERN
from product.backend.core.verification.permissions import PermissionRule


class DriftType(StrEnum):
    REQUIREMENT_UNCOVERED = "REQUIREMENT_UNCOVERED"
    CONTRACT_RULE_DISAPPEARED = "CONTRACT_RULE_DISAPPEARED"
    ROUTE_CHANGED = "ROUTE_CHANGED"
    OBSERVER_UNAVAILABLE = "OBSERVER_UNAVAILABLE"
    BEHAVIOR_CHANGED = "BEHAVIOR_CHANGED"
    LLM_REQUIREMENT_CONFLICT = "LLM_REQUIREMENT_CONFLICT"


class VerifiedBehaviorFingerprint(AnalysisModel):
    run_id: str = Field(pattern=RUN_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    contract_id: str = Field(pattern=LONG_SLUG_ID_PATTERN)
    contract_version: int = Field(ge=1)
    fingerprint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    summary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verified: Literal[True] = True


class DriftEntry(AnalysisModel):
    drift_type: DriftType
    reason_code: AnalysisReasonCode
    subject_id: str = Field(min_length=1, max_length=1024)
    blocking: bool = True
    candidate_ids: tuple[str, ...] = Field(default=(), max_length=512)
    requirement_ids: tuple[str, ...] = Field(default=(), max_length=512)
    rule_ids: tuple[str, ...] = Field(default=(), max_length=512)
    detail: str = Field(min_length=1, max_length=256)


class DriftReport(AnalysisModel):
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    contract_id: str = Field(pattern=LONG_SLUG_ID_PATTERN)
    contract_version: int = Field(ge=1)
    entries: tuple[DriftEntry, ...] = Field(default=(), max_length=4096)
    analysis_issues: tuple[AnalysisIssue, ...] = Field(default=(), max_length=4096)
    canonical_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def build_drift_report(
    contract: ContractVersion,
    *,
    requirements: tuple[Requirement, ...] = (),
    requirement_candidates: tuple[ContractCandidate, ...] = (),
    available_rule_ids: tuple[str, ...] | None = None,
    capability_candidates: tuple[ContractCandidate, ...] = (),
    unexecutable_rule_ids: tuple[str, ...] = (),
    available_observations: tuple[str, ...] = ("resource_state",),
    accepted_behavior: VerifiedBehaviorFingerprint | None = None,
    current_behavior: VerifiedBehaviorFingerprint | None = None,
    llm_candidates: tuple[ContractCandidate, ...] = (),
    analysis_issues: tuple[AnalysisIssue, ...] = (),
) -> DriftReport:
    """对显式输入生成六类漂移报告，不改变任何运行结论。"""

    for requirement in requirements:
        if requirement.project_id != contract.project_id:
            raise JiejianError(ErrorCode.CONTRACT_ANALYSIS_INVALID, "漂移需求与契约项目不一致")
    for candidate in (*requirement_candidates, *capability_candidates, *llm_candidates):
        if candidate.project_id != contract.project_id:
            raise JiejianError(ErrorCode.CONTRACT_ANALYSIS_INVALID, "漂移候选与契约项目不一致")

    entries: list[DriftEntry] = []
    contract_rules = {rule.rule_id: rule for rule in contract.snapshot.rules}
    for requirement in sorted(requirements, key=lambda item: item.requirement_id):
        candidates = tuple(
            candidate
            for candidate in requirement_candidates
            if requirement.requirement_id in candidate.requirement_ids
        )
        if not candidates or not any(
            _suggestion_key(candidate.suggestion) in {_suggestion_key(rule) for rule in contract.snapshot.rules}
            for candidate in candidates
        ):
            entries.append(
                DriftEntry(
                    drift_type=DriftType.REQUIREMENT_UNCOVERED,
                    reason_code=AnalysisReasonCode.REQUIREMENT_UNCOVERED,
                    subject_id=requirement.requirement_id,
                    requirement_ids=(requirement.requirement_id,),
                    detail="requirement_intent_not_covered_by_contract",
                )
            )
    if available_rule_ids is not None:
        available = set(available_rule_ids)
        for rule_id in sorted(set(contract_rules) - available):
            entries.append(
                DriftEntry(
                    drift_type=DriftType.CONTRACT_RULE_DISAPPEARED,
                    reason_code=AnalysisReasonCode.CONTRACT_RULE_DISAPPEARED,
                    subject_id=rule_id,
                    rule_ids=(rule_id,),
                    detail="contract_rule_missing_from_current_capabilities",
                )
            )
    capability_by_id = {candidate.suggestion.id: candidate.suggestion for candidate in capability_candidates}
    for rule_id in sorted(set(contract_rules) & set(capability_by_id)):
        if _suggestion_key(contract_rules[rule_id]) != _suggestion_key(capability_by_id[rule_id]):
            entries.append(
                DriftEntry(
                    drift_type=DriftType.ROUTE_CHANGED,
                    reason_code=AnalysisReasonCode.ROUTE_CHANGED,
                    subject_id=rule_id,
                    rule_ids=(rule_id,),
                    detail="current_route_capability_changed_rule_semantics",
                )
            )
    for rule_id in sorted(set(unexecutable_rule_ids)):
        entries.append(
            DriftEntry(
                drift_type=DriftType.ROUTE_CHANGED,
                reason_code=AnalysisReasonCode.RULE_UNEXECUTABLE,
                subject_id=rule_id,
                rule_ids=(rule_id,),
                detail="current_route_or_field_is_not_executable",
            )
        )
    observation_set = set(available_observations)
    for rule in contract.snapshot.rules:
        missing = tuple(sorted(set(rule.required_observations) - observation_set))
        if missing:
            entries.append(
                DriftEntry(
                    drift_type=DriftType.OBSERVER_UNAVAILABLE,
                    reason_code=AnalysisReasonCode.OBSERVER_UNAVAILABLE,
                    subject_id=rule.rule_id,
                    rule_ids=(rule.rule_id,),
                    detail="required_observer_unavailable:" + ",".join(missing),
                )
            )
    if (accepted_behavior is None) != (current_behavior is None):
        raise JiejianError(
            ErrorCode.CONTRACT_ANALYSIS_INVALID,
            "行为漂移必须同时提供已接受和当前的完整指纹",
        )
    if accepted_behavior is not None and current_behavior is not None:
        if not accepted_behavior.verified or not current_behavior.verified:
            raise JiejianError(
                ErrorCode.CONTRACT_ANALYSIS_INVALID,
                "行为漂移输入未通过完整性验证",
            )
        for label, fingerprint in (("accepted", accepted_behavior), ("current", current_behavior)):
            if (
                fingerprint.project_id != contract.project_id
                or fingerprint.contract_id != contract.contract_id
                or (label == "current" and fingerprint.contract_version != contract.version)
            ):
                raise JiejianError(
                    ErrorCode.CONTRACT_ANALYSIS_INVALID,
                    "行为漂移指纹与待评估契约上下文不一致",
                )
        if accepted_behavior.fingerprint_sha256 != current_behavior.fingerprint_sha256:
            entries.append(
                DriftEntry(
                    drift_type=DriftType.BEHAVIOR_CHANGED,
                    reason_code=AnalysisReasonCode.BEHAVIOR_CHANGED,
                    subject_id=current_behavior.run_id,
                    rule_ids=tuple(sorted(contract_rules)),
                    detail="verified_run_behavior_fingerprint_changed",
                )
            )
    explicit = [item for item in (*requirement_candidates, *llm_candidates) if item.source.source_type is not ContractSourceType.LLM]
    for llm in llm_candidates:
        for other in explicit:
            overlap = tuple(sorted(set(llm.requirement_ids) & set(other.requirement_ids)))
        if overlap and llm.suggestion != other.suggestion:
                entries.append(
                    DriftEntry(
                        drift_type=DriftType.LLM_REQUIREMENT_CONFLICT,
                        reason_code=AnalysisReasonCode.LLM_REQUIREMENT_CONFLICT,
                        subject_id=llm.candidate_id,
                        candidate_ids=tuple(sorted((llm.candidate_id, other.candidate_id))),
                        requirement_ids=overlap,
                        rule_ids=(llm.suggestion.id, other.suggestion.id),
                        detail="llm_candidate_conflicts_with_explicit_requirement",
                    )
                )
    ordered_entries = tuple(sorted(set(entries), key=_entry_key))
    body = {
        "project_id": contract.project_id,
        "contract_id": contract.contract_id,
        "contract_version": contract.version,
        "entries": ordered_entries,
        "analysis_issues": tuple(sorted(set(analysis_issues), key=lambda item: (item.code.value, item.subject_id))),
    }
    return DriftReport(
        project_id=contract.project_id,
        contract_id=contract.contract_id,
        contract_version=contract.version,
        entries=ordered_entries,
        analysis_issues=body["analysis_issues"],
        canonical_sha256=contract_analysis_sha256(body),
    )


def _suggestion_key(value: PermissionRule | object) -> tuple[str, tuple[str, ...], str]:
    if hasattr(value, "expectation"):
        return (value.expectation.value, tuple(sorted(value.required_observations)), value.severity)
    return (value.kind.value, tuple(sorted(value.required_observations)), value.severity)


def _entry_key(entry: DriftEntry) -> tuple[str, str, str, tuple[str, ...], tuple[str, ...]]:
    return (
        entry.drift_type.value,
        entry.reason_code.value,
        entry.subject_id,
        entry.rule_ids,
        entry.candidate_ids,
        entry.requirement_ids,
    )
