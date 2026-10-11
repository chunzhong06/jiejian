# 核对建议引用现成材料、真实源码线索与全部来源头；准备可用性仍由原投影决定。
import json
from uuid import uuid4

import pytest
from product.backend.core.errors import JiejianError
from product.backend.core.preparation.suggestions import SavePreparationSuggestion
from product.backend.infra.storage.preparation.proof_sources import ProofSourceRow
from product.backend.infra.storage.preparation.suggestions import PreparationSuggestionRevisionRow
from tests.fixtures.checks.check_service import ready_check_harness
from tests.fixtures.preparation.action_preparation import add_recording


def _command(harness,items):
    return SavePreparationSuggestion.model_validate_json(json.dumps({'operation_id':uuid4().hex,
        'expected_basis_id':harness.core.preparation_suggestions.basis(harness.project_id),'content':{'items':items}}))


def _item(harness,index,material):
    return {'item_id':f'psi_{index:016x}','target':{'kind':'APPROVED','action_id':harness.action.action_id,'action_revision':harness.action.revision,
        'actor_id':harness.actor.actor_id,'actor_revision':harness.actor.revision,'effect_id':harness.effect_id},
        'material':material,'description':'核对已有材料和所需条件','source':{'classification':'HYPOTHESIS','explanation':'依照当前业务要求整理'},
        'handler':'USER','depends_on':[]}


def test_real_material_references_are_reused_without_changing_preparation(tmp_path):
    harness=ready_check_harness(tmp_path)
    try:
        core,project=harness.core,harness.project_id
        context=core.proof_preparation.context(project)
        guidance=core.preparation_suggestions.context(project)
        target_recording=next(item for item in guidance['available_recordings'] if item['purpose']=='TARGET')
        items=[_item(harness,1,{'kind':'identity','account_requirement':'核对当前成员账号','existing_identity_ids':[harness.identities[0].identity_id]}),
            _item(harness,2,{'kind':'execution','normal_steps':['按原录制核对业务操作'],'existing_recording_ids':[target_recording['recording_id']]}),
            _item(harness,3,{'kind':'resource','resource_concept':'原测试资源','existing_resource_ids':[context['resources'][0]['resource_binding_id']]})]
        before=core.preparation.get(project)
        saved=core.preparation_suggestions.save(project,_command(harness,items))
        assert saved['state']=='CURRENT'
        assert core.preparation.get(project)==before
        wrong=_item(harness,4,{'kind':'recovery','expected_state':'恢复初始状态','existing_recording_ids':[target_recording['recording_id']]})
        with pytest.raises(JiejianError):core.preparation_suggestions.save(project,_command(harness,[wrong]))
        unknown=_item(harness,5,{'kind':'identity','account_requirement':'未知账号','existing_identity_ids':['tid_'+'f'*32]})
        with pytest.raises(JiejianError):core.preparation_suggestions.save(project,_command(harness,[unknown]))
        # 新增同项目录制也必须改变建议依据，不能只覆盖已经采用的绑定。
        add_recording(harness)
        assert core.preparation_suggestions.show(project,saved['suggestion']['suggestion_id'])['state']=='STALE'
    finally:harness.close()


def test_verified_code_locations_and_source_change_are_distinguished(tmp_path):
    harness=ready_check_harness(tmp_path)
    try:
        core,project=harness.core,harness.project_id
        hints=core.preparation_suggestions.context(project)['source_hints']
        source=next(item for item in hints if item['candidate_id'].startswith('action_'))
        item=_item(harness,1,{'kind':'execution','entry_candidate_id':source['candidate_id'],'normal_steps':['检查更新文档入口']})
        item['source']={'classification':'SOURCE_CANDIDATE','candidate_ids':[source['candidate_id']],'explanation':'已授权分析找到业务入口'}
        saved=core.preparation_suggestions.save(project,_command(harness,[item]))
        assert saved['items'][0]['source_locations'][0]['relative_path']=='routes.py'
        assert str(harness.source_root) not in str(saved)
        (harness.source_root/'routes.py').write_text('def update_document():\n    return False\n',encoding='utf-8')
        old=core.preparation_suggestions.show(project,saved['suggestion']['suggestion_id'])
        assert old['state']=='STALE' and old['items'][0]['source_locations']==[]
        with pytest.raises(JiejianError):core.preparation_suggestions.save(project,_command(harness,[item]))
    finally:harness.close()


def test_suggestion_basis_covers_source_heads_beyond_first_page(tmp_path):
    harness=ready_check_harness(tmp_path)
    try:
        core,project=harness.core,harness.project_id
        # 此处只测试来源头的失效依据，不把这些头当可采用来源或运行事实。
        with core.uow_factory() as work:
            work._session.add_all([ProofSourceRow(source_id=f'psr_{index:032x}',project_id=project,revision=1,created_at_us=index) for index in range(60)])
            work.commit()
        before=core.preparation_suggestions.basis(project)
        with core.uow_factory() as work:
            work._session.get(ProofSourceRow,f'psr_{59:032x}').revision=2
            work.commit()
        assert core.preparation_suggestions.basis(project)!=before
    finally:harness.close()


def test_source_contract_is_not_a_capability_and_does_not_mutate_requirements(tmp_path):
    harness=ready_check_harness(tmp_path)
    try:
        core,project=harness.core,harness.project_id
        before=core.business_boundaries.view(project)
        item=_item(harness,1,{'kind':'evidence','capability':'RESOURCE_FIELDS_V1','observable_result':'核对业务结果'})
        with pytest.raises(JiejianError) as rejected:
            core.preparation_suggestions.save(project,_command(harness,[item]))
        assert 'source_contract_id' in str(rejected.value)
        assert 'MANAGED_TRANSACTION_RECORDS' in str(rejected.value)
        assert core.business_boundaries.view(project)==before
        assert core.preparation_suggestions.context(project)['latest'] is None
    finally:harness.close()


def test_stored_suggestion_payload_cannot_change_its_project_identity(tmp_path):
    harness=ready_check_harness(tmp_path)
    try:
        core,project=harness.core,harness.project_id
        saved=core.preparation_suggestions.save(project,_command(harness,[_item(harness,1,{'kind':'identity','account_requirement':'核对账号'})]))
        suggestion=saved['suggestion'];suggestion_id=suggestion['suggestion_id']
        with core.uow_factory() as work:
            suggestion['project_id']='app_'+'f'*32
            work._session.get(PreparationSuggestionRevisionRow,(suggestion_id,1)).payload=json.dumps(suggestion)
            work.commit()
        with pytest.raises(JiejianError) as rejected:core.preparation_suggestions.show(project,suggestion_id,1)
        assert rejected.value.code=='STORAGE_STATE'
    finally:harness.close()
