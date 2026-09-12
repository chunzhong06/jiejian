# 验证当前实验的业务效果、真实身份、恢复、闭合与全计划三态矩阵。
import json

import pytest
from pydantic import ValidationError

from product.backend.core.lifecycle import CaseVerdict, RunVerdict
from product.backend.core.verification.checks import (
    CheckDecisionInput, CheckEffectFact, aggregate_check_verdict, evaluate_check_case,
    project_check_effect_facts,
)
from product.protocols.execution_v3 import ExecutionCase
from tests.fixtures.check_plan import plan, prepared_action


def decision_input(*, deny=True, superset=False, effect="ABSENT", **overrides):
    cases = plan(prepared_action(superset=superset)).actions[0].cases
    chosen = next(case for case in cases if (case.permission.expectation == "DENY") == deny
                  and (deny or "ALLOW_REGRESSION" in case.roles))
    case = ExecutionCase.model_validate_json(chosen.model_dump_json())
    effects = tuple(CheckEffectFact(effect_id=proof.effect_id, proof_fingerprint=proof.proof_fingerprint,
        state=effect, complete=True, reliable=True, correlated=True, authoritative=True, closure="CLOSED")
        for proof in case.proof_requirements)
    return CheckDecisionInput(case=case, **(dict(execution="DENIED" if deny else "ACCEPTED",
        actual_identity="MATCH", run_correlated=True, resource_correlated=True, baseline_trusted=True,
        recovery_verified=True, allow_control_verdict=CaseVerdict.SAFE, effects=effects) | overrides))


def test_explicit_denial_with_authoritative_forbidden_effect_blocks():
    result = evaluate_check_case(decision_input(effect="CONFIRMED"))
    assert result.verdict is CaseVerdict.VULNERABLE
    assert result.reason_codes == ("ORPHAN_EFFECT_CONFIRMED",)
    assert result.confirmed_forbidden_effect_ids


@pytest.mark.parametrize("later_state", ["ABSENT", "UNKNOWN"])
def test_later_observation_does_not_erase_confirmed_effect(later_state):
    from product.protocols.check_result import CheckObservation
    facts = decision_input(effect="CONFIRMED")
    proof = facts.case.proof_requirements[0]
    observation = CheckObservation(effect_id=proof.effect_id, proof_fingerprint=proof.proof_fingerprint,
        observer_id="proof", level=proof.level, phase="AFTER", state="CONFIRMED", closure="OPEN",
        complete=True, reliable=True, correlated=True, authoritative=True, window_start_us=1, window_end_us=2)
    later = observation.model_copy(update={"phase": "EVENTUAL", "state": later_state, "closure": "CLOSED"})
    projected = project_check_effect_facts(facts.case, (observation, later))
    assert projected[0].state == "CONFIRMED"
    assert evaluate_check_case(facts.model_copy(update={"effects": projected})).verdict is CaseVerdict.VULNERABLE


def test_partial_final_observation_cannot_prove_absence():
    from product.protocols.check_result import CheckObservation
    facts = decision_input()
    proof = facts.case.proof_requirements[0]
    observation = CheckObservation(effect_id=proof.effect_id, proof_fingerprint=proof.proof_fingerprint,
        observer_id="proof", level=proof.level, phase="AFTER", state="ABSENT", closure="CLOSED",
        complete=True, reliable=True, correlated=True, authoritative=True, window_start_us=1, window_end_us=2)
    partial = observation.model_copy(update={"phase": "EVENTUAL", "complete": False})
    projected = project_check_effect_facts(facts.case, (observation, partial))
    assert projected[0].state == "UNKNOWN"
    assert evaluate_check_case(facts.model_copy(update={"effects": projected})).verdict is CaseVerdict.INCONCLUSIVE


@pytest.mark.parametrize("changes", [
    {"execution": "FAILED"}, {"baseline_trusted": False}, {"recovery_verified": False},
    {"allow_control_verdict": CaseVerdict.INCONCLUSIVE},
])
def test_confirmed_attributed_violation_survives_other_failures(changes):
    assert evaluate_check_case(decision_input(effect="CONFIRMED", **changes)).verdict is CaseVerdict.VULNERABLE


