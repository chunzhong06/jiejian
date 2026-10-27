# 验证情境摘录、有限选项及当前格式严格读取；客户端不能伪造已确认来源。
import json
from copy import deepcopy

import pytest
from pydantic import ValidationError
from product.backend.domain.boundaries.rule_candidates import RuleCandidateSave, read_candidate_revision


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


def test_candidate_reader_requires_current_identity_and_rejects_unknown_fields():
    from product.backend.domain.boundaries.rule_candidates import RuleCandidateRevision
    from product.protocols.codec import encode_json
    root = RuleCandidateRevision.model_validate_json(json.dumps({
        'project_id':'project', 'candidate_id':'rcd_'+'1'*32, 'revision':1,
        'basis_id':'rb_'+'a'*64, 'content':{'original_text':'既有约定'},
        'submitted_via':'MCP', 'created_at_us':0})).model_dump(mode='json')
    assert read_candidate_revision(encode_json(root).decode()).schema_version == '1'
    for changes in ({'schema_version':'999'}, {'document_type':'old-candidate'}, {'unknown':True}):
        with pytest.raises(ValueError):
            read_candidate_revision(encode_json(root | changes).decode())
    with pytest.raises(ValueError):
        read_candidate_revision(' '*1048577)
