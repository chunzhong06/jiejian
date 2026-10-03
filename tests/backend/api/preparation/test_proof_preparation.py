# 验证所有准备写入口先经过本机会话/同源防护，空项目读取不执行目标或生成权限事实。
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient as RawClient
from types import SimpleNamespace
from product.backend.api.routers.preparation.proof_sources import build_proof_sources_router
from tests.fixtures.control_plane import TestClient, create_app, TEST_CONTROL_ORIGIN


@pytest.mark.parametrize('suffix',['sources','read-scopes','read-scopes/revoke','preflights','preflights/cancel','adoptions'])
def test_preparation_mutations_require_current_gui_session_and_origin(tmp_path,suffix):
    app = create_app(tmp_path/'var',start_worker=False,environ={})
    path = '/api/projects/any/proof-preparation/' + suffix
    with RawClient(app,base_url=TEST_CONTROL_ORIGIN) as client:
        assert client.post(path,json={}).status_code == 403
        client.cookies.set('jiejian_control_session','old-instance')
        assert client.post(path,json={},headers={'Origin':TEST_CONTROL_ORIGIN}).status_code == 403
    with TestClient(create_app(tmp_path/'var',start_worker=False,environ={})) as client:
        assert client.post(path,json={},headers={'Origin':'https://external.invalid'}).status_code == 403


def test_detached_proof_router_without_control_guard_rejects_requests():
    app = FastAPI()
    app.include_router(build_proof_sources_router(SimpleNamespace(proof_preparation=None)))
    with RawClient(app) as client:
        assert client.post('/api/projects/any/proof-preparation/adoptions',json={}).status_code == 403


def test_empty_project_preparation_context_is_read_only(tmp_path):
    source = tmp_path/'source'
    source.mkdir()
    with TestClient(create_app(tmp_path/'var',start_worker=False,environ={})) as client:
        project = client.post('/api/applications/connect',json={'schema_version':'1','source_root':str(source),'project_name':'普通应用'}).json()['data']['project']['project_id']
        path = f'/api/projects/{project}/proof-preparation'
        response = client.get(path)
        assert response.status_code == 200,response.text
        assert response.json()['data']['sources'] == []
        assert response.json()['data']['runtime_available'] is False
        guidance = response.json()['data']['guidance']
        workspace = client.get(f'/api/projects/{project}/workspace').json()['data']
        assert guidance['state'] == 'CURRENT'
        assert guidance['next_action']['kind'] == workspace['primary_task']['task_kind']
        assert guidance['next_action']['task_id'] == workspace['primary_task']['task_id']
        assert guidance['materials'] == []
        with client.app.state.context.uow_factory() as work:
            assert work.jobs.list_for_project(project) == ()
