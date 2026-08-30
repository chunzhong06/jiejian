# =============================================================================
# 业务后果授权连续性
#
# 定位
#   只凭冻结权限契约、差分孪生和已形成的安全效果事实，判断受保护后果
#   是否仍具有符合原权限要求的合法来源。
#
# 职责
#   统一孤儿后果判断｜对缺失或不可靠事实保持 UNKNOWN｜证明闭合 ABSENT 的连续性
#
# 边界
#   不读取 Ledger、目标现场、Trace 或源码，不执行请求，也不形成或改变 Verdict。
# =============================================================================

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from product.backend.core.verification.differential import PermissionTwin
from product.backend.core.verification.facts import (
    ObservedEffect,
    SecurityEffectFact,
    TemporalClosure,
)
from product.backend.core.verification.permissions import (
    PermissionContract,
    PermissionExpectation,
)


_PUBLIC_ID = r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}$"
_REASON_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


class AuthorizationContinuityState(StrEnum):
    INTACT = "INTACT"
    ORPHAN_EFFECT_CONFIRMED = "ORPHAN_EFFECT_CONFIRMED"
    UNKNOWN = "UNKNOWN"


class _ContinuityModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )


class AuthorizationEffectReference(_ContinuityModel):
    effect_id: str = Field(pattern=_PUBLIC_ID)
    resource_id: str = Field(pattern=_PUBLIC_ID)


class AuthorizationContinuityAssessment(_ContinuityModel):
    """冻结 DENY Case 的纯判断结果；它不是新的安全 Verdict。"""

    case_id: str = Field(pattern=_PUBLIC_ID)
    action_id: str = Field(pattern=_PUBLIC_ID)
    state: AuthorizationContinuityState
    protected_effects: tuple[AuthorizationEffectReference, ...] = Field(
        min_length=1,
        max_length=4096,
    )
    confirmed_effects: tuple[AuthorizationEffectReference, ...] = Field(
        default=(),
        max_length=4096,
    )
    unknown_effects: tuple[AuthorizationEffectReference, ...] = Field(
        default=(),
        max_length=4096,
    )
    reason_codes: tuple[str, ...] = Field(min_length=1, max_length=64)

    @field_validator("protected_effects", "confirmed_effects", "unknown_effects")
    @classmethod
    def validate_unique_effects(
        cls,
        values: tuple[AuthorizationEffectReference, ...],
    ) -> tuple[AuthorizationEffectReference, ...]:
        keys = {(item.effect_id, item.resource_id) for item in values}
        if len(keys) != len(values):
            raise ValueError("authorization continuity effect references must be unique")
        return tuple(sorted(values, key=lambda item: (item.effect_id, item.resource_id)))

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values) or any(
            _REASON_CODE.fullmatch(value) is None
            for value in values
        ):
            raise ValueError("authorization continuity reason codes must be stable tokens")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_state_shape(self) -> AuthorizationContinuityAssessment:
        protected = set(self.protected_effects)
        confirmed = set(self.confirmed_effects)
        unknown = set(self.unknown_effects)
        if not confirmed.issubset(protected) or not unknown.issubset(protected):
            raise ValueError("continuity result references an unprotected effect")
        if confirmed.intersection(unknown):
            raise ValueError("continuity effect cannot be both confirmed and unknown")
        if self.state is AuthorizationContinuityState.ORPHAN_EFFECT_CONFIRMED:
            if not confirmed:
                raise ValueError("confirmed orphan continuity requires a confirmed effect")
        elif self.state is AuthorizationContinuityState.UNKNOWN:
            if confirmed or not unknown:
                raise ValueError("unknown continuity requires only unknown protected effects")
        elif confirmed or unknown:
            raise ValueError("intact continuity requires every protected effect to be absent")
        return self


def assess_authorization_continuity(
    contract: PermissionContract,
    twin: PermissionTwin,
    effect_facts: tuple[SecurityEffectFact, ...],
) -> AuthorizationContinuityAssessment:
    """判断冻结 DENY Case 的受保护后果，不借 Trace 或当前现场补充授权。"""

    _validate_frozen_deny_scope(contract, twin)
    action = next(
        item for item in contract.actions if item.action_id == twin.invariant.action_id
    )
    protected = tuple(
        AuthorizationEffectReference(effect_id=effect_id, resource_id=resource_id)
        for effect_id in action.effect_ids
        for resource_id in twin.invariant.resource_ids
    )
    protected_keys = {(item.effect_id, item.resource_id) for item in protected}
    matching = tuple(
        item
        for item in effect_facts
        if (item.effect_id, item.resource_id) in protected_keys
    )
    by_key = {(item.effect_id, item.resource_id): item for item in matching}
    if len(by_key) != len(matching):
        raise ValueError("continuity facts must be unique per protected effect and resource")

    confirmed = tuple(
        reference
        for reference in protected
        if (fact := by_key.get((reference.effect_id, reference.resource_id))) is not None
        and fact.state is ObservedEffect.CONFIRMED
    )
    if confirmed:
        return AuthorizationContinuityAssessment(
            case_id=twin.deny_case.case_id,
            action_id=twin.invariant.action_id,
            state=AuthorizationContinuityState.ORPHAN_EFFECT_CONFIRMED,
            protected_effects=protected,
            confirmed_effects=confirmed,
            reason_codes=("DENY_PROTECTED_EFFECT_CONFIRMED",),
        )

    unknown = tuple(
        reference
        for reference in protected
        if not _is_reliably_absent(
            by_key.get((reference.effect_id, reference.resource_id))
        )
    )
    if unknown:
        return AuthorizationContinuityAssessment(
            case_id=twin.deny_case.case_id,
            action_id=twin.invariant.action_id,
            state=AuthorizationContinuityState.UNKNOWN,
            protected_effects=protected,
            unknown_effects=unknown,
            reason_codes=("PROTECTED_EFFECT_EVIDENCE_INCOMPLETE",),
        )
    return AuthorizationContinuityAssessment(
        case_id=twin.deny_case.case_id,
        action_id=twin.invariant.action_id,
        state=AuthorizationContinuityState.INTACT,
        protected_effects=protected,
        reason_codes=("ALL_PROTECTED_EFFECTS_RELIABLY_ABSENT",),
    )


def _validate_frozen_deny_scope(
    contract: PermissionContract,
    twin: PermissionTwin,
) -> None:
    if any(
        expectation is not PermissionExpectation.DENY
        for expectation in twin.deny_case.expectations
    ):
        raise ValueError("authorization continuity requires a frozen DENY case")
    action = next(
        (item for item in contract.actions if item.action_id == twin.invariant.action_id),
        None,
    )
    resources = {item.resource_id for item in contract.resources}
    subjects = {item.subject_id for item in contract.subjects}
    if (
        action is None
        or not action.effect_ids
        or twin.deny_case.subject_id not in subjects
        or any(
            resource_id not in resources
            for resource_id in twin.invariant.resource_ids
        )
    ):
        raise ValueError("continuity twin is outside the frozen contract")


def _is_reliably_absent(fact: SecurityEffectFact | None) -> bool:
    return (
        fact is not None
        and fact.state is ObservedEffect.ABSENT
        and fact.complete
        and fact.reliable
        and fact.correlated
        and fact.temporal_closure is TemporalClosure.CLOSED
        and fact.baseline_integrity
    )


__all__ = [
    "AuthorizationContinuityAssessment",
    "AuthorizationContinuityState",
    "AuthorizationEffectReference",
    "assess_authorization_continuity",
]
