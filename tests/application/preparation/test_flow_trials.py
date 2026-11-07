"""普通无源码应用的单次执行、有限反馈、未知副作用及显式恢复。"""
import json
from uuid import uuid4
import pytest
from product.backend.domain.errors import JiejianError
from product.backend.application.preparation.flow_trials import TrialSelection,StartFlowTrial
from tests.support.builders.preparation.external_application import external_application
from tests.support.builders.runtime.managed_records import wait_for

pytestmark=[pytest.mark.level4,pytest.mark.process]


def command(core,project,selection,operation=None):
    preview=core.flow_trials.preview(project,selection)
    return StartFlowTrial(selection=selection,plan_hash=preview['plan_hash'],operation_id=operation or uuid4().hex,confirmed=True)


def test_directory_summary_preserves_adopted_history_without_flow_body(tmp_path):
    with external_application(tmp_path) as app:
        service, project = app.core.operation_flows, app.project_id
        service.adopt(project, app.flow.id, 1)
        service.save(project, app.flow.model_copy(update={'revision': 2}))
        full = service.context(project)
        from product.backend.interfaces.http.envelope import data_response
        from product.backend.interfaces.http.routers.preparation.projections import OperationContextProjection
        assert data_response(full,projection=OperationContextProjection).body == data_response(full).body

        summary = service.context(project, summary=True)
        assert summary['actions'] == full['actions']
        assert summary['flows'] == [dict(
            id=item['document']['id'], revision=item['document']['revision'],
            business_action_id=item['document']['business_action_id'], action_revision=item['document']['action_revision'],
            adopted=item['adopted'], in_use=item['in_use'], configuration_current=item['configuration_current'])
            for item in full['flows']]
        assert next(item for item in summary['flows'] if item['in_use'])['revision'] == 1
        assert {item['revision'] for item in summary['flows']} == {1, 2}
        assert 'recordings' not in summary and 'workflow' not in json.dumps(summary)
        assert len(json.dumps(summary)) < len(json.dumps(full))
        assert service.read(project, app.flow.id, 1) == app.flow


def test_flow_latest_query_does_not_decode_historical_revisions(tmp_path,monkeypatch):
    from product.protocols.preparation.operation_flow import OperationFlow
    with external_application(tmp_path) as app:
        with app.core.uow_factory() as work:
            for revision in range(2,42):
                work.operation_flows.add(app.flow.model_copy(update={'revision':revision}),revision)
            work.commit()
        original=OperationFlow.model_validate_json;accepted=[]
        def decode(raw,**options):
            value=original(raw,**options);accepted.append(value.revision);return value
        monkeypatch.setattr(OperationFlow,'model_validate_json',decode)
        with app.core.uow_factory() as work:
            latest=work.operation_flows.latest(app.project_id)
            assert [item['document'].revision for item in latest]==[41]
            assert accepted==[41]
            assert work.operation_flows.get(app.flow.id,1)==app.flow
            assert work.operation_flows.latest_revision(app.project_id,app.flow.id).revision==41
            assert work.operation_flows.latest_revision('app_'+'f'*32,app.flow.id) is None


def test_trial_is_once_and_observations_do_not_adopt_or_decide_permissions(tmp_path):
    with external_application(tmp_path) as app:
        core,project=app.core,app.project_id
        selection=TrialSelection(flow_id=app.flow.id,revision=1,subject_identity_id=app.identities['member'])
        start=command(core,project,selection)
        assert app.state['target_calls']==0
        receipt=core.flow_trials.start(project,start)
        assert core.flow_trials.start(project,start)==receipt
        core.worker.start()
        result=wait_for(lambda:core.flow_trials.read(project,receipt['request']['trial_id']))
        assert result['state']=='SUCCEEDED',result
        assert result['report']['identity_status']=='MATCH'
        assert result['report']['steps']==[dict(step_id='read',purpose='TARGET',status_code=403,response_bytes=result['report']['steps'][0]['response_bytes'],classification='DENIED',error_code=None)]
        assert app.state['target_calls']==1
        assert core.operation_flows.context(project)['flows'][0]['adopted'] is False
        with core.uow_factory() as work:
            assert work.runs.list_for_project(project)==()
        raw=json.dumps(result)
        assert all(word not in raw for word in ('confidential-order-note','verdict','finding'))
        assert all(token not in raw for token in app.tokens)
        assert core.flow_trials.start(project,start)['request']==receipt['request']
        assert app.state['target_calls']==1
        other=TrialSelection(flow_id=app.flow.id,revision=1)
        with pytest.raises(JiejianError):core.flow_trials.start(project,command(core,project,other,start.operation_id))


