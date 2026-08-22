# =============================================================================
# 已发布权限行为的规范化差分
#
# 定位
#   在相同 Contract、Workflow、Twin 与 Baseline 下比较旧、新 Target 的安全行为。
#
# 职责
#   投影稳定安全字段｜拒绝不可比输入｜生成不改写 Verdict 的差分事实
#
# 边界
#   不比较完整响应、Header、时间戳、随机 ID 或非安全计数器，也不产生 Gate 决策。
#
# 调用链
#   Published Evidence / Regression Baseline → BehaviorSnapshot → Gate facts
# =============================================================================

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from product.backend.core.lifecycle import CaseVerdict
from product.backend.core.verification.facts import (
    ExecutionOutcome,
    ObservedEffect,
    TemporalClosure,
)
from product.backend.core.verification.permissions import (
    SecurityEffectKind,
    canonical_sha256,
)
from product.protocols.runner import Evidence


class BehaviorDifferentialModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal["1"] = "1"


class EvidenceSufficiency(StrEnum):
    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"


class BehaviorDifferenceKind(StrEnum):
    EXECUTION_OUTCOME = "EXECUTION_OUTCOME"
    SECURITY_EFFECT_VECTOR = "SECURITY_EFFECT_VECTOR"
    EVIDENCE_SUFFICIENCY = "EVIDENCE_SUFFICIENCY"
    TEMPORAL_CLOSURE = "TEMPORAL_CLOSURE"
    VERDICT = "VERDICT"


class NormalizedSecurityEffect(BehaviorDifferentialModel):
    effect_id: str
    kind: SecurityEffectKind
    resource_id: str
    state: ObservedEffect
    complete: bool
    reliable: bool
    correlated: bool
    temporal_closure: TemporalClosure
    baseline_integrity: bool


class BehaviorSnapshot(BehaviorDifferentialModel):
    contract_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    workflow_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    experiment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    baseline_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_outcome: ExecutionOutcome
    effect_vector: tuple[NormalizedSecurityEffect, ...] = Field(min_length=1, max_length=8192)
    evidence_sufficiency: EvidenceSufficiency
    temporal_closure: TemporalClosure
    verdict: CaseVerdict
    behavior_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_fingerprint(self) -> BehaviorSnapshot:
        payload = self.model_dump(mode="json", exclude={"behavior_fingerprint"})
        if self.behavior_fingerprint != canonical_sha256(payload):
            raise ValueError("behavior fingerprint does not match normalized security fields")
        return self


class BehaviorDifference(BehaviorDifferentialModel):
    kind: BehaviorDifferenceKind
    before_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    after_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class BehaviorDifferentialResult(BehaviorDifferentialModel):
    before_behavior_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    after_behavior_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    changed: bool
    differences: tuple[BehaviorDifference, ...] = Field(default=(), max_length=5)

    @model_validator(mode="after")
    def validate_result(self) -> BehaviorDifferentialResult:
        if self.changed != bool(self.differences):
            raise ValueError("changed must match the normalized differences")
        if len({item.kind for item in self.differences}) != len(self.differences):
            raise ValueError("behavior difference kinds must be unique")
        return self


def normalize_evidence_behavior(
    evidence: Evidence,
    *,
    contract_fingerprint: str,
    workflow_fingerprint: str,
    baseline_fingerprint: str,
) -> BehaviorSnapshot:
    """只从已发布 Evidence 投影允许进入回归比较的稳定安全字段。"""

    effect_vector = tuple(
        sorted(
            (
                NormalizedSecurityEffect(
                    effect_id=item.effect_id,
                    kind=item.kind,
                    resource_id=item.resource_id,
                    state=item.state,
                    complete=item.complete,
                    reliable=item.reliable,
                    correlated=item.correlated,
                    temporal_closure=item.temporal_closure,
                    baseline_integrity=item.baseline_integrity,
                )
                for item in evidence.security_effect_facts
            ),
            key=lambda item: (item.effect_id, item.resource_id),
        )
    )
    sufficient = (
        evidence.baseline_integrity
        and evidence.execution_fact.outcome not in {ExecutionOutcome.FAILED, ExecutionOutcome.UNKNOWN}
        and all(item.complete and item.reliable and item.correlated for item in effect_vector)
        and all(outcome.status.value == "AVAILABLE" for outcome in evidence.outcomes)
    )
    closures = {item.temporal_closure for item in effect_vector}
    closure = (
        TemporalClosure.CLOSED
        if closures == {TemporalClosure.CLOSED}
        else TemporalClosure.OPEN
        if TemporalClosure.OPEN in closures
        else TemporalClosure.UNKNOWN
    )
    experiment_fingerprint = (
        evidence.twin_snapshot.twin_fingerprint
        if evidence.twin_snapshot is not None
        else evidence.case_snapshot.fingerprint
    )
    payload = {
        "schema_version": "1",
        "contract_fingerprint": contract_fingerprint,
        "workflow_fingerprint": workflow_fingerprint,
        "experiment_fingerprint": experiment_fingerprint,
        "baseline_fingerprint": baseline_fingerprint,
        "execution_outcome": evidence.execution_fact.outcome,
        "effect_vector": effect_vector,
        "evidence_sufficiency": EvidenceSufficiency.SUFFICIENT if sufficient else EvidenceSufficiency.INSUFFICIENT,
        "temporal_closure": closure,
        "verdict": evidence.verdict,
    }
    return BehaviorSnapshot(
        **payload,
        behavior_fingerprint=canonical_sha256(payload),
    )


def compare_behavior_snapshots(
    before: BehaviorSnapshot,
    after: BehaviorSnapshot,
) -> BehaviorDifferentialResult:
    """相同冻结不变量下比较安全字段；不可比较时严格拒绝。"""

    invariant_fields = (
        "contract_fingerprint",
        "workflow_fingerprint",
        "experiment_fingerprint",
        "baseline_fingerprint",
    )
    if any(getattr(before, field) != getattr(after, field) for field in invariant_fields):
        raise ValueError("behavior snapshots do not share frozen comparison invariants")
    comparable = (
        (BehaviorDifferenceKind.EXECUTION_OUTCOME, before.execution_outcome, after.execution_outcome),
        (BehaviorDifferenceKind.SECURITY_EFFECT_VECTOR, before.effect_vector, after.effect_vector),
        (BehaviorDifferenceKind.EVIDENCE_SUFFICIENCY, before.evidence_sufficiency, after.evidence_sufficiency),
        (BehaviorDifferenceKind.TEMPORAL_CLOSURE, before.temporal_closure, after.temporal_closure),
        (BehaviorDifferenceKind.VERDICT, before.verdict, after.verdict),
    )
    differences = tuple(
        BehaviorDifference(
            kind=kind,
            before_fingerprint=canonical_sha256(old),
            after_fingerprint=canonical_sha256(new),
        )
        for kind, old, new in comparable
        if old != new
    )
    return BehaviorDifferentialResult(
        before_behavior_fingerprint=before.behavior_fingerprint,
        after_behavior_fingerprint=after.behavior_fingerprint,
        changed=bool(differences),
        differences=differences,
    )
