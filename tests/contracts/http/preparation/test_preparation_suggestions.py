# 验证五类材料建议从未运行应用开始，保持真实准备事实不变，并按精确批准映射续接。
from copy import deepcopy
from uuid import uuid4

import pytest
from tests.support.builders.control_plane import TestClient, create_app
from tests.support.builders.boundary_candidates import _project, _save, _content, confirm_scope


def _items(target):
    kinds = [
        {'kind':'identity','account_requirement':'准备负责人测试账号。'},
        {'kind':'execution','normal_steps':['登录后打开项目，再发布资料。']},
        {'kind':'resource','resource_concept':'项目资料','fields':[{'field':'state','requirement':'初始状态为草稿'}],
            'preparation_steps':['通过应用的正常创建入口建立合成测试资料。']},
        {'kind':'evidence','capability':'MANAGED_TRANSACTION_RECORDS','observable_result':'资料状态真正变为已发布','field_hints':['state']},
        {'kind':'recovery','expected_state':'资料恢复为草稿'}]
    return [{'item_id':'psi_'+str(index+1)*16,'target':target,'material':material,'description':'从当前业务要求整理准备办法。',
        'source':{'classification':'HYPOTHESIS','explanation':'实现和材料仍需核对。'},'handler':'AGENT','gap':'尚无实际材料',
        'depends_on':[] if index==0 else ['psi_'+'1'*16]} for index,material in enumerate(kinds)]


def _candidate_target(saved):
    candidate=saved['candidate']
    return {'kind':'CANDIDATE','candidate_id':candidate['candidate_id'],'revision':candidate['revision'],
        'action_item_id':'pactn_'+'1'*16,'actor_item_id':'pactr_'+'1'*16,'effect_item_id':'peff_'+'1'*16}


def _approve(client,prefix,saved):
    saved=confirm_scope(client,prefix,saved)
    candidate=saved['candidate']
    response=client.post(f"{prefix}/rule-candidates/{candidate['candidate_id']}/proposals",json={'revision':candidate['revision'],'operation_id':uuid4().hex})
    assert response.status_code==201,response.text
    proposal_id=response.json()['data']['proposal_id']
    proposal=client.get(f'{prefix}/proposals/{proposal_id}').json()['data']['proposal']
    result=client.post(f'{prefix}/proposals/{proposal_id}/approve',json={'schema_version':'1',
        'expected_fingerprint':proposal['proposal_fingerprint'],'reason':'核对非文件业务要求'})
    assert result.status_code==200,result.text
    return result.json()['data']


def _suggest(client,path,items,**extra):
    context=client.get(path)
    assert context.status_code==200,context.text
    command={'operation_id':uuid4().hex,'expected_basis_id':context.json()['data']['suggestion_context']['basis_id'],
        'content':{'items':items},**extra}
    response=client.post(path+'/suggestions',json=command)
    assert response.status_code==200,response.text
    return command,response.json()['data']


def test_code_only_five_materials_survive_restart_and_do_not_create_real_materials(tmp_path):
    var=tmp_path/'var'
    with TestClient(create_app(var,start_worker=False,environ={})) as client:
        project=_project(client,tmp_path/'source');prefix=f'/api/projects/{project}/business-boundaries'
        _,candidate=_save(client,prefix);path=f'/api/projects/{project}/proof-preparation'
        before=client.get(f'/api/projects/{project}/preparation').json()['data']
        command,saved=_suggest(client,path,_items(_candidate_target(candidate)))
        assert saved['state']=='CURRENT'
        assert {item['resolved_target']['state'] for item in saved['items']}=={'WAITING_APPROVAL'}
        assert client.get(f'/api/projects/{project}/preparation').json()['data']==before
        assert client.get(prefix).json()['data']['policy_epoch']==0
        assert client.post(path+'/suggestions',json=command).json()['data']==saved
        other=deepcopy(command);other['content']['items'][0]['description']='同键异文'
        assert client.post(path+'/suggestions',json=other).status_code==409
        assert client.get(path+'/suggestion-receipts/'+command['operation_id']).json()['data']['status']=='FOUND'
        approved=_approve(client,prefix,candidate)
        suggestion=saved['suggestion']
        current=client.get(f"{path}/suggestions/{suggestion['suggestion_id']}?revision=1").json()['data']
        assert current['state']=='CURRENT'
        assert all(item['resolved_target']['state']=='APPROVED' for item in current['items'])
        assert {item['resolved_target']['action_id'] for item in current['items']}=={approved['actions'][0]['action_id']}
        assert {item['resolved_target']['effect_id'] for item in current['items']}=={approved['actions'][0]['effect_catalog'][0]['effect_id']}
    with TestClient(create_app(var,start_worker=False,environ={})) as client:
        restored=client.get(f"{path}/suggestions/{suggestion['suggestion_id']}?revision=1").json()['data']
        assert restored['suggestion']==suggestion
        assert len(restored['items'])==5
        _,updated=_suggest(client,path,_items(_candidate_target(candidate)),suggestion_id=suggestion['suggestion_id'],expected_revision=1)
        assert updated['suggestion']['revision']==2 and updated['state']=='CURRENT'
        assert client.get(f'/api/projects/{project}/preparation').json()['data']['preparation_complete'] is False


