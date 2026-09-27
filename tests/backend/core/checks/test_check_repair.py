# 原题纯投影反例：空历史回归仍强制新控制、证据等价和完整计划，不因普通 PASS 冒充修复。

import pytest

from product.backend.core.checks.repair import repair_case_identity, repair_context, verify_current_repair
from tests.backend.core._support_check_repair import (
    contract_and_new,
    package,
)






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
