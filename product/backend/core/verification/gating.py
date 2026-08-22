# =============================================================================
# Regression Gate 回归基线与门禁纯领域模型
#
# 定位
#   只消费已验证的 Run/Finding/覆盖事实，确定性生成 GateResult
#
# 职责
#   固定基线身份｜比较 Finding 与覆盖变化｜按策略生成稳定阻断原因
#
# 边界
#   不读取 publication、不修改 Verdict、不执行 Runner，也不自动接受基线。
#
# 调用链
#   RegressionGate workflow → evaluate_gate → GateResult
# =============================================================================

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from product.backend.core.lifecycle import CaseVerdict, DomainModel, RunLifecycle, RunVerdict


_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}$")
_ACTOR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$")
_SECRET = re.compile(
    r"(?:authorization|cookie|credential|password|passwd|secret|token|api[_-]?key)\s*[:=]",
    re.IGNORECASE,
)
_SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def _clean_token(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 256 or _TOKEN.fullmatch(normalized) is None or _SECRET.search(normalized):
        raise ValueError(f"{label} is not a bounded public token")
    return normalized


def _clean_actor(value: str) -> str:
    normalized = value.strip()
    if not normalized or _ACTOR.fullmatch(normalized) is None or _SECRET.search(normalized):
        raise ValueError("actor is not a bounded public identity")
    return normalized


def canonical_sha256(value: Any) -> str:
    payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class GateDecision(StrEnum):
    PASS = "PASS"
    BLOCK = "BLOCK"
    ERROR = "ERROR"


class BaselineFindingRef(DomainModel):
    finding_id: str = Field(pattern=r"^finding_[0-9a-f]{32}$")
    occurrence_id: str = Field(pattern=r"^occ_[0-9a-f]{32}$")
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=8192)

    @field_validator("evidence_ids")
    @classmethod
    def validate_evidence_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values) or any(re.fullmatch(r"^ev_[0-9a-f]{20}$", value) is None for value in values):
            raise ValueError("baseline evidence references must be unique Evidence IDs")
        return tuple(sorted(values))


# 用户显式接受的不可变 Run 身份、Finding、覆盖与版本快照。
class RegressionBaseline(DomainModel):

    baseline_id: str = Field(pattern=r"^baseline_[0-9a-f]{32}$")
    project_id: str = Field(min_length=1, max_length=64)
    accepted_run_id: str = Field(pattern=r"^run_[0-9a-f]{32}$")
    finding_refs: tuple[BaselineFindingRef, ...] = Field(max_length=8192)
    coverage_ids: tuple[str, ...] = Field(max_length=16384)
    coverage_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    engine_version: str = Field(min_length=1, max_length=64)
    protocol_versions: tuple[str, ...] = Field(min_length=1, max_length=8)
    actor: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=1024)
    accepted_at_us: int = Field(ge=0)

    @field_validator("project_id", "engine_version")
    @classmethod
    def validate_tokens(cls, value: str, info) -> str:
        return _clean_token(value, info.field_name)

    @field_validator("coverage_ids", "protocol_versions")
    @classmethod
    def validate_token_lists(cls, values: tuple[str, ...], info) -> tuple[str, ...]:
        if len(set(values)) != len(values):
            raise ValueError(f"{info.field_name} must be unique")
        return tuple(sorted(_clean_token(value, info.field_name) for value in values))

    @field_validator("actor")
    @classmethod
    def validate_actor(cls, value: str) -> str:
        return _clean_actor(value)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 1024 or _SECRET.search(normalized):
            raise ValueError("baseline reason must be non-empty and non-secret")
        return normalized

    @model_validator(mode="after")
    def validate_baseline(self) -> RegressionBaseline:
        if tuple(sorted(ref.finding_id for ref in self.finding_refs)) != tuple(ref.finding_id for ref in self.finding_refs):
            raise ValueError("baseline finding references must be sorted")
        if self.coverage_digest != canonical_sha256(self.coverage_ids):
            raise ValueError("baseline coverage digest does not match coverage IDs")
        return self


class GateFinding(DomainModel):
    finding_id: str = Field(pattern=r"^finding_[0-9a-f]{32}$")
    occurrence_id: str = Field(pattern=r"^occ_[0-9a-f]{32}$")
    status: str = Field(min_length=1, max_length=16)
    verdict: CaseVerdict
    severity: Literal["low", "medium", "high", "critical", "unknown"]


class GateFacts(DomainModel):
    run_id: str = Field(pattern=r"^run_[0-9a-f]{32}$")
    project_id: str = Field(min_length=1, max_length=64)
    lifecycle: RunLifecycle
    verdict: RunVerdict | None
    publication_validated: bool
    findings: tuple[GateFinding, ...] = Field(max_length=8192)
    coverage_ids: tuple[str, ...] = Field(max_length=16384)
    coverage_gap_count: int = Field(ge=0, le=16384)
    required_observer_issues: tuple[str, ...] = Field(max_length=8192)
    inconclusive_reasons: tuple[str, ...] = Field(max_length=8192)
    execution_errors: tuple[str, ...] = Field(max_length=8192)
    behavior_change_ids: tuple[str, ...] = Field(default=(), max_length=8192)
    behavior_comparison_issues: tuple[str, ...] = Field(default=(), max_length=8192)
    request_snapshot_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    engine_version: str | None = Field(default=None, min_length=1, max_length=64)
    protocol_versions: tuple[str, ...] = Field(default=(), max_length=8)

    @field_validator("project_id", "engine_version")
    @classmethod
    def validate_fact_tokens(cls, value: str | None, info) -> str | None:
        return None if value is None else _clean_token(value, info.field_name)

    @field_validator(
        "coverage_ids",
        "required_observer_issues",
        "inconclusive_reasons",
        "execution_errors",
        "behavior_change_ids",
        "behavior_comparison_issues",
        "protocol_versions",
    )
    @classmethod
    def validate_fact_lists(cls, values: tuple[str, ...], info) -> tuple[str, ...]:
        if len(set(values)) != len(values):
            raise ValueError(f"{info.field_name} must be unique")
        return tuple(sorted(_clean_token(value, info.field_name) for value in values))


