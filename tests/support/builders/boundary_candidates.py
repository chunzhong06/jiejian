# 共用规则候选和本地应用构造器，不导入或执行其他测试用例。
from copy import deepcopy
from uuid import uuid4


def _content():
    return {
        "original_text": "负责人可以发布自己的资料。",
        "actors": [{"item_id": "pactr_1111111111111111", "write_mode": "CREATE",
            "display_name": "负责人", "description": "管理自己项目的资料", "effective_state": "ACTIVE"}],
        "actions": [{"item_id": "pactn_1111111111111111", "write_mode": "CREATE",
            "display_name": "发布资料", "description": "将资料持久发布", "primary_resource_concept": "项目资料",
            "operation_kind": "CHANGE", "state_changing": True, "effective_state": "ACTIVE",
            "effect_catalog": [{"item_id": "peff_1111111111111111", "business_label": "资料被发布",
                "effect_kind": "STATE_MUTATION", "resource_concept": "资料", "description": "资料已持久发布",
                "expected_state": "published"}]}],
        "permissions": [{"item_id": "pperm_1111111111111111", "write_mode": "CREATE", "effective_state": "ACTIVE",
            "subject_actor_item_id": "pactr_1111111111111111", "business_action_item_id": "pactn_1111111111111111",
            "resource_owner_actor_item_id": "pactr_1111111111111111", "relation": "OWNS", "expectation": "ALLOW",
            "protected_effect_item_ids": ["peff_1111111111111111"]}],
        "examples": [{"description": "负责人发布自己项目的资料，应该成功", "permission_item_id": "pperm_1111111111111111"}],
    }


def _project(client, path):
    path.mkdir()
    response = client.post("/api/applications/connect", json={"schema_version": "1", "source_root": str(path), "project_name": "普通资料应用"})
    assert response.status_code == 201, response.text
    return response.json()["data"]["project"]["project_id"]


def _save(client, prefix, content=None, **extra):
    context = client.get(prefix + "/rule-context")
    assert context.status_code == 200, context.text
    basis = context.json()["data"]["basis_id"]
    content = deepcopy(content if content is not None else _content())
    content.setdefault('requirement_sources', [{'requirement_id':'req_'+'1'*16, 'title':'本轮发布权限',
        'origin':'USER', 'source_excerpt':content['original_text'], 'interpretation':content['original_text'],
        'permission_item_ids':[item['item_id'] for item in content['permissions']]}])
    request = {"operation_id": uuid4().hex, "expected_basis_id": basis, "content": content, **extra}
    response = client.post(prefix + "/rule-candidates", json=request)
    assert response.status_code == 201, response.text
    return request, response.json()["data"]


def confirm_scope(client, prefix, saved):
    candidate = saved['candidate']
    choices = [{'requirement_id':item['source']['requirement_id'], 'requirement_fingerprint':item['fingerprint'],
        'disposition':'IN_SCOPE', 'requirement':item['source']['interpretation'],
        'reason':'本轮明确核对这项业务权限。', 'time_scope':'CHECK_WINDOW'}
        for item in saved['scope_review'] if item['status'] != 'CONFIRMED']
    if not choices:
        return saved
    response = client.post(f"{prefix}/rule-candidates/{candidate['candidate_id']}/scope-batch", json={
        'operation_id':uuid4().hex, 'expected_basis_id':candidate['basis_id'],
        'expected_revision':candidate['revision'], 'choices':choices})
    assert response.status_code == 201, response.text
    return response.json()['data']




def scenario_content():
    content = _content()
    content['original_text'] = '负责人可以发布自己的资料，评审的发布权限需要确认。'
    actor = deepcopy(content['actors'][0])
    actor.update(item_id='pactr_2222222222222222', display_name='评审')
    content['actors'].append(actor)
    rule = deepcopy(content['permissions'][0])
    rule.update(item_id='pperm_2222222222222222', subject_actor_item_id=actor['item_id'], relation='OTHER_ROLE', expectation='DENY')
    content['permissions'].append(rule)
    content['examples'].append({'description': '评审发布负责人的资料', 'permission_item_id': rule['item_id']})
    allowed = {**rule, 'expectation': 'ALLOW'}
    content['scenarios'] = [{'scenario_id': 'rsc_1111111111111111', 'original_excerpt': '评审的发布权限需要确认',
        'question': '评审能否发布负责人的资料？', 'options': [
            {'option_id': 'rop_1111111111111111', 'label': '允许发布', 'explanation': '评审可以发布这份资料。', 'replacements': [allowed]},
            {'option_id': 'rop_2222222222222222', 'label': '禁止发布', 'explanation': '评审不能发布这份资料。', 'replacements': [rule]}]}]
    return content



def decide(client, prefix, saved, action='SELECT', option='rop_2222222222222222', scenario_index=0, **extra):
    candidate = saved['candidate']; scenario = candidate['content']['scenarios'][scenario_index]
    command = {'operation_id': uuid4().hex, 'expected_basis_id': candidate['basis_id'], 'expected_revision': candidate['revision'],
        'scenario_id': scenario['scenario_id'], 'scenario_fingerprint': scenario['scenario_fingerprint'], 'action': action, **extra}
    if action == 'SELECT':
        command['option_id'] = option
    response = client.post(f"{prefix}/rule-candidates/{candidate['candidate_id']}/decisions", json=command)
    assert response.status_code == 201, response.text
    return command, response.json()['data']



def propose(client, prefix, saved):
    candidate = saved['candidate']
    return client.post(f"{prefix}/rule-candidates/{candidate['candidate_id']}/proposals",
        json={'operation_id': uuid4().hex, 'revision': candidate['revision']})