@pytest.mark.parametrize('fault',['cycle','arbitrary_command','secret','wrong_role','missing_candidate','unregistered_capability','item_budget','question_budget','root_budget'])
def test_suggestions_reject_unbounded_unsafe_or_wrong_references(tmp_path,fault):
    with TestClient(create_app(tmp_path/'var',start_worker=False,environ={})) as client:
        project=_project(client,tmp_path/'source');prefix=f'/api/projects/{project}/business-boundaries'
        _,candidate=_save(client,prefix);path=f'/api/projects/{project}/proof-preparation';items=_items(_candidate_target(candidate))
        if fault=='cycle':items[0]['depends_on']=[items[1]['item_id']]
        elif fault=='arbitrary_command':items[1]['material']['command']='run-unbounded-code'
        elif fault=='secret':items[0]['description']='password=never-persist-me'
        elif fault=='wrong_role':items[0]['target']={**items[0]['target'],'actor_item_id':'pactr_'+'9'*16}
        elif fault=='missing_candidate':items[0]['source']={'classification':'SOURCE_CANDIDATE','candidate_ids':['action_'+'9'*32],'explanation':'假称已核验'}
        elif fault=='unregistered_capability':items[3]['material']['capability']='UNREGISTERED_PROOF'
        elif fault in {'item_budget','root_budget'}:
            items=[{**deepcopy(items[1]),'item_id':f'psi_{index:016x}','depends_on':[],
                'material':{'kind':'execution','normal_steps':['材'*512]*10}} for index in range(51 if fault=='item_budget' else 50)]
        basis=client.get(path).json()['data']['suggestion_context']['basis_id']
        content={'items':items}
        if fault=='question_budget':content['unresolved_questions']=['待核对']*11
        response=client.post(path+'/suggestions',json={'operation_id':uuid4().hex,'expected_basis_id':basis,'content':content})
        assert response.status_code>=400,response.text
        assert 'never-persist-me' not in response.text
        assert client.get(path).json()['data']['suggestion_context']['latest'] is None


