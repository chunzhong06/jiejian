# 独立工单应用通过公开API和真实GUI接入；权限由GUI批准，录制来自真实浏览器操作。
import time
import socket
import json
from types import SimpleNamespace
from uuid import uuid4
from pathlib import Path
from playwright.sync_api import expect
from .harness.lifecycle import _wait_for
from .windows import window_snapshot,visible_top_level_windows,Desktop,_invoke_button,_wait_text,belongs_to_login_preparation
from tests.fixtures.runtime.ordinary_workbench import write_workbench,POLICY


def available_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));return sock.getsockname()[1]


def wait_window(before,chromium,preparation_id=None):
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        found=[item for item in visible_top_level_windows() if item.handle not in before and '普通工单工作台' in item.title
            and item.image==Path(chromium).resolve() and (preparation_id is None or belongs_to_login_preparation(item.process_id,preparation_id))]
        assert len(found)<2,'本轮普通应用窗口不唯一'
        if found:return Desktop(backend='uia').window(handle=found[0].handle)
        time.sleep(.15)
    raise AssertionError('未找到本轮受控工单窗口')


def connect_and_approve(client,gui,source):
    write_workbench(source)
    connection=client.call('POST','/api/applications/connect',dict(schema_version='1',source_root=str(source),project_name='普通工单应用'),accepted=(201,))
    project=connection['project']['project_id'];gui.ordinary_project_id=project; base=f'/api/projects/{project}'
    understanding=client.call('PUT',base+'/source-analysis-authorization',dict(schema_version='1',authorized=True,revision=connection['understanding']['revision']))
    understanding=client.call('POST',base+'/source-analysis',dict(schema_version='1',revision=understanding['revision']))
    context=client.call('GET',base+'/proof-preparation')
    assert not context['runtime_available'] and not context['identities'] and not context['resources']
    roles={item['canonical_key']:item['candidate_id'] for item in understanding['role_candidates']}
    action=next(item['candidate_id'] for item in understanding['action_candidates'] if item['canonical_key']=='POST /service/tickets/{ticket}/complete')
    owner,guest,task,effect='pactr_'+'1'*16,'pactr_'+'2'*16,'pactn_'+'1'*16,'peff_'+'1'*16
    proposal=client.call('POST',base+'/business-boundaries/proposals',dict(schema_version='1',
        proposed_actors=[dict(item_id=item,write_mode='CREATE',display_name=label,description=label,effective_state='ACTIVE',source_candidate_ids=[roles[role]])
            for item,label,role in [(owner,'主管','supervisor'),(guest,'协作者','contributor')]],
        proposed_actions=[dict(item_id=task,write_mode='CREATE',display_name='完成工单',description='将工单标为已完成',primary_resource_concept='工单',
            operation_kind='CHANGE',state_changing=True,effective_state='ACTIVE',source_candidate_ids=[action],effect_catalog=[dict(item_id=effect,
                business_label='工单已完成',effect_kind='STATE_MUTATION',resource_concept='工单',expected_state='ready',description='完成状态已提交')])],
        proposed_permissions=[dict(item_id='pperm_'+str(i)*16,write_mode='CREATE',effective_state='ACTIVE',subject_actor_item_id=actor,
            business_action_item_id=task,resource_owner_actor_item_id=owner,relation=relation,expectation=expectation,protected_effect_item_ids=[effect])
            for i,actor,relation,expectation in [(1,owner,'OWNS','ALLOW'),(2,guest,'OTHER_ROLE','DENY')]],
        provenance='根据普通工单代码和业务要求整理的验收提案；尚待界面批准'),accepted=(201,))['proposal']
    gui.page.reload()
    gui.page.get_by_role('button',name='切换应用，当前：尚未选择',exact=True).click()
    gui.page.get_by_role('menuitem',name='普通工单应用',exact=True).click()
    gui.approve(project,SimpleNamespace(**proposal))
    boundary=client.call('GET',base+'/business-boundaries')
    assert len(boundary['permission_intents'])==2
    assert client.call('GET',base+'/proof-preparation')['runtime_available'] is False
    # 先保存五类准备办法；尚无运行实例、真实账号或工单，建议不能把准备状态写成完成。
    action=boundary['actions'][0];owner=next(item for item in boundary['actors'] if item['display_name']=='主管')
    target=dict(kind='APPROVED',action_id=action['action_id'],action_revision=action['revision'],actor_id=owner['actor_id'],actor_revision=owner['revision'],effect_id=action['effect_catalog'][0]['effect_id'])
    kinds=[dict(kind='identity',account_requirement='分别准备主管和协作者的测试登录。'),
        dict(kind='execution',normal_steps=['登录后查看工单，再完成工单。']),
        dict(kind='resource',resource_concept='工单',fields=[dict(field='phase',requirement='起点为queued')],preparation_steps=['由主管通过创建入口建立虚构工单。']),
        dict(kind='evidence',capability='MANAGED_TRANSACTION_RECORDS',observable_result='phase真正提交为ready',field_hints=['phase']),
        dict(kind='recovery',expected_state='工单重新打开，phase恢复为queued')]
    context=client.call('GET',base+'/proof-preparation')
    receipt=client.call('POST',base+'/proof-preparation/suggestions',dict(operation_id=uuid4().hex,expected_basis_id=context['suggestion_context']['basis_id'],
        content=dict(items=[dict(item_id='psi_'+str(i+1)*16,target=target,material=material,description='从工单业务要求整理准备办法。',
            source=dict(classification='HYPOTHESIS',explanation='尚需实际创建和核对测试材料。'),handler='AGENT',gap='尚无实际材料') for i,material in enumerate(kinds)])))
    assert receipt['state']=='CURRENT' and len(receipt['items'])==5
    after=client.call('GET',base+'/proof-preparation')
    assert not after['runtime_available'] and not after['identities'] and not after['resources']
    gui._mark('ordinary-offline-rule-approval')
    gui._mark('ordinary-five-material-suggestions-before-runtime')
    return project,boundary


