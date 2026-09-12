# 当前权限实验的纯判定：先保留已归因的禁止效果，再要求完整证明才能判安全。
from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol

from pydantic import Field, model_validator

from product.backend.core.lifecycle import CaseVerdict, RunVerdict
from product.protocols.execution_v3 import EffectId, ExecutionCase, Hash, WireModel


class CheckEffectFact(WireModel):
    effect_id: EffectId
    proof_fingerprint: Hash
    state: Literal["CONFIRMED", "ABSENT", "UNKNOWN"]
    complete: bool
    reliable: bool
    correlated: bool
    authoritative: bool
    closure: Literal["CLOSED", "OPEN", "UNKNOWN"]


class CheckProofObservation(Protocol):
    proof_fingerprint: str
    observer_id: str
    phase: str
    level: str
    state: str
    closure: str
    complete: bool
    reliable: bool
    correlated: bool
    authoritative: bool


def project_check_effect_facts(case: ExecutionCase, observations: Sequence[CheckProofObservation]) -> tuple[CheckEffectFact, ...]:
    """从已验证来源的末次阶段事实提取效果；任何可靠确认优先，不完整通道不能证明不存在。"""
    facts = []
    for proof in case.proof_requirements:
        latest = {}
        observed = []
        for item in observations:
            if item.proof_fingerprint != proof.proof_fingerprint or item.level != proof.level or item.phase not in ("AFTER", "EVENTUAL"):
                continue
            observed.append(item)
            current = latest.get(item.observer_id)
            if current is None or item.phase == "EVENTUAL":
                latest[item.observer_id] = item
        values = tuple(latest.values())
        confirmed = tuple(item for item in observed if item.state == "CONFIRMED"
            and item.complete and item.reliable and item.correlated and item.authoritative)
        reliable = bool(values) and all(item.complete and item.reliable and item.correlated and item.authoritative for item in values)
        state = "CONFIRMED" if confirmed else "ABSENT" if reliable and all(item.state == "ABSENT" for item in values) else "UNKNOWN"
        trusted = bool(confirmed) or reliable
        facts.append(CheckEffectFact(effect_id=proof.effect_id, proof_fingerprint=proof.proof_fingerprint,
            state=state, complete=trusted, reliable=trusted, correlated=trusted, authoritative=trusted,
            closure="CLOSED" if values and all(item.closure == "CLOSED" for item in values) else "OPEN"))
    return tuple(facts)


class CheckDecisionInput(WireModel):
    case: ExecutionCase
    execution: Literal["ACCEPTED", "DENIED", "FAILED", "UNKNOWN"]
    actual_identity: Literal["MATCH", "MISMATCH", "UNKNOWN"]
    run_correlated: bool
    resource_correlated: bool
    baseline_trusted: bool
    recovery_verified: bool
    allow_control_verdict: CaseVerdict | None = None
    effects: tuple[CheckEffectFact, ...] = Field(max_length=48)

    @model_validator(mode="after")
    def validate_proof_associations(self):
        expected = {(proof.effect_id, proof.proof_fingerprint) for proof in self.case.proof_requirements}
        actual = [(fact.effect_id, fact.proof_fingerprint) for fact in self.effects]
        if len(set(actual)) != len(actual) or not set(actual) <= expected:
            raise ValueError("check facts must reference unique frozen case proofs")
        return self


class CheckDecision(WireModel):
    verdict: CaseVerdict
    reason_codes: tuple[str, ...] = Field(max_length=16)
    confirmed_forbidden_effect_ids: tuple[EffectId, ...] = Field(max_length=16)


def evaluate_check_case(facts: CheckDecisionInput) -> CheckDecision:
    """消费冻结 Case 与独立观察事实；缺失证明不补猜，也不发起任何 I/O。"""

    # 同一效果的辅助材料不能覆盖决定性来源；所有关联先按冻结 proof 身份核对。
    by_proof = {item.proof_fingerprint: item for item in facts.effects}
    required = tuple(
        by_proof.get(proof.proof_fingerprint)
        for proof in facts.case.proof_requirements
        if proof.level == "VERDICT_REQUIRED"
    )
    attributed = facts.actual_identity == "MATCH" and facts.run_correlated and facts.resource_correlated
    confirmed = tuple(sorted({
        item.effect_id for item in required
        if item is not None and item.state == "CONFIRMED"
        and item.authoritative and item.complete and item.reliable and item.correlated
    })) if attributed else ()
    deny = facts.case.permission.expectation == "DENY"
    # 已确认的禁止效果优先于后续恢复、执行错误和辅助 trace 缺失。
    if deny and confirmed:
        return CheckDecision(verdict=CaseVerdict.VULNERABLE,
            reason_codes=("ORPHAN_EFFECT_CONFIRMED",), confirmed_forbidden_effect_ids=confirmed)

    reasons: set[str] = set()
    if facts.actual_identity != "MATCH":
        reasons.add("ACTUAL_IDENTITY_" + facts.actual_identity)
    if not facts.run_correlated:
        reasons.add("RUN_CORRELATION_UNTRUSTED")
    if not facts.resource_correlated:
        reasons.add("RESOURCE_CORRELATION_UNTRUSTED")
    if not facts.baseline_trusted:
        reasons.add("BASELINE_INTEGRITY_INVALID")
    if not facts.recovery_verified:
        reasons.add("RECOVERY_UNVERIFIED")
    if facts.execution in ("FAILED", "UNKNOWN"):
        reasons.add("EXECUTION_" + facts.execution)
    if any(item is None or not (item.authoritative and item.complete and item.reliable and item.correlated)
           or item.state == "UNKNOWN" for item in required):
        reasons.add("REQUIRED_EFFECT_UNKNOWN")
    if any(item is None or item.closure != "CLOSED" for item in required):
        reasons.add("TEMPORAL_CLOSURE_INCOMPLETE")
    if deny:
        if facts.execution == "ACCEPTED":
            reasons.add("UNAUTHORIZED_EXECUTION_ACCEPTED")
        if facts.allow_control_verdict is not CaseVerdict.SAFE:
            reasons.add("ALLOW_CONTROL_INVALID")
        if any(item is None or item.state != "ABSENT" for item in required):
            reasons.add("REQUIRED_EFFECT_NOT_ABSENT")
    else:
        if facts.execution == "DENIED":
            reasons.add("ALLOW_EXECUTION_REJECTED")
        if set(confirmed) != set(facts.case.protected_effect_ids):
            reasons.add("ALLOW_EFFECT_UNCONFIRMED")
    return CheckDecision(verdict=CaseVerdict.INCONCLUSIVE if reasons else CaseVerdict.SAFE,
        reason_codes=tuple(sorted(reasons)), confirmed_forbidden_effect_ids=())


def aggregate_check_verdict(
    verdicts: tuple[CaseVerdict, ...], *, planned_case_count: int, has_gaps: bool = False,
) -> RunVerdict:
    """全计划 SAFE 才允许 PASS；未执行和旧错误状态均保留不确定性。"""

    if planned_case_count < 0 or len(verdicts) > planned_case_count:
        raise ValueError("invalid planned case cardinality")
    if CaseVerdict.VULNERABLE in verdicts:
        return RunVerdict.BLOCK
    if has_gaps or not verdicts or len(verdicts) != planned_case_count or any(
        verdict is not CaseVerdict.SAFE for verdict in verdicts
    ):
        return RunVerdict.INCONCLUSIVE
    return RunVerdict.PASS
