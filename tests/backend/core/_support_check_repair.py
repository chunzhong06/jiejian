# 所属业务域的共享测试构造器；不导入测试用例。
from types import SimpleNamespace
from product.backend.core.checks.repair import repair_context
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
