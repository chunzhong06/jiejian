# =============================================================================
# 通用执行与安全效果事实
#
# 定位
#   具体执行/观察适配器与 Verification 判定之间的纯事实语言。
#
# 职责
#   表达执行结果｜保留原始观察事实｜聚合与适配器无关的 SecurityEffectFact
#
# 边界
#   HTTP、数据库、队列等适配器字段必须先归约；事实本身不产生 Finding 或 Gate。
#
# 调用链
#   Execution/Observer adapters → ObservationFact → SecurityEffectFact → Verification
# =============================================================================

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from product.backend.core.verification.permissions import SecurityEffectDefinition, SecurityEffectKind


_ID = r"^[a-z][a-z0-9_-]{0,63}$"
_HEX = r"^[0-9a-f]{64}$"
_REASON = r"^[A-Z][A-Z0-9_]{0,127}$"


class FactModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal["3"] = "3"


class TargetType(StrEnum):
    WEB = "WEB"
    CLI_APPLICATION = "CLI_APPLICATION"
    MCP_AGENT = "MCP_AGENT"


class ExecutionOutcome(StrEnum):
    ACCEPTED = "ACCEPTED"
    DENIED = "DENIED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class ObservedEffect(StrEnum):
    CONFIRMED = "CONFIRMED"
    ABSENT = "ABSENT"
    UNKNOWN = "UNKNOWN"


