# 来源配置只接受有限只读位置和身份引用，拒绝秘密、可执行输入和自我声明的可靠性。
import json
import pytest
from pydantic import ValidationError
from product.protocols.preparation.proof_sources import ProofSourceConfig, SourceReadScope


def config():
    return dict(action_id='bac_'+'1'*32,action_revision=1,effect_id='bef_'+'1'*32,
        observation_identity_id='tid_'+'1'*32,resource_binding_id='res_'+'1'*32,
        relative_path_template='/api/resources/{resource_id}',mappings={'resource_id':['id'],'owner_id':['owner_id']},
        source_contract_id='OWNER_RESOURCE_VIEW_V1',identity_claims=[{'identity_id':'tid_'+'1'*32,'application_subject_id':'alice'}],source_files=['app.mjs'])


@pytest.mark.parametrize('key,value',[
    ('relative_path_template','https://external.invalid/{resource_id}'),
    ('relative_path_template','//external.invalid/{resource_id}'),
    ('relative_path_template','/../{resource_id}'),
    ('relative_path_template','/api/{resource_id}?all=true'),
    ('relative_path_template','/api/{resource_id}/{resource_id}'),
    ('relative_path_template','/api/{other_id}'),
    ('relative_path_template','/api/%2e%2e/{resource_id}'),
    ('mappings',{'resource_id':['id'],'owner_id':['__proto__']}),
    ('mappings',{'resource_id':['id'],'owner_id':['cookie']}),
    ('mappings',{'resource_id':['id'],'owner_id':['x']*9}),
    ('target_operation_path',['authorization']),('max_response_bytes',262145),('max_response_bytes',True),
    ('timeout_us',5000001),('source_files',['../secret.mjs']),('source_files',['app.mjs','app.mjs']),
    ('identity_claims',[]),('action_revision',True),('reliable',True),('sql','select * from anything'),
    ('code','return true'),('password','redacted-example'),('source_kind','SCRIPT'),
])
def test_source_configuration_rejects_unbounded_or_executable_inputs(key,value):
    payload=config();payload[key]=value
    with pytest.raises(ValidationError):ProofSourceConfig.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize('origin',['https://127.0.0.1:3100','http://localhost:3100','http://127.0.0.1:3100/a','http://127.0.0.1:3100?x=y','http://external.invalid:3100'])
def test_read_scope_cannot_expand_loopback_origin(origin):
    with pytest.raises(ValidationError):SourceReadScope.model_validate_json(json.dumps(dict(scope_id='prs_'+'1'*32,
        project_id='project',origin=origin,path_templates=['/api/me','/api/resources/{resource_id}'],
        identity_ids=['tid_'+'1'*32],resource_binding_ids=['res_'+'1'*32],max_response_bytes=1024,timeout_us=1000,created_at_us=0)))
