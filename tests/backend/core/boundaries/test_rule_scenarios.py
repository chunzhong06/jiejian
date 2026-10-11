# 验证情境摘录、有限选项及双版本严格读取；客户端不能伪造已确认来源。
import json
from copy import deepcopy

import pytest
from pydantic import ValidationError
from product.backend.core.boundaries.rule_candidates import RuleCandidateSave, read_candidate_revision


def _input():
    permission={'item_id':'pperm_'+'1'*16,'write_mode':'CREATE','effective_state':'ACTIVE',
        'subject_actor_item_id':'pactr_'+'1'*16,'resource_owner_actor_item_id':'pactr_'+'1'*16,
        'business_action_item_id':'pactn_'+'1'*16,'relation':'OWNS','expectation':'ALLOW','protected_effect_item_ids':['peff_'+'1'*16]}
    return {'operation_id':'a'*32,'expected_basis_id':'rb_'+'b'*64,'content':{'original_text':'允许预览；允许预览',
        'permissions':[permission], 'scenarios':[{'scenario_id':'rsc_'+'1'*16,'original_excerpt':'允许预览','occurrence':2,
        'question':'能否下载？','options':[{'option_id':'rop_'+str(index)*16,'label':label,'explanation':label,
            'replacements':[{**permission,'expectation':expectation}]} for index,label,expectation in ((1,'允许下载','ALLOW'),(2,'只能预览','DENY'))]}]}}


@pytest.mark.parametrize('fault',['excerpt','occurrence','duplicate','outside','spoof','too_many'])
def test_candidate_input_rejects_unverifiable_or_unbounded_scenarios(fault):
    value=_input(); scenario=value['content']['scenarios'][0]
    if fault=='excerpt':scenario['original_excerpt']='不在原话中'
    elif fault=='occurrence':scenario['occurrence']=3
    elif fault=='duplicate':scenario['options'][1]['option_id']=scenario['options'][0]['option_id']
    elif fault=='outside':scenario['options'][0]['replacements'][0]['item_id']='pperm_'+'2'*16
    elif fault=='spoof':scenario['scenario_fingerprint']='a'*64
    elif fault=='too_many':value['content']['scenarios']=[deepcopy(scenario) for _ in range(11)]
    with pytest.raises(ValidationError):RuleCandidateSave.model_validate_json(json.dumps(value))


def test_legacy_reader_does_not_accept_new_fields_or_unknown_versions():
    root={'schema_version':'1','project_id':'project','candidate_id':'rcd_'+'1'*32,'revision':1,
        'basis_id':'rb_'+'a'*64,'content':{'original_text':'既有约定'},'submitted_via':'MCP','created_at_us':0}
    assert read_candidate_revision(json.dumps(root)).schema_version=='1'
    root['content']['scenarios']=[]
    with pytest.raises(ValidationError):read_candidate_revision(json.dumps(root))
    root['schema_version']='999'
    with pytest.raises(ValidationError):read_candidate_revision(json.dumps(root))
    with pytest.raises(ValueError):read_candidate_revision(' '*1048577)
