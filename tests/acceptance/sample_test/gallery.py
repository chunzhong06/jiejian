# Node官方故事沿同一GUI、CHECK和历史链验证；不调用旧样例的六来源配方。
from uuid import uuid4
from tests.acceptance.sample_test.harness.state import SampleTestError
from tests.acceptance.sample_test.current_api import read_result,wait_published,project_run_ids,recover_run_for_cleanup,_digest
from tests.acceptance.sample_test.gui import gallery as ui


def assert_result(result,*,expected):
    if result['story']['verdict']!=expected or len(result['evidence'])!=5 or len({item['action_id'] for item in result['story']['actions']})!=3:
        raise SampleTestError('GALLERY_FULL_RESULT_MISMATCH')
    if any(item['schema_version']!='2' for item in result['evidence']):raise SampleTestError('GALLERY_FACT_EVIDENCE_MISSING')
    if any(item['case']['permission']['expectation']=='ALLOW' and item['outcome']['actual_identity_status']!='MATCH' for item in result['evidence']):
        raise SampleTestError('GALLERY_NORMAL_IDENTITY_UNVERIFIED')


def run_sequence(client,gui,project,state,chromium,*,stop_after_setup=False):
    ui.propose(gui,project)
    gui.prepare()
    prepared=client.call('GET',f'/api/projects/{project}/test-identities')
    if len(prepared)!=2 or any(item['status']!='PREPARED' for item in prepared):
        raise SampleTestError('GALLERY_AUTOMATIC_LOGIN_INCOMPLETE')
    identities={str(index):item['identity_id'] for index,item in enumerate(prepared)}
    gui._mark('identity-login')
    # 初次一键准备已经真实登录并创建资料；不再重置账号或重复创建，后续证明继续经界面确认。
    ui.proofs(gui,project)
    if stop_after_setup:return [],identities
    runs=[];reference=None
    for stage,expected in [('BASELINE','PASS'),('VULNERABLE','BLOCK'),('EXPOSE_REVOKE','BLOCK'),('FIXED','PASS'),('PREVIEW_CHANGED','PASS')]:
        print('正式界面场景：'+stage,flush=True)
        change=None
        if stage!='BASELINE':
            switched=gui.switch(stage,reference if stage=='FIXED' else None)
            change=switched['current_change_id']
            if not change:raise SampleTestError('GALLERY_PRESET_CHANGE_MISSING')
            identities=ui.login(gui,project,chromium)
            # 已有录制、资源和参照继续沿用；重载后只重做当前账号与来源核对。
            ui.proofs(gui,project)
        query='' if change is None else '?change_id='+change
        preview=client.call('GET',f'/api/projects/{project}/check-preview'+query)
        if not preview['can_execute'] or (preview['action_count'],preview['case_count'])!=(3,5):raise SampleTestError('GALLERY_FULL_PLAN_UNAVAILABLE')
        body=dict(schema_version='2',expected_plan_fingerprint=preview['plan_fingerprint'],idempotency_key='gallery-'+uuid4().hex,change_id=change)
        before=set(project_run_ids(client,project))
        try:submitted=gui.submit(project,body,change,require_repair=stage=='FIXED')
        except Exception:
            recover_run_for_cleanup(client,project,before,state);raise
        state.active_run_id,state.active_run_job_id=submitted['run']['run_id'],submitted['job']['job_id']
        wait_published(client,state.active_run_id,state.active_run_job_id)
        result=read_result(client,state.active_run_id);assert_result(result,expected=expected)
        state.active_run_id=state.active_run_job_id=None
        if stage=='VULNERABLE':
            contracts=client.call('GET',f"/api/runs/{result['run_id']}/repair-contracts")
            # 精确原题字段与普通修复入口共用，不按最新检查猜测来源。
            item=contracts[0];reference={key:item[key] for key in ('source_run_id','source_case_id','repair_fingerprint')}
        if stage=='EXPOSE_REVOKE':
            document=next(item for item in result['evidence'] if item['case']['permission']['expectation']=='DENY')
            commits={fact['data']['operation_id'] for fact in document['business_facts'] if fact['data']['kind']=='COMMITTED_STATE'}
            if document['outcome']['http_status']!=403 or len(commits)!=2:raise SampleTestError('GALLERY_REVOKE_HISTORY_MISSING')
            ui.evidence(gui,result)
        if stage=='FIXED' and (result['story'].get('repair_verification') or {}).get('status')!='VERIFIED':raise SampleTestError('GALLERY_ORIGINAL_REPAIR_UNVERIFIED')
        gui._goto('/tests?run_id='+result['run_id']);gui.page.get_by_role('heading',name='原题复验通过' if stage=='FIXED' else result['story']['judgement'],level=1,exact=True).wait_for()
        gui.capture('gallery-'+stage.lower().replace('_','-'));gui._mark('gallery-'+stage.lower())
        runs.append(result)
        for previous in runs:
            if _digest(read_result(client,previous['run_id']))!=_digest(previous):raise SampleTestError('GALLERY_HISTORY_CHANGED')
    gui.history_search(project,runs[1]['run_id']);gui.history_open(runs[1]);gui.history_return(runs[1]['run_id'])
    return runs,identities


