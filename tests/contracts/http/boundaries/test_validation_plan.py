"""保护要求评估的只读性、候选隔离、原决定接续和过期依据拒绝。"""
from uuid import uuid4

from tests.support.builders.control_plane import TestClient, create_app
from tests.support.builders.boundary_candidates import _content, _project, _save, confirm_scope, propose


def _approve(client, prefix, saved):
    ready = confirm_scope(client, prefix, saved)
    response = propose(client, prefix, ready)
    assert response.status_code == 201, response.text
    proposal_id = response.json()['data']['proposal_id']
    proposal = client.get(prefix + '/proposals/' + proposal_id).json()['data']['proposal']
    response = client.post(prefix + '/proposals/' + proposal_id + '/approve', json={
        'schema_version': '1', 'expected_fingerprint': proposal['proposal_fingerprint'], 'reason': '核对业务标准'})
    assert response.status_code == 200, response.text


def test_candidate_validation_explains_effect_without_approving_or_preparing(tmp_path):
    with TestClient(create_app(tmp_path / 'var', start_worker=False, environ={})) as client:
        project = _project(client, tmp_path / 'source')
        prefix = '/api/projects/' + project + '/business-boundaries'
        _, saved = _save(client, prefix)
        candidate = saved['candidate']
        response = client.get(prefix + '/validation-plan', params={'candidate_id': candidate['candidate_id'], 'revision': 1})
        assert response.status_code == 200, response.text
        plan = response.json()['data']
        assert plan['state'] == 'CURRENT'
        assert plan['candidate_revision'] == 1
        effect = plan['requirements'][0]['effects'][0]
        assert effect['kind'] == 'STATE_MUTATION'
        assert effect['supported_paths'] == ['TRANSACTION_HISTORY_V2']
        assert effect['material_status'] == 'NEEDS_SOURCE'
        assert any('恢复' in item for item in plan['requirements'][0]['preparation_requirements'])
        assert client.get(prefix).json()['data']['policy_epoch'] == 0
        assert client.get(prefix + '/rule-candidates/' + candidate['candidate_id']).json()['data']['candidate']['revision'] == 1
        assert client.get(prefix + '/validation-plan', params={'candidate_id': candidate['candidate_id'], 'revision': 1}).json()['data'] == plan


def test_unsaved_maintenance_is_evaluated_against_its_exact_basis_without_a_proposal(tmp_path):
    with TestClient(create_app(tmp_path / 'var', start_worker=False, environ={})) as client:
        project=_project(client,tmp_path/'source')
        prefix='/api/projects/'+project+'/business-boundaries'
        _,saved=_save(client,prefix)
        _approve(client,prefix,saved)
        draft=client.get(prefix+'/maintenance-draft').json()['data']
        command=dict(schema_version='1',expected_boundary_state_fingerprint=draft['boundary_state_fingerprint'],
            actors=draft['actors'],actions=draft['actions'],permissions=draft['permissions'])
        command['permissions'][0]['expectation']='DENY'
        response=client.post(prefix+'/validation-plan/preview',json=command)
        assert response.status_code==200,response.text
        result=response.json()['data']
        assert result['draft_fingerprint'] and result['requirements'][0]['expectation']=='DENY'
        assert '缺少' in result['requirements'][0]['normal_control']
        assert client.get(prefix).json()['data']['policy_epoch']==1
        command['expected_boundary_state_fingerprint']='f'*64
        assert client.post(prefix+'/validation-plan/preview',json=command).status_code==409


def test_preapproval_question_is_added_to_the_same_candidate_without_losing_the_story(tmp_path):
    with TestClient(create_app(tmp_path/'var',start_worker=False,environ={})) as client:
        project=_project(client,tmp_path/'source')
        prefix='/api/projects/'+project+'/business-boundaries'
        _,saved=_save(client,prefix)
        candidate=saved['candidate']
        plan=client.get(prefix+'/validation-plan',params=dict(candidate_id=candidate['candidate_id'],revision=1)).json()['data']
        question=plan['questions'][0]
        response=client.post(prefix+'/validation-questions/'+question['requirement_id'],json=dict(operation_id=uuid4().hex,
            expected_fingerprint=plan['fingerprint'],question_fingerprint=question['fingerprint'],candidate_id=candidate['candidate_id'],revision=1))
        assert response.status_code==201,response.text
        updated=response.json()['data']['candidate']
        assert updated['candidate_id']==candidate['candidate_id'] and updated['revision']==2
        assert updated['content']['original_text']==candidate['content']['original_text']
        assert updated['content']['permissions']==candidate['content']['permissions']
        assert any(item['requirement_id']==question['requirement_id'] for item in updated['content']['requirement_sources'])
        assert client.get(prefix).json()['data']['policy_epoch']==0


