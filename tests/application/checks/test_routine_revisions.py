"""方案的准确修订、重试、并发和旧范围承接；保存不能创建执行任务。"""
import json
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from product.backend.application.checks.routine_execution import BindRoutine, SaveRoutineRevision
from product.backend.application.checks.routines import SaveCheckRoutine
from product.backend.application.agent_access.tasks import CreateCollaboration
from product.backend.domain.errors import JiejianError
from product.backend.interfaces.http.routers.checks.checks import build_checks_router
from product.protocols.checks.execution_request import PermissionReference
from product.protocols.checks.routines import RoutineScope, read_routine, routine_bytes
from product.protocols.checks.routine_reference import RoutineReference
from tests.support.builders.checks.check_service import ready_check_harness
from tests.support.builders.preparation.action_preparation import build_preparation_harness
from tests.support.builders.preparation.external_application import external_application


def command(harness, **changes):
    permission = harness.core.business_boundaries.view(harness.project_id).permission_intents[0]
    reference = PermissionReference(intent_id=permission.intent_id, revision=permission.revision, intent_hash=permission.intent_hash)
    return SaveRoutineRevision(**(dict(operation_id=uuid4().hex, expected_revision=0, name='订单权限方案',
        scope=RoutineScope(permissions=(reference,))) | changes))


def test_revision_retry_conflict_and_original_history(tmp_path, monkeypatch):
    harness = build_preparation_harness(tmp_path)
    try:
        service, project = harness.core.check_routines.revisions, harness.project_id
        first_command = command(harness)
        first = service.save(project, first_command)
        assert first.requirements and {item.kind for item in first.requirements}=={'ACCOUNT','RESOURCE','FLOW','PROOF'}
        assert read_routine(routine_bytes(first)) == first
        second_command = command(harness, routine_id=first.routine_id, expected_revision=1, name='订单权限第二版')
        second = service.save(project, second_command)
        assert second.revision == 2
        assert service.read(project, first.routine_id, 1) == first
        assert service.save(project, first_command) == first
        assert [item['revision'] for item in service.history(project, first.routine_id)] == [2, 1]
        stale = command(harness, routine_id=first.routine_id, expected_revision=1)
        with pytest.raises(JiejianError, match='已有新修订'):
            service.save(project, stale)
        with pytest.raises(JiejianError, match='其他方案内容'):
            service.save(project, first_command.model_copy(update={'name':'另一内容'}))
        monkeypatch.setattr(service.boundaries, 'view', lambda *a, **k: pytest.fail('successful retry revalidated changed rules'))
        assert service.save(project, first_command) == first
        assert service.catalog(project)['routines'][0]['revision'] == 2
        with harness.core.uow_factory() as work:
            assert work.runs.list_for_project(project) == ()
    finally:
        harness.close()


def test_legacy_range_requires_explicit_conversion_and_remains_readable(tmp_path):
    harness = build_preparation_harness(tmp_path)
    try:
        owner, project = harness.core.check_routines, harness.project_id
        old = owner.save(project, SaveCheckRoutine(operation_id=uuid4().hex))
        assert owner.revisions.catalog(project)['legacy_selections'] == [old]
        with pytest.raises(JiejianError, match='修订不存在'):
            owner.revisions.read(project, old['routine_id'], 1)
        converted = owner.revisions.save(project, command(harness, routine_id=old['routine_id']))
        assert converted.revision == 1 and converted.scope.permissions
        assert owner.list(project)[0]['selected_permissions'] is None
        assert owner.revisions.catalog(project)['legacy_selections'] == []
        with pytest.raises(JiejianError, match='不能按旧范围删除'):
            owner.delete(project, old['routine_id'])
    finally:
        harness.close()


def test_routine_reader_requires_explicit_identity_and_rejects_unknown_version(tmp_path):
    harness = build_preparation_harness(tmp_path)
    try:
        saved = harness.core.check_routines.revisions.save(harness.project_id, command(harness))
        payload = saved.model_dump(mode='json')
        for key, value in [('schema_version', '99'), ('document_type', 'other')]:
            with pytest.raises(ValueError):
                read_routine(json.dumps(payload | {key:value}).encode())
        for key in ('schema_version', 'document_type'):
            with pytest.raises(ValueError, match='explicit'):
                read_routine(json.dumps({k:v for k,v in payload.items() if k != key}).encode())
        with pytest.raises(JiejianError, match='修订不存在'):
            harness.core.check_routines.revisions.read('app_'+uuid4().hex, saved.routine_id, 1)
    finally:
        harness.close()


def test_binding_does_not_copy_legacy_readiness_into_an_unidentified_environment(tmp_path):
    harness = ready_check_harness(tmp_path)
    try:
        service, project = harness.core.check_routines.revisions, harness.project_id
        saved = service.save(project, command(harness))
        preview = service.binding_preview(project, saved.routine_id, 1)
        assert preview['preview'].can_execute and not preview['can_bind']
        assert preview['environment'] is None
        with pytest.raises(JiejianError, match='当前环境'):
            service.bind(project, saved.routine_id, BindRoutine(operation_id=uuid4().hex, revision=1,
                expected_material_fingerprint=preview['material_fingerprint'], expected_environment_fingerprint='a'*64))
        assert service.bindings(project, saved.routine_id, 1) == []
    finally:
        harness.close()


