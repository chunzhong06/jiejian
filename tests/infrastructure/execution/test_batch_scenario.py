"""同主体混合资源的真实 HTTP 批量，整批义务与逐项权限分别核对。"""
import hashlib
import json
from types import SimpleNamespace as NS
import pytest
from product.backend.domain.checks.plan import ProjectCheckPlan,ActionCheckPlan,CheckCase
from product.backend.domain.checks.scenarios import compile_business_scenario
from product.backend.domain.boundaries.permissions import PermissionIntentRelation
from product.backend.infrastructure.execution.check_executor import CheckExecutor
from product.backend.infrastructure.artifacts.checks.check_validation import validate_check_decisions
from product.protocols.checks.check_result import CheckAssetReference
from product.protocols.checks.execution_request import ExecutionRequest,FrozenPermission,content_hash,canonical_execution_request_bytes
from product.protocols.checks.scenarios import BusinessScenarioRevision
from tests.support.builders.checks.assurance import permission,OTHER_ACTOR
from tests.support.builders.execution.check_target import check_target,execution_configuration


@pytest.mark.parametrize('strategy,fault',[('ATOMIC',None),('ATOMIC','PARTIAL_ATOMIC'),('PER_ITEM',None),('PER_ITEM','UNAUTHORIZED')])
def test_mixed_batch_obligations_have_full_normal_control_and_one_request(tmp_path,check_target,strategy,fault):
    def configure(payload):
        payload['target']['max_requests']=500;payload['budget']['max_requests']=500;payload['budget']['recovery_reserve_requests']=30
        admin=json.loads(json.dumps(payload['identities'][0]));admin.update(identity_id='tid_'+f'{3:032x}',actor_id=OTHER_ACTOR,identity_fingerprint=f'{3:064x}')
        admin['binding']['secret_ref']='env:CHECK_TEST_3'
        admin['verification'].update(expected_actor_id=OTHER_ACTOR,expected_application_subject_id='subject-3')
        payload['identities'].append(admin)
        payload['actions'][0]['steps'][0]['request']=dict(method='POST',path='/bulk',body=dict(kind='JSON',value={'items':[{'id':{'$slot':'resource'}}]}),
            input_slots=[dict(slot_id='resource',source='CASE_RESOURCE_ID',consumer='JSON_BODY')])
    request,bundle,runner,environment=execution_configuration(check_target,configure=configure)
    action=request.actions[0];base=next(case for case in action.cases if case.permission.expectation=='ALLOW')
    member='tid_'+f'{2:032x}';admin='tid_'+f'{3:032x}'
    admin_permission=permission(3,subject=OTHER_ACTOR,relation=PermissionIntentRelation.OTHER_ROLE)
    frozen=FrozenPermission.model_validate_json(json.dumps({name:getattr(admin_permission,name) for name in FrozenPermission.model_fields}))
    def clone(subject,owner,resource,rule):
        raw=base.model_dump(mode='json',exclude={'case_id'})
        raw.update(subject_test_identity_id=subject,subject_identity_fingerprint=f'{int(subject[-32:],16):064x}',
            subject_actor_id=rule.subject_actor_id,resource_owner_test_identity_id=owner,owner_identity_fingerprint=f'{int(owner[-32:],16):064x}',
            resource_id=resource,permission=rule.model_dump(mode='json'),roles=['ALLOW_REGRESSION'],resource_binding_fingerprint=hashlib.sha256(resource.encode()).hexdigest())
        for proof in raw['proof_requirements']:
            proof['resource_id']=resource
            proof['proof_fingerprint']=content_hash('EffectProofRequirement',{key:value for key,value in proof.items() if key!='proof_fingerprint'})
        identity=content_hash('CheckCase',dict(action_id=action.action_id,revision=action.action_revision,
            facts={key:value for key,value in raw.items() if key!='roles'}))
        return CheckCase.model_validate_json(json.dumps(dict(raw,case_id='case_'+identity[:32])))
    own_two=clone(member,member,'resource-2',base.permission)
    normal_one=clone(admin,base.subject_test_identity_id,'resource-1',frozen)
    normal_two=clone(admin,member,'resource-2',frozen)
    action_plan=ActionCheckPlan.model_validate_json(json.dumps(action.model_dump(mode='json')|dict(
        cases=[case.model_dump(mode='json') for case in (*action.cases,own_two,normal_one,normal_two)],gaps=[])))
    plan=ProjectCheckPlan(project_id=request.project_id,source_fingerprint=request.source_fingerprint,policy_epoch=request.policy_epoch,
        engine_version=request.engine_version,actions=(action_plan,),gaps=(),plan_fingerprint=request.plan_fingerprint)
    deny=next(case for case in action.cases if case.permission.expectation=='DENY')
    def invocation(cases):
        return dict(id='mixed',label='同一请求中的三项',batch=dict(strategy=strategy,array_path=['items']),items=[dict(id='item'+str(index),
            subject_identity_id=case.subject_test_identity_id,resource_id=case.resource_id,
            permission={key:getattr(case.permission,key) for key in ('intent_id','revision','intent_hash')}) for index,case in enumerate(cases)])
    document=BusinessScenarioRevision.model_validate_json(json.dumps(dict(id='bsc_'+'b'*32,project_id=request.project_id,revision=1,label='混合资源批量',experiments=[
        dict(id='normal',label='管理员正常对照',kind='NORMAL',invocations=[invocation((normal_two,normal_one,normal_two))]),
        dict(id='limited',label='成员同批操作',kind='CHANGE_SUBJECT',control_experiment_id='normal',invocations=[invocation((own_two,deny,own_two))]) ])))
    compiled=compile_business_scenario(plan,document,bundle)
    assert not compiled.gaps,compiled.gaps
    raw=request.model_dump(mode='json');raw.update(actions=[item.model_dump(mode='json',exclude={'gaps'}) for item in compiled.actions],scenario=compiled.scenario.model_dump(mode='json'),plan_fingerprint=compiled.plan_fingerprint)
    request=ExecutionRequest.model_validate_json(json.dumps(raw))
    digest=hashlib.sha256(canonical_execution_request_bytes(request)).hexdigest()
    runner=runner.model_copy(update=dict(request_hash=digest,assets=(CheckAssetReference(logical_id='request',sha256=digest),CheckAssetReference(logical_id='runtime',sha256=request.config_fingerprint))))
    state=check_target[1];state.update(cases={case.case_id:case for action in request.actions for case in action.cases},values={'resource-1':'original','resource-2':'original'},batch_strategy=strategy,batch_fault=fault)
    output=CheckExecutor(request,bundle,runner,environ=environment,attempt_dir=tmp_path,cancellation_requested=lambda:False).execute()
    assert output.result.verdict.value==('PASS' if fault is None else 'BLOCK'),output.result
    selected=next(item.case_ids for item in request.scenario.invocations if item.experiment_id=='limited')
    outcomes={item.case_id:item for item in output.result.case_results}
    assert all(outcomes[key].verdict.value=='SAFE' for key in selected) if fault is None else any(outcomes[key].verdict.value=='VULNERABLE' for key in selected)
    assert len(state['target_calls'])==2
    assert [item['id'] for item in state['batch_payloads'][-1]['items']]==['resource-2','resource-1','resource-2']
    assert state['values']=={'resource-1':'original','resource-2':'original'}
    validate_check_decisions(NS(request=request,result=output.result,evidence=output.evidence))


pytestmark=pytest.mark.level4
