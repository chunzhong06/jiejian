# 原题纯投影反例：空历史回归仍强制新控制、证据等价和完整计划，不因普通 PASS 冒充修复。
from types import SimpleNamespace

import pytest

from product.backend.core.check_repair import repair_case_identity, repair_context, verify_current_repair
from product.backend.core.lifecycle import CaseVerdict, RunVerdict
from product.backend.workflows.checks.repair import build_current_repair_contract
from product.protocols.check_result import CheckCaseOutcome, CheckObservation
from product.protocols.execution_v3 import ChangeContext
from tests.fixtures.check_execution import execution_pair


def package(*, allow_safe=True, forbidden=True, run_id="run_"+"1"*32):
    request,bundle = execution_pair(state_changing=True)
    results,documents = [],[]
    for action in request.actions:
        for case in action.cases:
            deny = case.permission.expectation == "DENY"
            outcome = CheckCaseOutcome(execution_outcome="DENIED" if deny else "ACCEPTED",actual_identity_status="MATCH",
                baseline_trusted=True,recovery_verified=True,run_correlated=True,resource_correlated=True)
            evidence_id = "ev_"+("d" if deny else "a")*64
            verdict = (CaseVerdict.VULNERABLE if forbidden else CaseVerdict.SAFE) if deny else (
                CaseVerdict.SAFE if allow_safe else CaseVerdict.INCONCLUSIVE)
            results.append(SimpleNamespace(case_id=case.case_id,verdict=verdict,outcome=outcome,evidence_ids=(evidence_id,)))
            observations = tuple(CheckObservation(effect_id=proof.effect_id,proof_fingerprint=proof.proof_fingerprint,
                observer_id=proof.reference.observer_id,level="VERDICT_REQUIRED",phase="AFTER",
                state="CONFIRMED" if forbidden or not deny else "ABSENT",closure="CLOSED",complete=True,reliable=True,
                correlated=True,authoritative=True,window_start_us=1,window_end_us=2) for proof in case.proof_requirements)
            documents.append(SimpleNamespace(evidence_id=evidence_id,observations=observations))
    return SimpleNamespace(request=request,bundle=bundle,evidence=tuple(documents),
        result=SimpleNamespace(run_id=run_id,case_results=tuple(results),verdict=RunVerdict.BLOCK if forbidden else
            RunVerdict.PASS if allow_safe else RunVerdict.INCONCLUSIVE))


def contract_and_new(*, historical_safe=True, new_safe=True, forbidden=False):
    source = package(allow_safe=historical_safe)
    deny = next(case for action in source.request.actions for case in action.cases if case.permission.expectation == "DENY")
    contract = build_current_repair_contract(source,deny.case_id)
    current = package(allow_safe=new_safe,forbidden=forbidden,run_id="run_"+"2"*32)
    change = ChangeContext(change_id="chg_"+"3"*32,impact_fingerprint="4"*64,
        required_intent_ids=tuple(sorted(ref.intent_id for ref in contract.original_intents)))
    payload = current.request.model_dump(mode="json")
    payload.update(change_context=change.model_dump(mode="json"),repair_context=repair_context(contract).model_dump(mode="json"))
    current.request = type(current.request).model_validate(payload,strict=False)
    return contract,current,change


@pytest.mark.parametrize("historical_safe",[False,True])
@pytest.mark.parametrize("new_safe,forbidden,expected",[(True,False,"VERIFIED"),(False,False,"INCONCLUSIVE"),(False,True,"NOT_VERIFIED")])
def test_repair_empty_history_never_removes_new_control_requirement(historical_safe,new_safe,forbidden,expected):
    contract,current,change = contract_and_new(historical_safe=historical_safe,new_safe=new_safe,forbidden=forbidden)
    assert bool(contract.regressions) is historical_safe
    assert bool(repair_context(contract).allow_regression_case_fingerprints) is historical_safe
    result = verify_current_repair(contract,request=current.request,bundle=current.bundle,result=current.result,
        evidence=current.evidence,expected_change_context=change)
    assert result.status == expected


@pytest.mark.parametrize("fault",["same_run","ordinary_pass","change","policy","standard"])
def test_repair_rejects_wrong_run_context_policy_or_standard(fault):
    contract,current,change = contract_and_new()
    if fault == "same_run":
        current.result.run_id = contract.source_run_id
    elif fault == "ordinary_pass":
        current.request = current.request.model_copy(update={"repair_context":None})
    elif fault == "change":
        change = change.model_copy(update={"change_id":"chg_"+"f"*32})
    elif fault == "policy":
        current.request = current.request.model_copy(update={"policy_epoch":current.request.policy_epoch+1})
    else:
        action = current.bundle.actions[0]
        proof = action.proofs[0].model_copy(update={"exclusive_resource_window":not action.proofs[0].exclusive_resource_window})
        current.bundle = current.bundle.model_copy(update={"actions":(action.model_copy(update={"proofs":(proof,)}),)})
    result = verify_current_repair(contract,request=current.request,bundle=current.bundle,result=current.result,
        evidence=current.evidence,expected_change_context=change)
    assert result.status == ("STALE" if fault == "policy" else "INCONCLUSIVE")


def test_case_identity_excludes_recording_source_configuration_but_preserves_business_identity():
    source = package()
    action,case = source.request.actions[0],source.request.actions[0].cases[0]
    identity = repair_case_identity(action,case)
    changed = case.model_copy(update={"case_id":"case_"+"f"*32,"source_fingerprint":"e"*64,"config_fingerprint":"d"*64,
        "resource_binding_fingerprint":"c"*64})
    assert repair_case_identity(action,changed) == identity
    changed = changed.model_copy(update={"resource_id":"different-resource"})
    assert repair_case_identity(action,changed).fingerprint() != identity.fingerprint()