def test_revision_http_accepts_json_arrays_and_rejects_scalar_coercion(tmp_path):
    harness = build_preparation_harness(tmp_path)
    try:
        app = FastAPI()
        app.include_router(build_checks_router(harness.core))
        body = command(harness).model_dump(mode='json')
        with TestClient(app) as client:
            url = '/api/projects/'+harness.project_id+'/check-routines/revisions'
            response = client.post(url, json=body)
            assert response.status_code == 200, response.text
            assert response.json()['data']['schema_version'] == '2'
            assert client.post(url, json=body | {'expected_revision':'0'}).status_code == 422
            assert client.post(url, json=body | {'cookie':'secret'}).status_code == 422
    finally:
        harness.close()


def test_catalog_cursor_does_not_repeat_updated_revisions(tmp_path):
    harness=build_preparation_harness(tmp_path)
    try:
        service,project=harness.core.check_routines.revisions,harness.project_id
        saved=[service.save(project,command(harness,operation_id=f'{number:032x}',name='方案 '+str(number))) for number in (1,2,3)]
        first=service.catalog(project,limit=2)
        assert [item['routine_id'] for item in first['routines']]==[item.routine_id for item in saved[:2]]
        service.save(project,command(harness,routine_id=saved[0].routine_id,expected_revision=1,name='修订后的方案'))
        second=service.catalog(project,after=first['next_cursor'],limit=2)
        assert [item['routine_id'] for item in second['routines']]==[saved[2].routine_id]
        assert second['next_cursor'] is None
        assert service.catalog(project,limit=2)['routines'][0]['revision']==2
    finally:
        harness.close()


def test_binding_freezes_exact_plan_and_retry_survives_later_environment_change(tmp_path, monkeypatch):
    with external_application(tmp_path) as harness:
        core, project = harness.core, harness.project_id
        service = core.check_routines.revisions
        core.operation_flows.adopt(project, harness.flow.id, harness.flow.revision)
        saved = service.save(project, command(harness))
        monkeypatch.setattr(core.secret_store, 'read', lambda ref: pytest.fail('binding or submit read a secret value'))
        preparation = service.binding_preview(project, saved.routine_id, 1)
        assert preparation['can_bind'], [gap.reason for gap in preparation['preview'].gaps]
        assert {item.kind for item in preparation['assets']} == {'ACCOUNT','FLOW','RESOURCE','PROOF'}
        binding_command = BindRoutine(operation_id=uuid4().hex, revision=1,
            expected_material_fingerprint=preparation['material_fingerprint'],
            expected_environment_fingerprint=preparation['environment'].fingerprint)
        bound = service.bind(project, saved.routine_id, binding_command)
        assert all(any(asset.requirement_slot==requirement.slot for asset in bound.assets) for requirement in saved.requirements)
        assert len([asset for asset in bound.assets if asset.kind=='RESOURCE'])==1
        assert service.bind(project, saved.routine_id, binding_command) == bound
        reference = RoutineReference(routine_id=saved.routine_id, revision=1, binding_id=bound.binding_id)
        handoff=core.collaboration.create(project,CreateCollaboration(operation_id=uuid4().hex,goal='核对当前方案',purpose='CHECK',
            references=dict(routine_id=saved.routine_id,routine_revision='1',binding_id=bound.binding_id)))
        context=core.collaboration.context(project,handoff['task_id'])['check_plan']
        assert context['document']==saved.model_dump(mode='json') and context['binding']==bound.model_dump(mode='json')
        preview = core.checks.preview(project, routine_reference=reference)
        assert preview.can_execute, preview.model_dump()
        first = core.checks.submit(project, routine_reference=reference,
            expected_plan_fingerprint=preview.plan_fingerprint, idempotency_key='routine-run')
        request = core.checks.pending_request(first.run.run_id)
        status = core.check_results.status(first.run.run_id, project_id=project)
        assert status.routine == request.routine and status.environment == harness.environment
        assert core.checks.routine_receipt(project, reference, preview.plan_fingerprint, 'routine-run').run.run_id == first.run.run_id
        assert request.routine.routine_fingerprint == saved.fingerprint
        assert request.routine.binding_fingerprint == bound.fingerprint
        assert request.selection.selected == saved.scope.permissions
        with core.uow_factory() as work:
            current = work.application_understanding.get(project)
            work.application_understanding.replace(current.model_copy(update={
                'environment':current.environment.model_copy(update={'revision':2,'deployment_label':'新部署'})}))
            work.commit()
        assert service.bind(project, saved.routine_id, binding_command) == bound
        repeated = core.checks.submit(project, routine_reference=reference,
            expected_plan_fingerprint=preview.plan_fingerprint, idempotency_key='routine-run')
        assert not repeated.created and repeated.run.run_id == first.run.run_id
        changed = core.checks.preview(project, routine_reference=reference)
        assert not changed.can_execute
        with pytest.raises(JiejianError):
            core.checks.submit(project, routine_reference=reference,
                expected_plan_fingerprint=preview.plan_fingerprint, idempotency_key='another-run')
        assert harness.state['target_calls'] == 0