def start_runtime(client,project,port):
    base=f'/api/projects/{project}';understanding=client.call('GET',base+'/application-understanding')
    preview=client.call('POST',base+'/controlled-runtime/preview',dict(entry='workbench.mjs',port=port,revision=understanding['revision'],consent_source_read=True))
    operation=uuid4().hex
    client.call('POST',base+'/controlled-runtime/start',dict(entry='workbench.mjs',port=port,revision=preview['revision'],
        preview_fingerprint=preview['preview_fingerprint'],operation_id=operation,consent_execute=True),accepted=(202,))
    result=_wait_for(lambda:client.call('GET',base+'/controlled-runtime/operations/'+operation),lambda value:value['state'] in {'SUCCEEDED','FAILED','CANCELLED'},timeout=45,label='普通工单运行')
    assert result['state']=='SUCCEEDED'
    understanding=client.call('GET',base+'/application-understanding')
    client.call('PUT',base+'/endpoint',dict(schema_version='1',revision=understanding['revision'],endpoint=f'http://127.0.0.1:{port}'))
    return result


def login_accounts(client,gui,project,boundary,chromium,*,create=False):
    identities=client.call('GET',f'/api/projects/{project}/test-identities')
    if not identities:
        for actor in boundary['actors']:
            client.call('POST',f'/api/projects/{project}/test-identities',dict(schema_version='1',actor_id=actor['actor_id'],actor_revision=actor['revision'],
                label='lead' if actor['display_name']=='主管' else 'guest'),accepted=(201,))
        identities=client.call('GET',f'/api/projects/{project}/test-identities')
    for identity in identities:
        gui._goto('/tests?materials=1&identities=1')
        row=gui.page.locator('.identity-account-row').filter(has_text=identity['label'])
        if identity['auth_method'] is not None:
            row.get_by_role('button',name='清除登录状态' if identity['status']=='PREPARED' else '清除旧状态',exact=True).click()
            gui._response(f"/api/test-identities/{identity['identity_id']}/reset",lambda:gui.page.get_by_role('dialog').get_by_role('button',name='清除登录状态',exact=True).click())
        before=window_snapshot()
        receipt,_=gui._response(f"/api/test-identities/{identity['identity_id']}/preparations",lambda:row.get_by_role('button',name='打开登录浏览器',exact=True).click())
        window=wait_window(before,chromium,receipt['preparation_id'])
        _invoke_button(window,'主管登录' if identity['label']=='lead' else '协作者登录');_wait_text(window,identity['label'],timeout=15)
        try:
            if create and identity['label']=='lead':
                _invoke_button(window,'查看工单');_wait_text(window,'尚无工单',timeout=15)
                _invoke_button(window,'创建合成工单');_wait_text(window,'合成工单已创建',timeout=15)
        except Exception:
            texts=[item.window_text()[:256] for item in window.descendants(control_type='Text')][:30]
            (gui.audit_dir/'ordinary-business-page-failed.json').write_text(json.dumps({'visible_text':texts},ensure_ascii=False),encoding='utf-8')
            raise
        gui._response(f"/api/identity-preparations/{receipt['preparation_id']}/confirm",lambda:gui.page.get_by_role('button',name='我已完成登录',exact=True).click())
        _wait_for(lambda:client.call('GET',f"/api/test-identities/{identity['identity_id']}"),lambda value:value['status']=='PREPARED',timeout=30,label='保存普通工单登录')
    gui._mark('ordinary-real-login-and-data')
    return identities


