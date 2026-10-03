# 验证建议忠于当前任务与来源事实，未知状态不编造原因，也不越过人的决定。
from copy import deepcopy
from types import SimpleNamespace

import pytest

from product.backend.workflows.preparation.guidance.service import PreparationGuidanceService, _source_advice
from product.backend.workflows.workspace.models import PrimaryTaskView


def source_context():
    return {'project_id': 'app_guidance', 'basis_id': 'basis-current', 'runtime_available': True,
        'actions': [{'action_id':'action-one', 'revision':3, 'effects':[{'effect_id':'effect-one'}]}],
        'sources': [{'source_id': 'source-one', 'revision': 2, 'supported': True, 'adopted': False,
            'read_scope_confirmed': True, 'preflight': None,
            'config': {'action_id': 'action-one', 'action_revision': 3, 'effect_id': 'effect-one'}}]}


def task(kind='COMPLETE_EFFECT_EVIDENCE'):
    return PrimaryTaskView(task_id='ptk_'+'1'*32, task_kind=kind, action_label='处理当前材料',
        completion_criteria='核对当前材料', title='当前任务', why_now='服务端选择的原因',
        user_responsibility='核对业务事实', system_will_do='读取当前情况', route='/tests',
        can_execute=True, stale_fingerprint='a'*64, business_action_id='action-one',
        action_revision=3, effect_id='effect-one')


@pytest.mark.parametrize('updates,expected,handler,level', [
    ({'supported': False}, 'MIGRATE_SOURCE', 'AGENT', 'PREPARE'),
    ({'read_scope_confirmed': False}, 'CONFIRM_READ_SCOPE', 'USER', None),
    ({}, 'RUN_PREFLIGHT', 'EITHER', 'EXECUTE'),
    ({'preflight': {'preflight_id': 'p1', 'state': 'RUNNING', 'current_basis': True, 'report': None}}, 'WAIT_PREFLIGHT', 'SYSTEM', 'READ'),
    ({'preflight': {'preflight_id': 'p1', 'state': 'SUCCEEDED', 'current_basis': True, 'report': {'assessment': 'USABLE', 'checks': []}}}, 'REVIEW_ADOPTION', 'USER', 'READ'),
])
def test_source_stage_exposes_exact_reference_without_approval_tool(updates, expected, handler, level):
    context = source_context()
    context['sources'][0].update(updates)
    result = _source_advice(context, context['sources'][0])
    assert result.next_action.kind == expected
    assert result.next_action.handler == handler
    assert result.next_action.required_level == level
    assert result.next_action.source_revision == 2
    assert result.next_action.action_revision == 3
    assert 'project_id=app_guidance' in result.next_action.gui_url
    assert result.next_action.mcp_tool not in {'approve', 'adopt', 'grant_scope'}


def test_runtime_unavailable_does_not_claim_lost_configuration_or_start_it():
    context = source_context(); context['runtime_available'] = False
    result = _source_advice(context, context['sources'][0])
    assert result.next_action.kind == 'REVIEW_RUNTIME'
    assert result.next_action.mcp_tool is None
    assert '保留' in result.next_action.reason


@pytest.mark.parametrize('code,kind,phrase', [
    ('ACTUAL_IDENTITY_MISMATCH', 'REVIEW_IDENTITY', '账号或角色'),
    ('MAPPING_MISSING', 'REVIEW_SOURCE', '字段'),
    ('PROTECTED_FIELD_MISSING', 'REVIEW_SOURCE', '受保护'),
    ('FUTURE_UNKNOWN_REASON', 'REVIEW_SOURCE', '不推测'),
])
def test_failed_checks_offer_bounded_help_without_guessing_identity_expiry(code, kind, phrase):
    context = source_context()
    source = context['sources'][0]
    source['preflight'] = {'preflight_id': 'p1', 'state': 'SUCCEEDED', 'current_basis': True,
                          'report': {'assessment': 'NEEDS_CHANGES', 'checks': [{'code': code, 'status': 'MISSING'}]}}
    result = _source_advice(context, source).next_action
    assert result.kind == kind and phrase in result.reason
    if kind == 'REVIEW_IDENTITY':
        assert 'identities=1' in result.gui_url and result.mcp_tool is None


def test_old_usable_report_does_not_offer_adoption_or_permission_pass():
    context = source_context(); source = context['sources'][0]
    source['preflight'] = {'preflight_id': 'p1', 'state': 'SUCCEEDED', 'current_basis': False,
                          'report': {'assessment': 'USABLE', 'checks': []}}
    result = _source_advice(context, source)
    assert result.next_action.kind == 'RUN_PREFLIGHT'
    assert '旧报告' in result.next_action.reason
    source['preflight']['current_basis'] = True; source['adopted'] = True
    result = _source_advice(context, source)
    assert result.state == 'USABLE' and result.next_action is None


def test_changed_rule_reference_does_not_suggest_running_an_obsolete_source():
    context=source_context();context['actions'][0]['revision']=4
    result=_source_advice(context,context['sources'][0])
    assert result.next_action.kind=='REVIEW_RULE_REFERENCE'
    assert result.next_action.mcp_tool is None


def test_cancelled_job_with_a_report_does_not_become_usable():
    context=source_context();source=context['sources'][0]
    source['preflight']={'preflight_id':'p1','state':'CANCELLED','current_basis':True,'report':{'assessment':'USABLE','checks':[]}}
    assert _source_advice(context,source).next_action.kind=='RUN_PREFLIGHT'


def guidance(context, primary, after=None):
    reads = iter([context, after or deepcopy(context)])
    return PreparationGuidanceService(sources=SimpleNamespace(context=lambda _: next(reads)),
        workspace=SimpleNamespace(get=lambda _: SimpleNamespace(primary_task=primary)),
        preparation=SimpleNamespace(get=lambda _: SimpleNamespace(actions=()))).context('app_guidance')['guidance']


def test_global_account_task_precedes_source_preflight():
    result = guidance(source_context(), task('PREPARE_TEST_IDENTITY'))
    assert result['next_action']['kind'] == 'PREPARE_TEST_IDENTITY'
    assert result['next_action']['task_id'] == task().task_id
    assert 'task_id=' in result['next_action']['gui_url']
    assert result['sources'][0]['next_action']['kind'] == 'RUN_PREFLIGHT'


def test_evidence_task_uses_exact_source_but_multiple_candidates_are_not_auto_selected():
    context = source_context()
    result = guidance(context, task())
    assert result['next_action']['kind'] == 'RUN_PREFLIGHT'
    second = deepcopy(context['sources'][0]); second['source_id'] = 'source-two'
    context['sources'].append(second)
    result = guidance(context, task())
    assert result['next_action']['kind'] == 'COMPLETE_EFFECT_EVIDENCE'
    assert result['next_action']['source_id'] is None


def test_changing_basis_suppresses_mixed_materials_and_next_action():
    context = source_context(); after = deepcopy(context); after['basis_id'] = 'basis-new'
    result = guidance(context, task(), after)
    assert result['state'] == 'NEEDS_REFRESH'
    assert result['next_action'] is None and result['materials'] == [] and result['sources'] == []


def test_official_ready_task_does_not_require_a_node_proof_source():
    context = source_context(); context.update(runtime_available=False, sources=[])
    result = guidance(context, task('RUN_CURRENT_CHECK'))
    assert result['next_action']['kind'] == 'RUN_CURRENT_CHECK'
    assert result['next_action']['mcp_tool'] == 'jiejian_check_run'
