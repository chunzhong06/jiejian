# 验证人的含义选择不可由Agent继承、抹去或越过正式批准，且精确来源跨重启保留。
from copy import deepcopy
from uuid import uuid4

import pytest

from tests.support.builders.control_plane import TestClient, create_app
from tests.support.builders.boundary_candidates import _content, _project, _save, scenario_content, decide, propose, confirm_scope


def test_choice_proposal_and_formal_rule_keep_exact_provenance(tmp_path):
    var = tmp_path/'var'
    with TestClient(create_app(var, start_worker=False, environ={})) as client:
        project = _project(client, tmp_path/'source'); prefix = f'/api/projects/{project}/business-boundaries'
        _, first = _save(client, prefix, scenario_content())
        assert first['candidate']['schema_version'] == '6'
        assert first['assessment'] == 'NEEDS_CHANGES'
        assert propose(client, prefix, first).status_code == 409
        command, selected = decide(client, prefix, first)
        assert selected['candidate']['revision'] == 2
        assert selected['assessment'] == 'NEEDS_CHANGES'
        assert any(item['code']=='SCOPE_DECISION_REQUIRED' for item in selected['issues'])
        assert client.get(prefix).json()['data']['policy_epoch'] == 0
        url = f"{prefix}/rule-candidates/{first['candidate']['candidate_id']}/decisions"
        assert client.post(url, json=command).json()['data'] == selected
        assert client.post(url, json={**command, 'option_id': 'rop_1111111111111111'}).status_code == 409
        assert client.get(f"{prefix}/rule-operations/DECIDE/{command['operation_id']}").json()['data']['status'] == 'FOUND'
        selected = confirm_scope(client, prefix, selected)
        created = propose(client, prefix, selected)
        assert created.status_code == 201, created.text
        proposal_id = created.json()['data']['proposal_id']
        proposal = client.get(f'{prefix}/proposals/{proposal_id}').json()['data']['proposal']
        response = client.post(f'{prefix}/proposals/{proposal_id}/approve', json={'schema_version':'1',
            'expected_fingerprint': proposal['proposal_fingerprint'], 'reason':'核对选择及完整规则'})
        assert response.status_code == 200, response.text
        approved_rules = response.json()['data']['permission_intents']
    with TestClient(create_app(var, start_worker=False, environ={})) as client:
        view = client.get(f"{prefix}/rule-candidates/{first['candidate']['candidate_id']}?revision={selected['candidate']['revision']}").json()['data']
        mapping = next(item for item in view['approval_mappings'] if item['permission_item_id']=='pperm_2222222222222222')
        assert mapping['scenario_decision_ids'] == [selected['scenario_decisions'][0]['decision']['decision_id']]
        assert any((item['intent_id'],item['revision'],item['intent_hash']) == (mapping['intent_id'],mapping['revision'],mapping['intent_hash']) for item in approved_rules)
        assert view['scenario_decisions'][0]['decision']['submitted_via'] == 'LOCAL_GUI'


@pytest.mark.parametrize('action', ['CORRECT','DEFER'])
def test_unresolved_decision_cannot_be_removed_or_proposed(tmp_path, action):
    with TestClient(create_app(tmp_path/'var', start_worker=False, environ={})) as client:
        project = _project(client,tmp_path/'source'); prefix=f'/api/projects/{project}/business-boundaries'
        content=scenario_content(); _, first=_save(client,prefix,content)
        content['requirement_sources']=first['candidate']['content']['requirement_sources']
        _, pending=decide(client,prefix,first,action=action,**({'correction':'仅公开展示允许发布'} if action=='CORRECT' else {}))
        assert propose(client,prefix,pending).status_code == 409
        content['scenarios']=[]
        command={'operation_id':uuid4().hex,'expected_basis_id':first['candidate']['basis_id'],
            'candidate_id':first['candidate']['candidate_id'],'expected_revision':2,'content':content}
        assert client.post(prefix+'/rule-candidates',json=command).status_code == 409
        _, dismissed=decide(client,prefix,pending,action='DISMISS',correction='本应用没有评审发布入口，这处歧义不适用')
        assert dismissed['scenario_decisions'][0]['status']=='DISMISS'
        assert client.post(prefix+'/rule-candidates',json={**command,'operation_id':uuid4().hex,'expected_revision':3}).status_code==201