def record_action(client,core,gui,project,chromium,*,parent=None):
    from product.backend.workflows.preparation.demonstrations import legal_demonstrations
    from product.protocols.recording.flow_draft import flow_draft_source_choice_id
    action=core.preparation.get(project).actions[0]
    choice=next(item for item in legal_demonstrations(action.assurance_contract,action.permissions,action.identity_requirements) if item.can_execute)
    before=window_snapshot()
    recording=client.call('POST',f'/api/projects/{project}/recordings',dict(schema_version='2',business_action_id=action.action_id,action_revision=action.action_revision,
        subject_test_identity_id=choice.subject_test_identity_id,resource_owner_test_identity_id=choice.resource_owner_test_identity_id,
        subject_slot_id=choice.subject_slot_id,resource_owner_slot_id=choice.resource_owner_slot_id,resource_owner_confirmed=True,duration_seconds=120,
        idempotency_key=uuid4().hex,purpose='RECOVERY' if parent else 'TARGET',parent_recording_id=parent),accepted=(202,))['recording']['recording_id']
    path='/api/recordings/'+recording
    _wait_for(lambda:client.call('GET',path),lambda value:value['capture_phase']=='AWAITING_CAPTURE',timeout=45,label='普通业务录制窗口')
    window=wait_window(before,chromium)
    client.call('POST',path+'/capture/start')
    _wait_for(lambda:client.call('GET',path),lambda value:value['capture_phase']=='CAPTURING',timeout=20,label='开始真实录制')
    _invoke_button(window,'查看工单');_wait_text(window,'工单内容已读取',timeout=15)
    _invoke_button(window,'重新打开工单' if parent else '完成工单');_wait_text(window,'工单已重新打开' if parent else '工单已完成',timeout=15)
    client.call('POST',path+'/capture/stop')
    def ready_to_review(value):
        state=value['recording']['state']
        if state!='PENDING_REVIEW':return state in {'COMPLETED','FAILED','CANCELLED','SAFETY_STOPPED'}
        draft=value['draft']
        # 无歧义草稿会在消费后自动最终化；不能抢在该事务前重复审阅。
        return not draft['target_step_id'] or (not parent and not draft['resource_candidate_id']) or any(item['confirmed_source'] is None for item in draft['variables'])
    result=_wait_for(lambda:client.call('GET',path),ready_to_review,timeout=45,label='读取真实录制草稿')
    assert result['recording']['state'] in {'PENDING_REVIEW','COMPLETED'},(result['recording']['state'],result['recording']['reason_codes'])
    # 正式处理器可自动接受唯一业务解释；不为脚本重复进入已完成录制的审阅。
    if result['recording']['state']=='COMPLETED':
        gui._mark('ordinary-real-recovery-recording' if parent else 'ordinary-real-target-recording')
        return recording
    draft=core.recording_lifecycle.status(recording).draft
    target=next(item for item in draft.steps if item.method=='POST' and item.path.endswith('/reopen' if parent else '/complete'))
    def review(command):return client.call('POST',path+'/review',dict(schema_version='1',command=dict(schema_version='1',**command)))
    for variable in draft.variables:
        if variable.confirmed_source is None:
            review(dict(operation='CONFIRM_VARIABLE_CHOICE',variable_name=variable.name,choice_id=flow_draft_source_choice_id(variable.candidate_sources[0])))
    review(dict(operation='CONFIRM_TARGET_STEP',step_id=target.id))
    if not parent:
        resource=next(item for item in target.resource_candidates if item.consumer=='PATH' and item.location=='path[2]')
        review(dict(operation='CONFIRM_RESOURCE_SLOT',candidate_id=resource.candidate_id))
    client.call('POST',path+'/finalize',dict(schema_version='1'))
    gui._mark('ordinary-real-recovery-recording' if parent else 'ordinary-real-target-recording')
    return recording