def resume_last_stage(client,gui,chromium):
    """接续已安全停止的四轮官方GUI检查，只运行剩余预览修改；MCP复用已有真实SDK证据。"""
    from .harness.state import HarnessState
    from .harness.lifecycle import _wait_for
    status=client.call('GET','/api/experience/official-sample')
    project=status['project_id'];gui.ordinary_project_id=project
    assert not status['active'] and status['scenario_version']=='PREVIEW_CHANGED'
    prefix=f'/api/projects/{project}'
    history=client.call('GET',prefix+'/check-history')['items']
    all_runs=sorted((item['status']['run'] for item in history),key=lambda item:item['created_at_us'])
    assert all(item['lifecycle'] in {'COMPLETED','CANCELLED'} for item in all_runs)
    saved=[item for item in all_runs if item['lifecycle']=='COMPLETED']
    cancelled=[item['run_id'] for item in all_runs if item['lifecycle']=='CANCELLED']
    assert [item['verdict'] for item in saved]==['PASS','BLOCK','BLOCK','PASS']
    runs=[read_result(client,item['run_id']) for item in saved]
    assert runs[-1]['story']['repair_verification']['status']=='VERIFIED'
    state=HarnessState()
    try:
        runtime=client.call('GET',prefix+'/controlled-runtime');configuration=runtime['configuration']
        current=client.call('GET',prefix+'/application-understanding')
        preview=client.call('POST',prefix+'/controlled-runtime/preview',dict(entry=configuration['entry'],port=configuration['port'],revision=current['revision'],consent_source_read=True))
        operation=uuid4().hex
        client.call('POST',prefix+'/controlled-runtime/start',dict(entry=preview['entry'],port=preview['port'],revision=preview['revision'],preview_fingerprint=preview['preview_fingerprint'],operation_id=operation,consent_execute=True),accepted=(202,))
        loaded=_wait_for(lambda:client.call('GET',prefix+'/controlled-runtime/operations/'+operation),lambda item:item['state'] in {'SUCCEEDED','FAILED','CANCELLED'},timeout=45,label='恢复同一批预览修改')
        assert loaded['state']=='SUCCEEDED'
        gui.page.reload()
        gui.page.get_by_role('button',name='切换应用，当前：尚未选择',exact=True).click()
        gui.page.get_by_role('menuitem',name=status['display_name'],exact=True).click()
        ui.login(gui,project,chromium);ui.proofs(gui,project)
        status=client.call('GET','/api/experience/official-sample');change=status['current_change_id'];assert change
        preview=client.call('GET',prefix+'/check-preview?change_id='+change)
        assert preview['can_execute'] and (preview['action_count'],preview['case_count'])==(3,5)
        before=set(project_run_ids(client,project))
        try:submitted=gui.submit(project,dict(expected_plan_fingerprint=preview['plan_fingerprint']),change)
        except Exception:
            recover_run_for_cleanup(client,project,before,state)
            raise
        state.active_run_id,state.active_run_job_id=submitted['run']['run_id'],submitted['job']['job_id']
        wait_published(client,state.active_run_id,state.active_run_job_id)
        result=read_result(client,state.active_run_id);assert_result(result,expected='PASS')
        state.active_run_id=state.active_run_job_id=None
        runs.append(result);gui.capture('gallery-preview-changed');gui._mark('gallery-preview_changed')
        for old in runs:assert _digest(read_result(client,old['run_id']))==_digest(old)
        gui.history_search(project,runs[1]['run_id']);gui.history_open(runs[1]);gui.history_return(runs[1]['run_id'])
        print('官方剩余预览修改及历史核对通过',flush=True)
        return {'project_id':project,'reused_run_ids':[item['run_id'] for item in runs[:4]],
            'runs':[{'run_id':item['run_id'],'verdict':item['story']['verdict']} for item in runs],
            'retained_cancelled_run_ids':cancelled,'mcp_reused_evidence':'pytest-6be475c112cc438ca03bebf25604fe03.json',
            'gui_checkpoints':gui.records,'scope':'四轮已有GUI证据与本次最后一轮分段验收；MCP复用真实SDK证据，不宣称单轮完整sample-test通过'}
    finally:
        if state.active_run_job_id:
            observed=client.call('GET',f'/api/runs/{state.active_run_id}')
            if observed['run']['lifecycle'] in {'QUEUED','RUNNING'}:
                client.call('POST',f'/api/jobs/{state.active_run_job_id}/cancel')
                _wait_for(lambda:client.call('GET',f'/api/runs/{state.active_run_id}'),lambda item:item['run']['lifecycle'] not in {'QUEUED','RUNNING'},timeout=30,label='回收本轮检查')
            state.active_run_id=state.active_run_job_id=None
        client.call('POST','/api/experience/official-sample/stop')
