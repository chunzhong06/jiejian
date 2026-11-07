"""两个真实 HTTP 业务动作共享前提；恢复只在完整实验结束后执行。"""
import hashlib
import json
from types import SimpleNamespace as NS

import pytest
from product.backend.domain.checks.plan import compile_project_check_plan
from product.backend.domain.checks.scenarios import compile_business_scenario
from product.backend.infrastructure.artifacts.checks.check_validation import validate_check_decisions
from product.backend.infrastructure.execution.check_executor import CheckExecutor
from product.protocols.checks.check_runtime import CheckRuntimeBundle,check_runtime_fingerprint
from product.protocols.checks.check_result import CheckAssetReference
from product.protocols.checks.execution_request import ExecutionRequest,canonical_execution_request_bytes
from product.protocols.checks.scenarios import BusinessScenarioRevision
from tests.support.builders.checks.check_execution import execution_pair
from tests.support.builders.checks.check_plan import prepared_action
from tests.support.builders.execution.check_target import check_target,execution_configuration


@pytest.mark.parametrize('variant,forbidden,expected',[(None,False,'PASS'),('REORDER',False,'INCONCLUSIVE'),
    ('OMIT',False,'INCONCLUSIVE'),('REPEAT',False,'INCONCLUSIVE'),('CHANGE_SUBJECT',False,'PASS'),('CHANGE_SUBJECT',True,'BLOCK'),
    (None,False,'CANCELLED'),('CHANGE_SUBJECT','RECOVERY_FAILURE','BLOCK')])
def test_real_business_prerequisite_survives_nodes_without_extra_base_writes(tmp_path,check_target,variant,forbidden,expected):
    prepared=(prepared_action(state_changing=True),prepared_action(state_changing=True,action_number=2))
    request,bundle,runner,environment=execution_configuration(check_target)
    _,second=execution_pair(port=check_target[0],prepared=prepared[1],state_changing=True)
    payload=bundle.model_dump(mode='json');payload['actions'].extend(second.model_dump(mode='json')['actions'])
    payload['target']['max_requests']=500;payload['budget'].update(max_requests=500,recovery_reserve_requests=40)
    bundle=CheckRuntimeBundle.model_validate_json(json.dumps(payload))
    fingerprint=check_runtime_fingerprint(bundle)
    plan=compile_project_check_plan(request.project_id,source_fingerprint=bundle.source_fingerprint,policy_epoch=1,
        engine_version=request.engine_version,config_fingerprint=fingerprint,actions=prepared)
    def node(index,denied=False):
        action=plan.actions[index];case=next(case for case in action.cases if case.permission.expectation==('DENY' if denied else 'ALLOW'))
        return dict(id='review' if index==0 else 'approve',label='审阅' if index==0 else '批准',depends_on=[] if index==0 else ['review'],items=[dict(
            id='item',permission={key:getattr(case.permission,key) for key in ('intent_id','revision','intent_hash')},
            subject_identity_id=case.subject_test_identity_id,resource_id=case.resource_id)])
    normal=[node(0),node(1)]
    experiments=[dict(id='normal',label='审阅后批准',kind='NORMAL',invocations=normal)]
    if variant:
        values=json.loads(json.dumps(normal))
        if variant=='OMIT':values=values[1:]
        if variant=='REORDER':values.reverse()
        if variant=='REPEAT':values.append(values[-1]|dict(id='approve_again'))
        if variant=='CHANGE_SUBJECT':values[-1]=node(1,True)
        experiments.append(dict(id='challenge',label='检查业务变体',kind=variant,control_experiment_id='normal',invocations=values))
    document=BusinessScenarioRevision.model_validate_json(json.dumps(dict(id='bsc_'+'d'*32,project_id=request.project_id,
        revision=1,label='两步审批',experiments=experiments)))
    compiled=compile_business_scenario(plan,document,bundle)
    assert not compiled.gaps,compiled.gaps
    raw=compiled.model_dump(mode='json',exclude={'gaps'})
    for action in raw['actions']:action.pop('gaps')
    raw.update(config_fingerprint=fingerprint,budget_fingerprint=bundle.budget.fingerprint())
    request=ExecutionRequest.model_validate_json(json.dumps(raw))
    digest=hashlib.sha256(canonical_execution_request_bytes(request)).hexdigest()
    runner=runner.model_copy(update=dict(request_hash=digest,config_hash=fingerprint,assets=(
        CheckAssetReference(logical_id='request',sha256=digest),CheckAssetReference(logical_id='runtime',sha256=fingerprint))))
    state=check_target[1];state.update(cases={case.case_id:case for action in request.actions for case in action.cases},
        pipeline={case.case_id:('reviewed' if action.action_id==plan.actions[0].action_id else 'approved')
            for action in request.actions for case in action.cases},deny_effect=bool(forbidden),recovery_fail=forbidden=='RECOVERY_FAILURE')
    output=CheckExecutor(request,bundle,runner,environ=environment,attempt_dir=tmp_path,
        cancellation_requested=lambda:expected=='CANCELLED' and bool(state['target_calls'])).execute()
    if expected=='CANCELLED':
        assert output.result.result_type=='CANCELLED' and output.result.verdict is None
        assert state['pipeline_events']==[('reviewed',True)] and len(state['target_calls'])==1
        from product.backend.infrastructure.artifacts.checks.scenario_progress import read_scenario_journal
        journal=read_scenario_journal(tmp_path/'scenario-execution.json',request,runner)
        assert [item.request for item in journal.nodes]==['RECEIVED','NOT_STARTED']
    else:
        assert output.result.verdict.value==expected,[(item.verdict,item.reason_codes) for item in output.result.case_results]
        assert state['pipeline_events'][:2]==[('reviewed',True),('approved',True)]
        assert len(state['target_calls'])==sum(len(item['invocations']) for item in experiments)
    if forbidden=='RECOVERY_FAILURE':
        assert 'SCENARIO_RECOVERY_UNVERIFIED' in output.result.cleanup_issues and len(state['recovery_calls'])==3
    else:assert state['value']=='original'
    validate_check_decisions(NS(request=request,result=output.result,evidence=output.evidence))


pytestmark=pytest.mark.level4