def test_changed_meaning_and_new_candidate_do_not_inherit_agreement(tmp_path):
    with TestClient(create_app(tmp_path/'var',start_worker=False,environ={})) as client:
        project=_project(client,tmp_path/'source'); prefix=f'/api/projects/{project}/business-boundaries'
        content=scenario_content(); _,first=_save(client,prefix,content); _,selected=decide(client,prefix,first)
        content['scenarios'][0]['options'][1]['explanation']='只对内部资料限制发布。'
        _,changed=_save(client,prefix,content,candidate_id=first['candidate']['candidate_id'],expected_revision=selected['candidate']['revision'])
        assert changed['scenario_decisions'][0]['status']=='NEEDS_DECISION'
        assert propose(client,prefix,changed).status_code==409
        _,other=_save(client,prefix,scenario_content())
        assert other['scenario_decisions'][0]['decision'] is None
        _,same=decide(client,prefix,changed)
        same=confirm_scope(client,prefix,same)
        assert same['assessment']=='REVIEWABLE'


def test_approve_cannot_use_old_candidate_head(tmp_path):
    with TestClient(create_app(tmp_path/'var',start_worker=False,environ={})) as client:
        project=_project(client,tmp_path/'source'); prefix=f'/api/projects/{project}/business-boundaries'
        content=scenario_content(); _,first=_save(client,prefix,content); _,selected=decide(client,prefix,first)
        selected=confirm_scope(client,prefix,selected)
        proposed=propose(client,prefix,selected).json()['data']
        proposal=client.get(f"{prefix}/proposals/{proposed['proposal_id']}").json()['data']['proposal']
        _save(client,prefix,content,candidate_id=first['candidate']['candidate_id'],expected_revision=selected['candidate']['revision'])
        response=client.post(f"{prefix}/proposals/{proposal['proposal_id']}/approve",json={'schema_version':'1',
            'expected_fingerprint':proposal['proposal_fingerprint'],'reason':'旧窗口批准'})
        assert response.status_code==409
        assert client.get(prefix).json()['data']['policy_epoch']==0


def test_conflicting_choices_do_not_use_the_last_click(tmp_path):
    with TestClient(create_app(tmp_path/'var',start_worker=False,environ={})) as client:
        project=_project(client,tmp_path/'source'); prefix=f'/api/projects/{project}/business-boundaries'
        content=scenario_content(); second=deepcopy(content['scenarios'][0]); second['scenario_id']='rsc_2222222222222222'
        second['question']='另一处情境是否也适用？'; content['scenarios'].append(second)
        _,first=_save(client,prefix,content); _,one=decide(client,prefix,first,option='rop_1111111111111111')
        _,two=decide(client,prefix,one,scenario_index=1)
        assert any(item['code']=='CHOICES_CONFLICT' for item in two['issues'])
        assert propose(client,prefix,two).status_code==409
        _,fixed=decide(client,prefix,two,option='rop_1111111111111111',scenario_index=1)
        fixed=confirm_scope(client,prefix,fixed)
        assert fixed['assessment']=='REVIEWABLE'


def test_decision_rejects_stale_cross_project_and_forged_source(tmp_path):
    with TestClient(create_app(tmp_path/'var',start_worker=False,environ={})) as client:
        project=_project(client,tmp_path/'source'); other=_project(client,tmp_path/'other')
        prefix=f'/api/projects/{project}/business-boundaries'; _,first=_save(client,prefix,scenario_content())
        command,_=decide(client,prefix,first); url=f"{prefix}/rule-candidates/{first['candidate']['candidate_id']}/decisions"
        assert client.post(url,json={**command,'operation_id':uuid4().hex}).status_code==409
        other_basis=client.get(prefix.replace(project,other)+'/rule-context').json()['data']['basis_id']
        assert client.post(url.replace(project,other),json={**command,'operation_id':uuid4().hex,'expected_basis_id':other_basis}).status_code==404
        assert client.post(url,json={**command,'submitted_via':'LOCAL_GUI'}).status_code==422


