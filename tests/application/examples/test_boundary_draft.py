"""预置规则读取只形成展示数据；创建提案仍需显式命令。"""
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from product.backend.application.examples.node_environment import NodeOfficialSampleExperience
from product.backend.interfaces.http.routers.applications.experience import build_experience_router


def _service():
    created = []
    service = SimpleNamespace(
        _active=lambda: SimpleNamespace(project_id='prj_1234567890abcdef'),
        understanding=SimpleNamespace(get=lambda _: SimpleNamespace(role_candidates=[], action_candidates=[])),
        boundaries=SimpleNamespace(create_initial_proposal=lambda project, command: created.append((project, command)) or command),
    )
    service.boundary_draft=lambda **kwargs: NodeOfficialSampleExperience.boundary_draft(service, **kwargs)
    return service, created


def test_preview_never_creates_or_approves_permissions():
    service, created = _service()
    allowed=service.boundary_draft(exhibition_download=True)
    denied=service.boundary_draft(exhibition_download=False)
    assert created == []
    assert allowed.project_id == denied.project_id
    assert len(allowed.command.proposed_permissions) == 5
    assert allowed.command.proposed_permissions[-1].expectation.value == 'ALLOW'
    assert denied.command.proposed_permissions[-1].expectation.value == 'DENY'
    assert denied.choice_permission_item_id == denied.command.proposed_permissions[-1].item_id
    command=NodeOfficialSampleExperience.boundary_proposal(service, exhibition_download=False)
    assert len(created) == 1
    assert command == denied.command


def test_draft_http_reader_keeps_choice_and_project_without_writing():
    service, created = _service()
    app=FastAPI()
    context=SimpleNamespace(official_experience=service, official_samples=SimpleNamespace(installation=SimpleNamespace(runtime_kind='NODE_ESM')))
    app.include_router(build_experience_router(context))
    with TestClient(app) as client:
        response=client.get('/api/experience/official-sample/boundary-draft?exhibition_download=false')
        assert response.status_code == 200
        data=response.json()['data']
        assert data['project_id'] == 'prj_1234567890abcdef'
        assert data['command']['proposed_permissions'][-1]['expectation'] == 'DENY'
        assert client.get('/api/experience/official-sample/boundary-draft?exhibition_download=invalid').status_code == 422
    assert created == []


def test_python_preview_uses_same_recipe_without_mutating_the_experience():
    from threading import RLock
    from product.backend.application.examples.environment import OfficialSampleExperience
    current=SimpleNamespace(project_id='prj_1234567890abcdef')
    service=SimpleNamespace(_lock=RLock(),_require_active=lambda:current,
        _understanding=SimpleNamespace(get=lambda _:SimpleNamespace(role_candidates=[],action_candidates=[])))
    service._boundary_command=lambda value:OfficialSampleExperience._boundary_command(service,value)
    preview=OfficialSampleExperience.boundary_draft(service)
    assert preview.runtime_kind=='PYTHON'
    assert preview.choice_permission_item_id is None
    assert len(preview.command.proposed_permissions)==3
    assert vars(current)=={'project_id':'prj_1234567890abcdef'}