class GatePolicy(DomainModel):
    policy_version: Literal["gate-v1"] = "gate-v1"
    minimum_severity: Literal["low", "medium", "high", "critical"] = "low"


class GateReason(DomainModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,127}$")
    subject: str = Field(min_length=1, max_length=256)

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, value: str) -> str:
        return _clean_token(value, "reason subject")


class GateResult(DomainModel):
    gate_result_id: str = Field(pattern=r"^gate_[0-9a-f]{32}$")
    baseline_id: str = Field(pattern=r"^baseline_[0-9a-f]{32}$")
    run_id: str = Field(pattern=r"^run_[0-9a-f]{32}$")
    policy_version: Literal["gate-v1"]
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    reasons: tuple[GateReason, ...] = Field(max_length=8192)
    decision: GateDecision
    evaluated_at_us: int = Field(ge=0)


def baseline_id_for(project_id: str, run_id: str, request_snapshot_sha256: str, coverage_digest: str) -> str:
    return f"baseline_{canonical_sha256((project_id, run_id, request_snapshot_sha256, coverage_digest))[:32]}"


def gate_input_hash(baseline_id: str, facts: GateFacts, policy: GatePolicy) -> str:
    return canonical_sha256((baseline_id, policy.model_dump(mode="json"), facts.model_dump(mode="json")))


def gate_result_id_for(baseline_id: str, run_id: str, policy_version: str, input_hash: str) -> str:
    return f"gate_{canonical_sha256((baseline_id, run_id, policy_version, input_hash))[:32]}"


def _reason(code: str, subject: str) -> GateReason:
    return GateReason(code=code, subject=subject)


def evaluate_gate(baseline: RegressionBaseline, facts: GateFacts, policy: GatePolicy) -> GateResult:
    """确定性比较固定基线与当前事实；任何关键不确定或缺失默认阻断。"""

    reasons: list[GateReason] = []
    if not facts.publication_validated:
        reasons.append(_reason("PUBLICATION_NOT_VALIDATED", facts.run_id))
    for code in facts.execution_errors:
        reasons.append(_reason("EXECUTION_ERROR", code))
    if facts.lifecycle is not RunLifecycle.COMPLETED or facts.verdict is None:
        reasons.append(_reason("RUN_NOT_COMPLETED", facts.lifecycle.value))
    if facts.coverage_gap_count > 0:
        reasons.append(_reason("COVERAGE_GAP", str(facts.coverage_gap_count)))
    for coverage_id in sorted(set(baseline.coverage_ids) - set(facts.coverage_ids)):
        reasons.append(_reason("BASELINE_COVERAGE_MISSING", coverage_id))
    for issue in facts.required_observer_issues:
        reasons.append(_reason("REQUIRED_OBSERVER_INCOMPLETE", issue))
    for issue in facts.inconclusive_reasons:
        reasons.append(_reason("INCONCLUSIVE", issue))
    for behavior_id in facts.behavior_change_ids:
        reasons.append(_reason("SECURITY_BEHAVIOR_CHANGED", behavior_id))
    for issue in facts.behavior_comparison_issues:
        reasons.append(_reason("SECURITY_BEHAVIOR_NOT_COMPARABLE", issue))

    baseline_ids = {item.finding_id for item in baseline.finding_refs}
    threshold = _SEVERITY_ORDER[policy.minimum_severity]
    for finding in facts.findings:
        if finding.verdict is CaseVerdict.INCONCLUSIVE:
            reasons.append(_reason("INCONCLUSIVE_FINDING", finding.finding_id))
        if finding.verdict is not CaseVerdict.VULNERABLE or _SEVERITY_ORDER.get(finding.severity, 0) < threshold:
            continue
        if finding.status == "REAPPEARED":
            reasons.append(_reason("FINDING_REAPPEARED", finding.finding_id))
        elif finding.finding_id not in baseline_ids:
            reasons.append(_reason("NEW_VULNERABLE_FINDING", finding.finding_id))
        else:
            reasons.append(_reason("VULNERABLE_FINDING", finding.finding_id))
    if facts.verdict is RunVerdict.INCONCLUSIVE:
        reasons.append(_reason("RUN_INCONCLUSIVE", facts.run_id))
    elif facts.verdict is RunVerdict.BLOCK:
        reasons.append(_reason("RUN_VERDICT_BLOCK", facts.run_id))

    unique = {(item.code, item.subject): item for item in reasons}
    ordered = tuple(unique[key] for key in sorted(unique))
    decision = GateDecision.ERROR if facts.execution_errors or not facts.publication_validated or facts.lifecycle is not RunLifecycle.COMPLETED or facts.verdict is None else GateDecision.BLOCK if ordered else GateDecision.PASS
    input_hash = gate_input_hash(baseline.baseline_id, facts, policy)
    return GateResult(
        gate_result_id=gate_result_id_for(baseline.baseline_id, facts.run_id, policy.policy_version, input_hash),
        baseline_id=baseline.baseline_id,
        run_id=facts.run_id,
        policy_version=policy.policy_version,
        input_hash=input_hash,
        reasons=ordered,
        decision=decision,
        evaluated_at_us=0,
    )
