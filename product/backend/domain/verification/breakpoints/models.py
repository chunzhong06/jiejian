# 权限断裂诊断的严格输出模型与内部事实。
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from product.backend.domain.verification.continuity import AuthorizationContinuityAssessment, AuthorizationContinuityState
from product.backend.domain.verification.facts import ObservedEffect
from product.backend.domain.verification.trace import TraceEvent


_PUBLIC_ID = r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}$"


_REASON_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


class BreakpointType(StrEnum):
    AUTHORIZATION_MISSING = "AUTHORIZATION_MISSING"
    AUTHORIZATION_LATE = "AUTHORIZATION_LATE"
    AUTHORIZATION_BYPASS = "AUTHORIZATION_BYPASS"
    IDENTITY_SUBSTITUTION = "IDENTITY_SUBSTITUTION"
    AUTHORITY_EXPANSION = "AUTHORITY_EXPANSION"
    COMPENSATION_MASKING = "COMPENSATION_MASKING"


class BreakpointPrecision(StrEnum):
    EXACT = "EXACT"
    RANGE = "RANGE"
    VIOLATION_ONLY = "VIOLATION_ONLY"


class _BreakpointModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )


class BreakpointResult(_BreakpointModel):
    case_id: str = Field(pattern=_PUBLIC_ID)
    action_id: str = Field(pattern=_PUBLIC_ID)
    breakpoint_type: BreakpointType | None
    precision: BreakpointPrecision
    last_known_good_event_id: str | None = Field(default=None, pattern=_PUBLIC_ID)
    first_violation_event_id: str | None = Field(default=None, pattern=_PUBLIC_ID)
    range_start_event_id: str | None = Field(default=None, pattern=_PUBLIC_ID)
    range_end_event_id: str | None = Field(default=None, pattern=_PUBLIC_ID)
    continuity: AuthorizationContinuityAssessment
    orphan_effect_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    downstream_event_ids: tuple[str, ...] = Field(default=(), max_length=512)
    amplifier_types: tuple[BreakpointType, ...] = Field(default=(), max_length=5)
    evidence_refs: tuple[str, ...] = Field(min_length=1, max_length=128)
    reason_codes: tuple[str, ...] = Field(min_length=1, max_length=32)

    @field_validator(
        "orphan_effect_ids",
        "downstream_event_ids",
        "evidence_refs",
    )
    @classmethod
    def validate_unique_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values):
            raise ValueError("breakpoint ID references must be unique")
        return values

    @field_validator("amplifier_types")
    @classmethod
    def validate_amplifiers(
        cls, values: tuple[BreakpointType, ...]
    ) -> tuple[BreakpointType, ...]:
        if len(set(values)) != len(values):
            raise ValueError("breakpoint amplifier types must be unique")
        return values

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values) or any(
            _REASON_CODE.fullmatch(value) is None for value in values
        ):
            raise ValueError("breakpoint reason codes must be stable unique tokens")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_precision_shape(self) -> BreakpointResult:
        if (
            self.continuity.state
            is not AuthorizationContinuityState.ORPHAN_EFFECT_CONFIRMED
            or self.continuity.case_id != self.case_id
            or self.continuity.action_id != self.action_id
            or set(self.orphan_effect_ids)
            != {item.effect_id for item in self.continuity.confirmed_effects}
        ):
            raise ValueError("breakpoint must reuse its confirmed continuity assessment")
        if self.breakpoint_type is not None and self.breakpoint_type in self.amplifier_types:
            raise ValueError("primary breakpoint cannot also be an amplifier")
        if self.precision is BreakpointPrecision.EXACT:
            if self.breakpoint_type is None or self.first_violation_event_id is None:
                raise ValueError("EXACT breakpoint requires a type and first violation event")
            if self.range_start_event_id is not None or self.range_end_event_id is not None:
                raise ValueError("EXACT breakpoint cannot carry a range")
        elif self.precision is BreakpointPrecision.RANGE:
            if (
                self.breakpoint_type is None
                or self.first_violation_event_id is not None
                or self.range_start_event_id is None
                or self.range_end_event_id is None
            ):
                raise ValueError("RANGE breakpoint requires only range boundaries")
        elif (
            self.last_known_good_event_id is not None
            or self.range_start_event_id is not None
            or self.range_end_event_id is not None
        ):
            raise ValueError("VIOLATION_ONLY cannot claim a stable trace boundary")
        return self


@dataclass(frozen=True, slots=True)
class _Candidate:
    breakpoint_type: BreakpointType
    event_id: str
    orphan_event_ids: tuple[str, ...]
    reason_code: str


@dataclass(frozen=True, slots=True)
class _AllowControlEvent:
    event: TraceEvent
    parent_roles: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _LocatedEffect:
    effect_id: str
    resource_id: str
    state: ObservedEffect


@dataclass(frozen=True, slots=True)
class _AuthorizationScope:
    known_subject_ids: frozenset[str]
    legal_actions: frozenset[str]
    legal_resources: frozenset[str]
    invariant_action: str
    invariant_resources: frozenset[str]