def test_preview_is_read_only_and_distinguishes_rule_sources(tmp_path):
    import sqlite3
    from product.backend.infrastructure.runtime.paths import RuntimePaths
    var=tmp_path/'var'
    with TestClient(create_app(var,start_worker=False,environ={})) as client:
        project=_project(client,tmp_path/'source');prefix=f'/api/projects/{project}/business-boundaries'
        _,first=_save(client,prefix,scenario_content())
        reference={'kind':'CANDIDATE','candidate_id':first['candidate']['candidate_id'],'revision':1}
        assert client.post(prefix+'/rule-preview',json={'reference':reference}).json()['data']['availability']=='NEEDS_DECISION'
        _,selected=decide(client,prefix,first)
        selected=confirm_scope(client,prefix,selected)
        proposed=propose(client,prefix,selected).json()['data']
        situation={'subject_id':'pactr_2222222222222222','owner_id':'pactr_1111111111111111','relation':'OTHER_ROLE',
            'action_id':'pactn_1111111111111111','effect_id':'peff_1111111111111111'}
        def snapshot():
            with sqlite3.connect(RuntimePaths(var).database) as connection:return tuple(connection.iterdump())
        before=snapshot()
        for source in ({**reference,'revision':selected['candidate']['revision']},{'kind':'PROPOSAL','proposal_id':proposed['proposal_id']}):
            response=client.post(prefix+'/rule-preview',json={'reference':source,'situation':situation})
            assert response.status_code==200,response.text
            assert response.json()['data']['coverage']=='DENY'
            uncovered={**situation,'subject_id':'pactr_1111111111111111','relation':'SAME_ROLE_OTHER_ACCOUNT'}
            assert client.post(prefix+'/rule-preview',json={'reference':source,'situation':uncovered}).json()['data']['coverage']=='UNCOVERED'
        assert snapshot()==before
        proposal=client.get(f"{prefix}/proposals/{proposed['proposal_id']}").json()['data']['proposal']
        approved=client.post(f"{prefix}/proposals/{proposal['proposal_id']}/approve",json={'schema_version':'1',
            'expected_fingerprint':proposal['proposal_fingerprint'],'reason':'保存精确规则'}).json()['data']
        rule=next(item for item in approved['permission_intents'] if item['expectation']=='DENY')
        source={'kind':'APPROVED','rules':[{'intent_id':rule['intent_id'],'revision':rule['revision']}]}
        situation={'subject_id':rule['subject_actor_id'],'owner_id':rule['resource_owner_actor_id'],'relation':rule['relation'],
            'action_id':rule['business_action_id'],'effect_id':rule['protected_effect_ids'][0]}
        response=client.post(prefix+'/rule-preview',json={'reference':source,'situation':situation})
        assert response.status_code==200,response.text
        assert response.json()['data']['coverage']=='DENY'
        assert response.json()['data']['matches'][0]['intent_hash']==rule['intent_hash']
        stale=client.post(prefix+'/rule-preview',json={'reference':{**reference,'revision':2}}).json()['data']
        assert stale['availability']=='STALE' and stale['coverage'] is None


def test_failed_decision_receipt_rolls_back_candidate_and_choice(tmp_path,monkeypatch):
    from product.backend.infrastructure.storage.boundaries.rule_candidates import RuleCandidateRepository
    from product.backend.domain.errors import JiejianError, ErrorCode
    with TestClient(create_app(tmp_path/'var',start_worker=False,environ={})) as client:
        project=_project(client,tmp_path/'source');prefix=f'/api/projects/{project}/business-boundaries'
        _,first=_save(client,prefix,scenario_content());candidate=first['candidate'];scenario=candidate['content']['scenarios'][0]
        original=RuleCandidateRepository.add_receipt
        def fail(self,project_id,kind,*args,**kwargs):
            if kind=='DECIDE':raise JiejianError(ErrorCode.STORAGE_STATE,'injected receipt failure')
            return original(self,project_id,kind,*args,**kwargs)
        monkeypatch.setattr(RuleCandidateRepository,'add_receipt',fail)
        operation=uuid4().hex
        response=client.post(f"{prefix}/rule-candidates/{candidate['candidate_id']}/decisions",json={
            'operation_id':operation,'expected_basis_id':candidate['basis_id'],'expected_revision':1,
            'scenario_id':scenario['scenario_id'],'scenario_fingerprint':scenario['scenario_fingerprint'],
            'action':'SELECT','option_id':scenario['options'][0]['option_id']})
        assert response.status_code>=400
        current=client.get(f"{prefix}/rule-candidates/{candidate['candidate_id']}").json()['data']
        assert current['candidate']['revision']==1
        assert current['scenario_decisions'][0]['decision'] is None
        assert client.get(f'{prefix}/rule-operations/DECIDE/{operation}').json()['data']['status']=='UNKNOWN'