def test_failed_recovery_requires_original_restore_without_replaying_target(tmp_path):
    with external_application(tmp_path,changing=True) as app:
        core,project=app.core,app.project_id
        selection=TrialSelection(flow_id=app.flow.id,revision=1)
        first=core.flow_trials.start(project,command(core,project,selection))
        app.state['recovery_failures']=1;core.worker.start()
        first=wait_for(lambda:core.flow_trials.read(project,first['request']['trial_id']))
        assert first['state']=='SUCCEEDED' and first['report']['recovery']=='UNCONFIRMED',first
        assert first['recovery_pending'] and app.state['changed']
        with pytest.raises(JiejianError):core.flow_trials.start(project,command(core,project,selection))
        restore=TrialSelection(flow_id=app.flow.id,revision=1,restore_trial_id=first['request']['trial_id'])
        second=core.flow_trials.start(project,command(core,project,restore))
        second=wait_for(lambda:core.flow_trials.read(project,second['request']['trial_id']))
        assert second['state']=='SUCCEEDED' and second['report']['recovery']=='REQUEST_ACCEPTED',second
        assert second['report']['target_attempted'] is False and not app.state['changed']
        assert app.state['target_calls']==1 and app.state['restore_calls']==2
        assert core.flow_trials.read(project,first['request']['trial_id'])['recovery_pending'] is False
        assert core.flow_trials.read(project,first['request']['trial_id'])['report']==first['report']


def test_cancel_before_claim_never_sends_target_and_stale_preview_is_rejected(tmp_path):
    with external_application(tmp_path) as app:
        core,project=app.core,app.project_id
        selection=TrialSelection(flow_id=app.flow.id,revision=1)
        start=command(core,project,selection)
        first=core.flow_trials.start(project,start)
        catalog = core.agent_capabilities
        operation = dict(capability='flows.trial.start', title='执行已确认的场景试运行', operation_id=start.operation_id,
            arguments=start.model_dump(mode='json'), result=first)
        assert catalog.receipt(project, operation) == first
        assert any(item['label'] == '受检操作' for item in catalog.describe(project, 'flows.trial.start', start))
        catalog.cancel_owned(project, [operation])
        cancelled=core.flow_trials.read(project,first['request']['trial_id'])
        assert cancelled['state']=='CANCELLED' and not cancelled['operation_may_have_run']
        core.worker.start()
        assert app.state['target_calls']==0
        preview=command(core,project,selection)
        account=core.test_identities.get_record(app.identities['owner'])
        core.test_identities.configure_authentication(account.identity_id,account.authentication,expected_updated_at_us=account.updated_at_us)
        assert command(core,project,selection).plan_hash==preview.plan_hash
        core.test_identities.reset(account.identity_id)
        with pytest.raises(JiejianError):core.flow_trials.start(project,preview)
        assert app.state['target_calls']==0


def test_cancelled_inflight_trial_is_not_replayed_after_restart(tmp_path):
    from product.backend.bootstrap.application import ApplicationCore
    from tests.support.builders.runtime.runtime_environment import runtime_identity_environment
    from tests.support.official import until
    with external_application(tmp_path,changing=True) as app:
        core,project=app.core,app.project_id
        selection=TrialSelection(flow_id=app.flow.id,revision=1)
        app.state['delay']=2
        first=core.flow_trials.start(project,command(core,project,selection))
        core.worker.start()
        until(lambda:app.state['target_entered'],bool,seconds=30)
        core.flow_trials.cancel(project,first['request']['trial_id'])
        core.close()
        # 取消本地进程并不撤回服务端已经接收的请求；独立真值先等待它实际结束。
        until(lambda:app.state['target_calls'],lambda count:count==1,seconds=10)
        assert app.state['changed']
        reopened=ApplicationCore(core.var_dir,secret_store=core.secret_store,environ=runtime_identity_environment(core.var_dir))
        try:
            reopened.worker.start()
            original=wait_for(lambda:reopened.flow_trials.read(project,first['request']['trial_id']))
            assert original['state'] in {'CANCELLED','FAILED'} and original['report'] is None
            assert original['recovery_pending']
            assert reopened.flow_trials.requested(project,first['request']['operation_id'])['request']==first['request']
            restore=TrialSelection(flow_id=app.flow.id,revision=1,restore_trial_id=first['request']['trial_id'])
            result=reopened.flow_trials.start(project,command(reopened,project,restore))
            result=wait_for(lambda:reopened.flow_trials.read(project,result['request']['trial_id']))
            assert result['state']=='SUCCEEDED' and result['report']['recovery']=='REQUEST_ACCEPTED',result
            assert app.state['target_calls']==1 and app.state['restore_calls']==1 and not app.state['changed']
        finally:reopened.close()