def test_question_uses_original_scope_decision_and_save_receipt_after_restart(tmp_path):
    var = tmp_path / 'var'
    with TestClient(create_app(var, start_worker=False, environ={})) as client:
        project = _project(client, tmp_path / 'source')
        prefix = '/api/projects/' + project + '/business-boundaries'
        _, saved = _save(client, prefix)
        _approve(client, prefix, saved)
        plan = client.get(prefix + '/validation-plan').json()['data']
        question = next(item for item in plan['questions'] if item['dimension'].startswith('OTHER_ACCOUNT:'))
        command = {'operation_id': uuid4().hex, 'expected_fingerprint': plan['fingerprint'], 'question_fingerprint': question['fingerprint']}
        url = prefix + '/validation-questions/' + question['requirement_id']
        response = client.post(url, json=command)
        assert response.status_code == 201, response.text
        opened = response.json()['data']
        assert opened['candidate']['content']['permissions'] == []
        assert client.post(url, json=command).json()['data'] == opened
        assert client.post(url, json={**command, 'expected_fingerprint': 'f' * 64}).status_code == 409
        item = opened['scope_review'][0]
        response = client.post(prefix + '/rule-candidates/' + opened['candidate']['candidate_id'] + '/scope-decisions', json={
            'operation_id': uuid4().hex, 'expected_basis_id': opened['candidate']['basis_id'], 'expected_revision': 1,
            'requirement_id': item['source']['requirement_id'], 'requirement_fingerprint': item['fingerprint'],
            'disposition': 'OUT_OF_SCOPE', 'requirement': '此项目账号均为独立资料所有者，本轮暂不覆盖其他账号。',
            'reason': '负责人明确本次业务范围', 'time_scope': 'NOT_APPLICABLE'})
        assert response.status_code == 201, response.text
        checked = client.get(prefix + '/validation-plan').json()['data']
        decided = next(item for item in checked['questions'] if item['requirement_id'] == question['requirement_id'])
        assert decided['status'] == 'EXCLUDED'
        assert decided['decision_reason'] == '负责人明确本次业务范围'
        assert client.get(prefix).json()['data']['policy_epoch'] == 1
    with TestClient(create_app(var, start_worker=False, environ={})) as client:
        assert client.post(url, json=command).json()['data'] == opened
        assert next(item for item in client.get(prefix + '/validation-plan').json()['data']['questions']
                    if item['requirement_id'] == question['requirement_id'])['status'] == 'EXCLUDED'

        def maintain(change):
            draft = client.get(prefix + '/maintenance-draft').json()['data']
            change(draft)
            created = client.post(prefix + '/maintenance-proposals', json=dict(schema_version='1',
                expected_boundary_state_fingerprint=draft['boundary_state_fingerprint'],
                actors=draft['actors'], actions=draft['actions'], permissions=draft['permissions'],
                provenance='核对决定依据发生变化时的连续性'))
            assert created.status_code == 201, created.text
            proposal = created.json()['data']['proposal']
            result = client.post(prefix + '/proposals/' + proposal['proposal_id'] + '/approve', json=dict(
                schema_version='1', expected_fingerprint=proposal['proposal_fingerprint'], reason='核对本次业务变化'))
            assert result.status_code == 200, result.text
            return next(item for item in client.get(prefix + '/validation-plan').json()['data']['questions']
                        if item['requirement_id'] == question['requirement_id'])

        # 无关角色不撤销已有排除；同一业务动作的语义变化必须重核原决定。
        unrelated = maintain(lambda draft: draft['actors'].append(dict(item_id='pactr_'+'2'*16,
            display_name='独立审阅人', description='尚未参与本操作的另一角色', effective_state='ACTIVE')))
        assert unrelated['status'] == 'EXCLUDED' and unrelated['fingerprint'] == question['fingerprint']
        def change_action(draft):
            draft['actions'][0]['description'] += '，发布后同步到外部交付区'
        changed = maintain(change_action)
        assert changed['status'] == 'RECHECK' and changed['fingerprint'] != question['fingerprint']


def test_stale_question_and_cross_project_references_are_rejected(tmp_path):
    with TestClient(create_app(tmp_path / 'var', start_worker=False, environ={})) as client:
        project = _project(client, tmp_path / 'source')
        other = _project(client, tmp_path / 'other')
        prefix = '/api/projects/' + project + '/business-boundaries'
        _, saved = _save(client, prefix)
        _approve(client, prefix, saved)
        plan = client.get(prefix + '/validation-plan').json()['data']
        question = plan['questions'][0]
        response = client.post(prefix + '/validation-questions/' + question['requirement_id'], json={
            'operation_id': uuid4().hex, 'expected_fingerprint': '0' * 64, 'question_fingerprint': question['fingerprint']})
        assert response.status_code == 409
        other_prefix = '/api/projects/' + other + '/business-boundaries'
        assert client.get(other_prefix + '/validation-plan', params={'candidate_id': saved['candidate']['candidate_id']}).status_code == 404
        assert client.get(prefix + '/validation-plan', params={'revision': 1}).status_code == 400
        assert client.get(prefix + '/validation-plan', params={'intent_id': 'pin_' + '0' * 32}).status_code == 404


def test_disclosure_and_creation_have_distinct_proof_paths(tmp_path):
    with TestClient(create_app(tmp_path / 'var', start_worker=False, environ={})) as client:
        project = _project(client, tmp_path / 'source')
        prefix = '/api/projects/' + project + '/business-boundaries'
        for kind, expected in [('DATA_DISCLOSURE', ['HTTP_ENTITY_QUERY', 'RESOURCE_FIELDS_V1']), ('OBJECT_CREATION', ['OBJECT_CREATION_V1'])]:
            content = _content()
            effect = content['actions'][0]['effect_catalog'][0]
            effect.update(effect_kind=kind, expected_state=None)
            if kind == 'DATA_DISCLOSURE':
                effect['protected_projection'] = ['title']
                content['actions'][0]['state_changing'] = False
            _, saved = _save(client, prefix, content)
            response = client.get(prefix + '/validation-plan', params={'candidate_id': saved['candidate']['candidate_id'], 'revision': 1})
            assert response.status_code == 200, response.text
            assert response.json()['data']['requirements'][0]['effects'][0]['supported_paths'] == expected