def test_old_revision_cross_project_and_source_change_cannot_overwrite_current_advice(tmp_path):
    app=create_app(tmp_path/'var',start_worker=False,environ={})
    with TestClient(app) as client:
        project=_project(client,tmp_path/'source');other=_project(client,tmp_path/'other')
        source=tmp_path/'source'/'logic.py';source.write_text('def publish(item):\n    return item\n',encoding='utf-8')
        core=app.state.context;initial=core.application_understanding.get(project)
        authorized=core.application_understanding.authorize_source_analysis(project,revision=initial.revision)
        core.application_understanding.scan_source(project,revision=authorized.revision)
        prefix=f'/api/projects/{project}/business-boundaries';_,candidate=_save(client,prefix)
        path=f'/api/projects/{project}/proof-preparation';command,first=_suggest(client,path,_items(_candidate_target(candidate)))
        suggestion_id=first['suggestion']['suggestion_id']
        _,second=_suggest(client,path,_items(_candidate_target(candidate)),suggestion_id=suggestion_id,expected_revision=1)
        old=client.get(path+'/suggestions/'+suggestion_id+'?revision=1').json()['data']
        assert old['state']=='SUPERSEDED' and old['latest_revision']==2
        assert not any(item['current'] for item in old['items'])
        assert client.get(path+'/suggestions/'+suggestion_id+'?revision=0').status_code==400
        stale={**command,'operation_id':uuid4().hex,'suggestion_id':suggestion_id,'expected_revision':1}
        assert client.post(path+'/suggestions',json=stale).status_code==409
        assert client.get(path.replace(project,other)+'/suggestions/'+suggestion_id).status_code==404
        source.write_text('def publish(item):\n    return {"changed": item}\n',encoding='utf-8')
        changed=client.get(path+'/suggestions/'+suggestion_id).json()['data']
        assert changed['state']=='STALE'
        stale['expected_revision']=second['suggestion']['revision']
        assert client.post(path+'/suggestions',json=stale).status_code==409


def test_receipt_failure_rolls_back_suggestion_and_guidance_failure_does_not_hide_materials(tmp_path,monkeypatch):
    from product.backend.infrastructure.storage.preparation.suggestions import PreparationSuggestionRepository
    from product.backend.domain.errors import ErrorCode, JiejianError
    app=create_app(tmp_path/'var',start_worker=False,environ={})
    with TestClient(app) as client:
        project=_project(client,tmp_path/'source');prefix=f'/api/projects/{project}/business-boundaries'
        _,candidate=_save(client,prefix);path=f'/api/projects/{project}/proof-preparation'
        basis=client.get(path).json()['data']['suggestion_context']['basis_id']
        command={'operation_id':uuid4().hex,'expected_basis_id':basis,'content':{'items':_items(_candidate_target(candidate))}}
        def failed_receipt(*args,**kwargs):
            raise JiejianError(ErrorCode.STORAGE_STATE,'测试回执失败')
        with monkeypatch.context() as patch:
            patch.setattr(PreparationSuggestionRepository,'add_receipt',failed_receipt)
            assert client.post(path+'/suggestions',json=command).status_code>=400
        assert client.get(path).json()['data']['suggestion_context']['latest'] is None
        assert client.get(path+'/suggestion-receipts/'+command['operation_id']).json()['data']['status']=='UNKNOWN'
        with monkeypatch.context() as patch:
            patch.setattr(app.state.context.preparation_suggestions,'context',failed_receipt)
            value=client.get(path).json()['data']
            assert value['suggestion_context']['state']=='UNAVAILABLE'
            assert value['guidance']['state']=='CURRENT'
            assert value['actions']==[]


@pytest.mark.parametrize('meaning_changed', [False, True])
def test_unapproved_advice_reuses_unchanged_meaning_and_rejects_changed_permission(tmp_path, meaning_changed):
    with TestClient(create_app(tmp_path/'var',start_worker=False,environ={})) as client:
        project=_project(client,tmp_path/'source');prefix=f'/api/projects/{project}/business-boundaries'
        _,candidate=_save(client,prefix);path=f'/api/projects/{project}/proof-preparation'
        items=_items(_candidate_target(candidate));_,saved=_suggest(client,path,items)
        content=_content()
        if meaning_changed:
            content['actions'][0]['description']='发布到全部项目而非当前项目'
        _save(client,prefix,content,candidate_id=candidate['candidate']['candidate_id'],expected_revision=1)
        old=client.get(path+'/suggestions/'+saved['suggestion']['suggestion_id']).json()['data']
        assert old['state']==('STALE' if meaning_changed else 'CURRENT')
        assert all(item['resolved_target']['state']==('STALE' if meaning_changed else 'WAITING_APPROVAL') for item in old['items'])
        basis=client.get(path).json()['data']['suggestion_context']['basis_id']
        rejected=client.post(path+'/suggestions',json={'operation_id':uuid4().hex,'expected_basis_id':basis,'content':{'items':items}})
        assert rejected.status_code==(409 if meaning_changed else 200)

pytestmark = [pytest.mark.level3]