def test_old_question_must_enter_human_review_before_removal(tmp_path):
    with TestClient(create_app(tmp_path/'var',start_worker=False,environ={})) as client:
        project=_project(client,tmp_path/'source');prefix=f'/api/projects/{project}/business-boundaries'
        content=scenario_content();question=content['scenarios'][0]['question'];content['unresolved_questions']=[question]
        scenario=content.pop('scenarios');_,first=_save(client,prefix,content)
        content['unresolved_questions']=[]
        command={'operation_id':uuid4().hex,'candidate_id':first['candidate']['candidate_id'],'expected_revision':1,
            'expected_basis_id':first['candidate']['basis_id'],'content':content}
        assert client.post(prefix+'/rule-candidates',json=command).status_code==409
        content['scenarios']=scenario
        _,updated=_save(client,prefix,content,candidate_id=first['candidate']['candidate_id'],expected_revision=1)
        assert updated['assessment']=='NEEDS_CHANGES'
        _,selected=decide(client,prefix,updated)
        selected=confirm_scope(client,prefix,selected)
        assert selected['assessment']=='REVIEWABLE'


@pytest.mark.parametrize('conversion', ['none', 'partial', 'paraphrased'])
def test_revision_reports_every_unmapped_question_without_losing_original_requirements(tmp_path, conversion):
    with TestClient(create_app(tmp_path/'var',start_worker=False,environ={})) as client:
        project=_project(client,tmp_path/'source');prefix=f'/api/projects/{project}/business-boundaries'
        content=scenario_content(); first_scene=content.pop('scenarios')[0]
        second_scene={**deepcopy(first_scene),'scenario_id':'rsc_2222222222222222','question':'评审能否发布负责人的公开资料？'}
        content['unresolved_questions']=[first_scene['question'],second_scene['question']]
        content['unsupported_constraints']=['跨检查窗口的历史记录尚未确认']
        _,first=_save(client,prefix,content)
        incoming=deepcopy(content);incoming['unresolved_questions']=[]
        incoming['scenarios']=[] if conversion=='none' else [deepcopy(first_scene)]
        if conversion=='paraphrased':
            incoming['scenarios'][0]['question']='是否允许评审发布负责人的资料？'
        operation=uuid4().hex
        command={'operation_id':operation,'candidate_id':first['candidate']['candidate_id'],'expected_revision':1,
            'expected_basis_id':first['candidate']['basis_id'],'content':incoming}
        rejected=client.post(prefix+'/rule-candidates',json=command)
        assert rejected.status_code==409
        details=rejected.json()['error']['details']
        assert details['reason']=='CANDIDATE_QUESTION_REVIEW_REQUIRED'
        assert [item['question_number'] for item in details['issues']]==([2] if conversion=='partial' else [1,2])
        assert details['revision']==1 and details['candidate_id']==first['candidate']['candidate_id']
        assert details['review_url']==first['review_url']
        assert '保存成功后' in details['recovery']
        latest=client.get(f"{prefix}/rule-candidates/{first['candidate']['candidate_id']}").json()['data']
        assert latest['candidate']==first['candidate']
        assert client.get(f'{prefix}/rule-operations/SAVE/{operation}').json()['data']['status']=='UNKNOWN'

        # 完整迁移先保存待人核对的rev2；原文、禁止结果和真实能力限制均不因转换消失。
        incoming['scenarios']=[first_scene,second_scene]
        _,updated=_save(client,prefix,incoming,candidate_id=first['candidate']['candidate_id'],expected_revision=1)
        assert updated['candidate']['revision']==2
        for field in ('original_text','permissions','actions','unsupported_constraints'):
            assert updated['candidate']['content'][field]==first['candidate']['content'][field]
        assert updated['assessment']=='NEEDS_CHANGES'
        assert propose(client,prefix,updated).status_code==409
        _,selected=decide(client,prefix,updated)
        _,selected=decide(client,prefix,selected,scenario_index=1)
        assert selected['assessment']=='NEEDS_CHANGES'
        assert any(issue['code']=='RULE_KIND_UNSUPPORTED' for issue in selected['issues'])
        assert client.get(prefix).json()['data']['policy_epoch']==0

pytestmark = [pytest.mark.level3]
