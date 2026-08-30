# 验证授权连续性只消费冻结 DENY 孪生与已形成效果事实，并保持三态闭合。

from __future__ import annotations

from pathlib import Path

import pytest

from product.backend.core.verification.continuity import (
    AuthorizationContinuityState,
    assess_authorization_continuity,
)
from product.backend.core.verification.facts import (
    ObservedEffect,
    SecurityEffectFact,
    TemporalClosure,
)
from product.backend.core.verification.permissions import PermissionContract
from product.backend.core.verification.permissions.coverage import (
    build_permission_coverage_plan,
)
from product.protocols.web.profile import WebExecutionProfile
from tests.fixtures.runner import write_web_test_profile


@pytest.fixture()
def frozen_scope(tmp_path: Path):
    profile_path, contract_path = write_web_test_profile(
        tmp_path,
        include_comparison_subject=True,
    )
    contract = PermissionContract.model_validate_json(
        contract_path.read_text(encoding="utf-8")
    )
    profile = WebExecutionProfile.model_validate_json(
        profile_path.read_text(encoding="utf-8")
    )
    coverage = build_permission_coverage_plan(
        contract,
        engine_version="coverage-v2",
        seed=profile.seed,
        case_budget=profile.case_budget,
        max_relation_depth=profile.max_relation_depth,
    )
    plan = profile.build_snapshot(contract, coverage).differential_plan
    twin = plan.twins[0]
    action = next(
        item for item in contract.actions if item.action_id == twin.invariant.action_id
    )
    effect = next(item for item in contract.effects if item.effect_id in action.effect_ids)
    return contract, twin, effect


def _fact(scope, state: ObservedEffect) -> SecurityEffectFact:
    _contract, twin, effect = scope
    known = state is not ObservedEffect.UNKNOWN
    return SecurityEffectFact(
        effect_id=effect.effect_id,
        kind=effect.kind,
        resource_id=twin.invariant.resource_ids[0],
        state=state,
        complete=known,
        reliable=known,
        correlated=known,
        temporal_closure=(
            TemporalClosure.CLOSED if known else TemporalClosure.UNKNOWN
        ),
        baseline_integrity=known,
        source_requirement_ids=("resource-state",),
        reason_codes=() if known else ("EFFECT_STATE_UNKNOWN",),
    )


def test_confirmed_protected_effect_is_orphan_without_trace(frozen_scope) -> None:
    contract, twin, _effect = frozen_scope

    result = assess_authorization_continuity(
        contract,
        twin,
        (_fact(frozen_scope, ObservedEffect.CONFIRMED),),
    )

    assert result.state is AuthorizationContinuityState.ORPHAN_EFFECT_CONFIRMED
    assert result.confirmed_effects == result.protected_effects
    assert result.unknown_effects == ()


def test_unknown_protected_effect_never_uses_surface_or_trace_as_absence(
    frozen_scope,
) -> None:
    contract, twin, _effect = frozen_scope

    result = assess_authorization_continuity(
        contract,
        twin,
        (_fact(frozen_scope, ObservedEffect.UNKNOWN),),
    )

    assert result.state is AuthorizationContinuityState.UNKNOWN
    assert result.unknown_effects == result.protected_effects


def test_closed_reliable_absence_is_intact(frozen_scope) -> None:
    contract, twin, _effect = frozen_scope

    result = assess_authorization_continuity(
        contract,
        twin,
        (_fact(frozen_scope, ObservedEffect.ABSENT),),
    )

    assert result.state is AuthorizationContinuityState.INTACT
    assert result.confirmed_effects == result.unknown_effects == ()


def test_missing_protected_effect_fact_is_unknown(frozen_scope) -> None:
    contract, twin, _effect = frozen_scope

    result = assess_authorization_continuity(contract, twin, ())

    assert result.state is AuthorizationContinuityState.UNKNOWN
    assert result.unknown_effects == result.protected_effects


def test_continuity_has_exactly_three_states() -> None:
    assert tuple(AuthorizationContinuityState) == (
        AuthorizationContinuityState.INTACT,
        AuthorizationContinuityState.ORPHAN_EFFECT_CONFIRMED,
        AuthorizationContinuityState.UNKNOWN,
    )