def prepare_source(client,gui,project,boundary,identities):
    prefix=f'/api/projects/{project}/proof-preparation';context=client.call('GET',prefix)
    action=boundary['actions'][0];owner=next(item for item in identities if item['label']=='lead')
    resource=next(item for item in context['resources'] if item['action_id']==action['action_id'] and item['owner_identity_id']==owner['identity_id'])
    config=dict(source_kind='MANAGED_TRANSACTION_RECORDS',source_contract_id='TRANSACTION_HISTORY_V2',
        action_id=action['action_id'],action_revision=action['revision'],effect_id=action['effect_catalog'][0]['effect_id'],
        observation_identity_id=owner['identity_id'],resource_binding_id=resource['resource_binding_id'],collection='tickets',
        relative_path_template='/collections/tickets/{resource_id}',mappings={'resource_id':['resource_id'],'owner_id':['owner_id'],'state':['data','phase']},
        identity_claims=[dict(identity_id=item['identity_id'],application_subject_id=item['label'],application_role='supervisor' if item['label']=='lead' else 'contributor',
            request_path='/session/current',subject_path=['id'],role_path=['role']) for item in identities])
    receipt=client.call('POST',prefix+'/sources',dict(operation_id=uuid4().hex,basis_id=context['basis_id'],config=config))
    gui._mark('ordinary-proof-candidate')
    return receipt['result']['source_id']


def verify_source(client,gui,project,source_id):
    prefix=f'/api/projects/{project}/proof-preparation';context=client.call('GET',prefix)
    source=next(item for item in context['sources'] if item['source_id']==source_id)
    gui._goto(f'/tests?materials=1&proof_sources=1&source={source_id}')
    if not source['read_scope_confirmed']:
        gui.page.get_by_role('button',name='确认读取范围',exact=True).click()
        modal=gui.page.get_by_role('dialog',name='确认来源读取范围',exact=True)
        modal.get_by_role('checkbox',name='我已核对以上范围与影响',exact=True).check()
        gui._response(prefix+'/read-scopes',lambda:modal.get_by_role('button',name='允许这些读取',exact=True).click())
    receipt,_=gui._response(prefix+'/preflights',lambda:gui.page.get_by_role('button',name='开始预检查',exact=True).click())
    result=_wait_for(lambda:client.call('GET',prefix+'/preflights/'+receipt['result']['preflight_id']),lambda value:value['state'] in {'SUCCEEDED','FAILED','CANCELLED'},timeout=60,label='普通工单证明预检查')
    assert result['report']['assessment']=='USABLE'
    if not source['adopted']:
        gui.page.get_by_role('button',name='预览采用影响',exact=True).click()
        modal=gui.page.get_by_role('dialog',name='采用这项证明来源',exact=True);modal.get_by_role('checkbox').check()
        gui._response(prefix+'/adoptions',lambda:modal.get_by_role('button',name='确认采用',exact=True).click())
    gui._mark('ordinary-source-verified')


