# 验证当前冻结执行计划的孤儿后果归因，不通过旧权限合同或重新判定得到结论。
import pytest

from product.backend.core.lifecycle import CaseVerdict
from product.backend.core.verification.checks import CheckDecisionInput, CheckEffectFact
from product.backend.core.verification.continuity import (
    AuthorizationContinuityState as State,
    assess_check_authorization_continuity,
)
from tests.fixtures.check_execution import execution_pair


def current_facts(state="CONFIRMED", **changes):
    request, _ = execution_pair()
    action = request.actions[0]
    case = next(case for case in action.cases if case.permission.expectation == "DENY")
    values = dict(case=case, execution="DENIED", actual_identity="MATCH", run_correlated=True,
        resource_correlated=True, baseline_trusted=True, recovery_verified=True,
        allow_control_verdict=CaseVerdict.SAFE,
        effects=tuple(CheckEffectFact(effect_id=proof.effect_id, proof_fingerprint=proof.proof_fingerprint,
            state=state, complete=True, reliable=True, correlated=True, authoritative=True,
            closure="CLOSED") for proof in case.proof_requirements))
    return action, CheckDecisionInput(**(values | changes))


@pytest.mark.parametrize("changes", [{}, {"execution": "FAILED"}, {"recovery_verified": False},
                                     {"baseline_trusted": False}, {"allow_control_verdict": None}])
def test_confirmed_orphan_survives_execution_recovery_and_control_gaps(changes):
    action, facts = current_facts(**changes)
    result = assess_check_authorization_continuity(action, facts)
    assert result.state is State.ORPHAN_EFFECT_CONFIRMED
    assert {item.effect_id for item in result.confirmed_effects} == set(facts.case.protected_effect_ids)


@pytest.mark.parametrize("changes", [{"actual_identity": "UNKNOWN"}, {"actual_identity": "MISMATCH"},
                                     {"run_correlated": False}, {"resource_correlated": False}])
def test_raw_confirmation_without_identity_and_run_attribution_is_unknown(changes):
    action, facts = current_facts(**changes)
    assert assess_check_authorization_continuity(action, facts).state is State.UNKNOWN


@pytest.mark.parametrize("field", ["complete", "reliable", "correlated", "authoritative"])
def test_untrusted_source_cannot_establish_orphan(field):
    action, facts = current_facts()
    effects = tuple(item.model_copy(update={field: False}) for item in facts.effects)
    result = assess_check_authorization_continuity(action, facts.model_copy(update={"effects": effects}))
    assert result.state is State.UNKNOWN


def test_absence_requires_closed_observation_and_trusted_baseline():
    action, facts = current_facts("ABSENT")
    assert assess_check_authorization_continuity(action, facts).state is State.INTACT
    assert assess_check_authorization_continuity(action, facts.model_copy(update={"baseline_trusted": False})).state is State.UNKNOWN
    effects = tuple(item.model_copy(update={"closure": "OPEN"}) for item in facts.effects)
    assert assess_check_authorization_continuity(action, facts.model_copy(update={"effects": effects})).state is State.UNKNOWN


def test_current_continuity_rejects_case_outside_action_and_allow_case():
    action, facts = current_facts()
    with pytest.raises(ValueError, match="outside"):
        assess_check_authorization_continuity(action.model_copy(update={"cases": ()}), facts)
    case = next(case for case in action.cases if case.permission.expectation == "ALLOW")
    with pytest.raises(ValueError, match="DENY"):
        assess_check_authorization_continuity(action, facts.model_copy(update={"case": case}))