class TemporalClosure(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    UNKNOWN = "UNKNOWN"


def _reason_codes(values: tuple[str, ...]) -> tuple[str, ...]:
    if len(values) != len(set(values)) or any(re.fullmatch(_REASON, value) is None for value in values):
        raise ValueError("reason_codes must contain unique stable codes")
    return tuple(sorted(values))


class ExecutionFact(FactModel):
    case_id: str = Field(pattern=_ID)
    action_id: str = Field(pattern=_ID)
    target_type: TargetType
    outcome: ExecutionOutcome
    execution_marker: str = Field(pattern=_ID)
    input_hash: str = Field(pattern=_HEX)
    output_hash: str = Field(pattern=_HEX)
    reason_codes: tuple[str, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def validate_reasons(self) -> ExecutionFact:
        reasons = _reason_codes(self.reason_codes)
        if self.outcome in {ExecutionOutcome.ACCEPTED, ExecutionOutcome.DENIED} and reasons:
            raise ValueError("successful execution facts cannot contain failure reasons")
        if self.outcome in {ExecutionOutcome.FAILED, ExecutionOutcome.UNKNOWN} and not reasons:
            raise ValueError("failed or unknown execution facts require a reason")
        object.__setattr__(self, "reason_codes", reasons)
        return self


class ObservationFact(FactModel):
    requirement_id: str = Field(pattern=_ID)
    resource_id: str = Field(pattern=_ID)
    effect: ObservedEffect
    complete: bool
    reliable: bool
    correlated: bool
    temporal_closure: TemporalClosure
    reason_codes: tuple[str, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def validate_observation(self) -> ObservationFact:
        reasons = _reason_codes(self.reason_codes)
        if self.effect is ObservedEffect.UNKNOWN and self.complete and self.reliable and self.correlated:
            raise ValueError("unknown observation cannot be complete, reliable, and correlated")
        if not self.complete or not self.reliable or not self.correlated or self.temporal_closure is not TemporalClosure.CLOSED:
            if not reasons:
                raise ValueError("incomplete, unreliable, uncorrelated, or open observations require a reason")
        elif reasons:
            raise ValueError("complete reliable observations cannot contain failure reasons")
        object.__setattr__(self, "reason_codes", reasons)
        return self


class DisclosureProof(FactModel):
    projection_version: str = Field(min_length=1, max_length=64)
    projection_complete: bool
    owner_digest: str = Field(pattern=_HEX)
    response_digest: str = Field(pattern=_HEX)
    matched: bool
    correlation_digest: str = Field(pattern=_HEX)


# Observer 原始事实之上的安全效果聚合；不暴露具体适配器类型。
class SecurityEffectFact(FactModel):
    effect_id: str = Field(pattern=_ID)
    kind: SecurityEffectKind
    resource_id: str = Field(pattern=_ID)
    state: ObservedEffect
    complete: bool
    reliable: bool
    correlated: bool
    temporal_closure: TemporalClosure
    baseline_integrity: bool
    source_requirement_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    disclosure_proof: DisclosureProof | None = None
    reason_codes: tuple[str, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def validate_effect_fact(self) -> SecurityEffectFact:
        reasons = _reason_codes(self.reason_codes)
        if len(set(self.source_requirement_ids)) != len(self.source_requirement_ids):
            raise ValueError("source requirement IDs must be unique")
        if self.kind is SecurityEffectKind.DATA_DISCLOSURE:
            if self.disclosure_proof is None:
                raise ValueError("DATA_DISCLOSURE requires a digest proof")
            if self.state is ObservedEffect.CONFIRMED and (not self.disclosure_proof.projection_complete or not self.disclosure_proof.matched):
                raise ValueError("confirmed disclosure requires a matching digest")
        elif self.disclosure_proof is not None:
            raise ValueError("disclosure proof is only valid for DATA_DISCLOSURE")
        if self.state is ObservedEffect.CONFIRMED:
            if not (self.complete and self.reliable and self.correlated):
                raise ValueError("confirmed effect requires an authoritative complete source")
        elif self.state is ObservedEffect.ABSENT:
            if not (self.complete and self.reliable and self.correlated and self.temporal_closure is TemporalClosure.CLOSED and self.baseline_integrity):
                raise ValueError("absent effect requires complete closed evidence and a valid baseline")
        elif not reasons:
            raise ValueError("unknown effect requires a reason")
        object.__setattr__(self, "source_requirement_ids", tuple(sorted(self.source_requirement_ids)))
        object.__setattr__(self, "reason_codes", reasons)
        return self


def aggregate_security_effect(
    effect: SecurityEffectDefinition,
    *,
    resource_id: str,
    required_requirement_ids: tuple[str, ...],
    corroborating_requirement_ids: tuple[str, ...],
    observations: tuple[ObservationFact, ...],
    baseline_integrity: bool,
    disclosure_proof: DisclosureProof | None = None,
) -> SecurityEffectFact:
    """按存在性 BLOCK、全称性 PASS 规则聚合一个资源上的安全效果。"""

    relevant_ids = set(required_requirement_ids + corroborating_requirement_ids)
    selected = tuple(item for item in observations if item.resource_id == resource_id and item.requirement_id in relevant_ids)
    authoritative = tuple(item for item in selected if item.requirement_id in required_requirement_ids)
    confirmed = tuple(item for item in authoritative if item.effect is ObservedEffect.CONFIRMED and item.complete and item.reliable and item.correlated)
    if disclosure_proof is not None and disclosure_proof.projection_complete and disclosure_proof.matched:
        confirmed = authoritative or selected
    if confirmed:
        closure = _aggregate_closure(tuple(item.temporal_closure for item in confirmed))
        return SecurityEffectFact(
            effect_id=effect.effect_id,
            kind=effect.kind,
            resource_id=resource_id,
            state=ObservedEffect.CONFIRMED,
            complete=True,
            reliable=True,
            correlated=True,
            temporal_closure=closure,
            baseline_integrity=baseline_integrity,
            source_requirement_ids=tuple(sorted({item.requirement_id for item in confirmed} or relevant_ids)),
            disclosure_proof=disclosure_proof,
        )
    by_requirement = {item.requirement_id: item for item in authoritative}
    complete = set(by_requirement) == set(required_requirement_ids) and all(item.complete for item in by_requirement.values())
    reliable = complete and all(item.reliable for item in by_requirement.values())
    correlated = reliable and all(item.correlated for item in by_requirement.values())
    closure = _aggregate_closure(tuple(item.temporal_closure for item in by_requirement.values()))
    all_absent = correlated and all(item.effect is ObservedEffect.ABSENT for item in by_requirement.values())
    disclosure_absent = disclosure_proof is None or (disclosure_proof.projection_complete and not disclosure_proof.matched)
    if all_absent and disclosure_absent and closure is TemporalClosure.CLOSED and baseline_integrity:
        return SecurityEffectFact(
            effect_id=effect.effect_id,
            kind=effect.kind,
            resource_id=resource_id,
            state=ObservedEffect.ABSENT,
            complete=True,
            reliable=True,
            correlated=True,
            temporal_closure=TemporalClosure.CLOSED,
            baseline_integrity=True,
            source_requirement_ids=required_requirement_ids,
            disclosure_proof=disclosure_proof,
        )
    reasons: list[str] = []
    if not complete:
        reasons.append("REQUIRED_EFFECT_CHANNEL_INCOMPLETE")
    if complete and not reliable:
        reasons.append("REQUIRED_EFFECT_CHANNEL_UNRELIABLE")
    if reliable and not correlated:
        reasons.append("REQUIRED_EFFECT_CHANNEL_UNCORRELATED")
    if closure is not TemporalClosure.CLOSED:
        reasons.append("TEMPORAL_CLOSURE_INCOMPLETE")
    if not baseline_integrity:
        reasons.append("BASELINE_INTEGRITY_INVALID")
    if disclosure_proof is not None and not disclosure_proof.projection_complete:
        reasons.append("DISCLOSURE_PROJECTION_INCOMPLETE")
    if not reasons:
        reasons.append("EFFECT_STATE_UNKNOWN")
    return SecurityEffectFact(
        effect_id=effect.effect_id,
        kind=effect.kind,
        resource_id=resource_id,
        state=ObservedEffect.UNKNOWN,
        complete=complete,
        reliable=reliable,
        correlated=correlated,
        temporal_closure=closure,
        baseline_integrity=baseline_integrity,
        source_requirement_ids=tuple(sorted(set(required_requirement_ids) or relevant_ids)),
        disclosure_proof=disclosure_proof,
        reason_codes=tuple(reasons),
    )


def _aggregate_closure(values: tuple[TemporalClosure, ...]) -> TemporalClosure:
    if values and all(value is TemporalClosure.CLOSED for value in values):
        return TemporalClosure.CLOSED
    if any(value is TemporalClosure.OPEN for value in values):
        return TemporalClosure.OPEN
    return TemporalClosure.UNKNOWN