def run_journey(client,gui,core,source,chromium):
    from .current_api import read_result,wait_published,_digest
    from .gui.gallery import evidence
    project,boundary=connect_and_approve(client,gui,source)
    print("普通应用：未运行时的规则批准和五类准备建议已核对",flush=True)
    base=f'/api/projects/{project}';port=available_port()
    start_runtime(client,project,port)
    identities=login_accounts(client,gui,project,boundary,chromium,create=True)
    print("普通应用：实际登录和业务数据已创建",flush=True)
    target=record_action(client,core,gui,project,chromium)
    record_action(client,core,gui,project,chromium,parent=target)
    proof=prepare_source(client,gui,project,boundary,identities)
    print("普通应用：真实动作与恢复录制已完成",flush=True)
    original_recordings=client.call('GET',base+'/recordings');runs=[];reference=None
    for stage,expected in [(0,'PASS'),(1,'BLOCK'),(2,'PASS')]:
        print('普通应用检查轮次：'+str(stage),flush=True)
        change=None
        if stage:
            runtime=client.call('GET',base+'/controlled-runtime')
            client.call('POST',base+'/controlled-runtime/stop',dict(instance_id=runtime['operation']['instance_id']))
            (source/'policy.mjs').write_text("export function mayComplete(actor, owner) { return true; }" if stage==1 else POLICY,encoding='utf-8')
            preview=client.call('GET',base+'/source-changes/registration-preview')
            change=client.call('POST',base+'/source-changes/register',dict(schema_version='1',operation_id=uuid4().hex,
                expected_registration_fingerprint=preview['fingerprint'],reason='修改工单完成权限实现',claimed_paths=['policy.mjs'],repair_reference=reference if stage==2 else None),accepted=(201,))['change_id']
            start_runtime(client,project,port)
            current=client.call('GET',base+'/application-understanding')
            client.call('POST',base+'/source-analysis',dict(schema_version='1',revision=current['revision']))
            identities=login_accounts(client,gui,project,boundary,chromium)
            assert not client.call('GET',base+'/check-preview?change_id='+change)['can_execute']
        verify_source(client,gui,project,proof)
        preview=client.call('GET',base+'/check-preview'+('?change_id='+change if change else ''))
        assert preview['can_execute'] and (preview['action_count'],preview['case_count'])==(1,2)
        submitted=gui.submit(project,dict(expected_plan_fingerprint=preview['plan_fingerprint']),change,require_repair=stage==2)
        wait_published(client,submitted['run']['run_id'],submitted['job']['job_id'])
        result=read_result(client,submitted['run']['run_id']);assert result['story']['verdict']==expected
        if stage==1:
            item=client.call('GET',f"/api/runs/{result['run_id']}/repair-contracts")[0]
            reference={name:item[name] for name in ('source_run_id','source_case_id','repair_fingerprint')}
            evidence(gui,result)
        if stage==2:assert result['story']['repair_verification']['status']=='VERIFIED'
        runs.append(result)
        assert client.call('GET',base+'/recordings')==original_recordings
        for old in runs:assert _digest(read_result(client,old['run_id']))==_digest(old)
        gui.capture('ordinary-stage-'+str(stage));gui._mark('ordinary-stage-'+str(stage))
    gui.history_search(project,runs[1]['run_id']);gui.history_open(runs[1]);gui.history_return(runs[1]['run_id'])
    runtime=client.call('GET',base+'/controlled-runtime')
    client.call('POST',base+'/controlled-runtime/stop',dict(instance_id=runtime['operation']['instance_id']))
    for item in identities:client.call('POST',f"/api/test-identities/{item['identity_id']}/reset",dict(schema_version='1'))
    return {'project_id':project,'runs':[{'run_id':item['run_id'],'verdict':item['story']['verdict']} for item in runs],
        'gui_checkpoints':gui.records,'scope':'真实GUI批准、真实浏览器登录和录制、公开API材料准备、三轮真实CHECK；未调用真实开发Agent'}