@pytest.mark.parametrize("changes", [
    {"actual_identity": "UNKNOWN"}, {"actual_identity": "MISMATCH"},
    {"run_correlated": False}, {"resource_correlated": False},
])
def test_confirmed_raw_observation_cannot_replace_attribution(changes):
    facts = decision_input(effect="CONFIRMED", **changes)
    assert evaluate_check_case(facts).verdict is CaseVerdict.INCONCLUSIVE
    assert facts.effects[0].state == "CONFIRMED"


def test_accepted_without_business_effect_is_inconclusive():
    result = evaluate_check_case(decision_input(execution="ACCEPTED"))
    assert result.verdict is CaseVerdict.INCONCLUSIVE
    assert "UNAUTHORIZED_EXECUTION_ACCEPTED" in result.reason_codes


@pytest.mark.parametrize("changes", [
    {"execution": "FAILED"}, {"execution": "UNKNOWN"}, {"baseline_trusted": False},
    {"recovery_verified": False}, {"actual_identity": "UNKNOWN"}, {"resource_correlated": False},
    {"allow_control_verdict": None}, {"allow_control_verdict": CaseVerdict.INCONCLUSIVE},
    {"effects": ()},
])
def test_absence_requires_all_safe_preconditions(changes):
    assert evaluate_check_case(decision_input(**changes)).verdict is CaseVerdict.INCONCLUSIVE


@pytest.mark.parametrize("deny,effect", [(True, "ABSENT"), (False, "CONFIRMED")])
@pytest.mark.parametrize("change", [
    {"closure": "OPEN"}, {"closure": "UNKNOWN"}, {"state": "UNKNOWN"},
    {"complete": False}, {"reliable": False}, {"correlated": False}, {"authoritative": False},
])
def test_observation_gaps_do_not_prove_safety(deny, effect, change):
    facts = decision_input(deny=deny, effect=effect)
    updated = facts.effects[0].model_copy(update=change)
    assert evaluate_check_case(facts.model_copy(update={"effects": (updated,)})).verdict is CaseVerdict.INCONCLUSIVE


def test_closed_denial_and_complete_allow_can_be_safe():
    assert evaluate_check_case(decision_input()).verdict is CaseVerdict.SAFE
    assert evaluate_check_case(decision_input(deny=False, effect="CONFIRMED")).verdict is CaseVerdict.SAFE


@pytest.mark.parametrize("changes", [
    {"execution": "DENIED"}, {"effect": "ABSENT"}, {"recovery_verified": False},
])
def test_allow_rejection_missing_effect_or_recovery_is_inconclusive(changes):
    assert evaluate_check_case(decision_input(deny=False, **({"effect": "CONFIRMED"} | changes))).verdict is CaseVerdict.INCONCLUSIVE


def test_allow_superset_must_prove_every_regression_effect():
    facts = decision_input(deny=False, superset=True, effect="CONFIRMED")
    assert len(facts.effects) == 2
    assert evaluate_check_case(facts.model_copy(update={"effects": facts.effects[:1]})).verdict is CaseVerdict.INCONCLUSIVE


@pytest.mark.parametrize("tamper", ["duplicate", "wrong_proof", "wrong_effect"])
def test_facts_cannot_reference_another_case_proof(tamper):
    payload = decision_input().model_dump(mode="json")
    if tamper == "duplicate":
        payload["effects"].append(payload["effects"][0])
    elif tamper == "wrong_proof":
        payload["effects"][0]["proof_fingerprint"] = "0" * 64
    else:
        payload["effects"][0]["effect_id"] = "bef_" + "0" * 32
    with pytest.raises(ValidationError):
        CheckDecisionInput.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("verdicts,count,gaps,expected", [
    ((CaseVerdict.SAFE,), 1, False, RunVerdict.PASS),
    ((CaseVerdict.SAFE,), 2, False, RunVerdict.INCONCLUSIVE),
    ((CaseVerdict.SAFE,), 1, True, RunVerdict.INCONCLUSIVE),
    ((), 0, False, RunVerdict.INCONCLUSIVE),
    ((CaseVerdict.ERROR,), 1, False, RunVerdict.INCONCLUSIVE),
    ((CaseVerdict.SKIPPED,), 1, False, RunVerdict.INCONCLUSIVE),
    ((CaseVerdict.VULNERABLE,), 2, True, RunVerdict.BLOCK),
])
def test_run_aggregation_covers_full_plan(verdicts, count, gaps, expected):
    assert aggregate_check_verdict(verdicts, planned_case_count=count, has_gaps=gaps) is expected
