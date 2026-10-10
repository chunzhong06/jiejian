# 唯一官方Node示例的同意、人的规则选择、材料门禁及准确停止API。
from pathlib import Path
import time
import pytest
from product.backend.core.lifecycle import ProjectStatus
from tests.fixtures.secrets import InMemorySecretStore
from tests.fixtures.control_plane import TestClient,create_app
from tests.fixtures.runtime.runtime_environment import runtime_identity_environment

_SAMPLE_ROOT=Path(__file__).resolve().parents[4]/'samples/web/digital_gallery'
pytestmark=[pytest.mark.process,pytest.mark.slow]

def _app(tmp_path,*,sample_root=_SAMPLE_ROOT):
    var=tmp_path/'var';store=InMemorySecretStore()
    return create_app(var,start_worker=False,official_sample_root=sample_root,secret_store=store,environ=runtime_identity_environment(var)),store

def _completed(client,response):
    assert response.status_code==202,response.text
    operation=response.json()['data']['operation_id']
    deadline=time.monotonic()+35
    while time.monotonic()<deadline:
        response=client.get('/api/experience/official-sample',params={'operation_id':operation})
        state=response.json()['data']['operation_state']
        if state!='PENDING':
            assert state=='SUCCEEDED',response.text
            return response
        time.sleep(.1)
    raise AssertionError('原环境操作未在期限内完成')

def _start(client):return _completed(client,client.post('/api/experience/official-sample/start',json={'schema_version':'1','consent':True}))

def test_unavailable_installation_keeps_product_alive_and_requires_consent(tmp_path):
    app,_=_app(tmp_path,sample_root=None)
    with TestClient(app) as client:
        status=client.get('/api/experience/official-sample').json()['data']
        assert not status['available'] and not status['active'] and status['project_id'] is None
        assert client.get('/ready').status_code==200
        assert client.post('/api/experience/official-sample/start',json={'schema_version':'1','consent':False}).status_code==422
        assert client.post('/api/experience/official-sample/boundary-proposal').status_code!=200
        assert not client.get('/api/experience/official-sample/validation-summary').json()['data']['available']

def test_start_stop_preserves_project_and_explicit_reset_archives(tmp_path):
    app,_=_app(tmp_path)
    with TestClient(app) as client:
        first_response=_start(client);assert first_response.status_code==200,first_response.text
        first=first_response.json()['data'];core=app.state.context
        source=Path(core.application_understanding.get(first['project_id']).source_root)
        assert first['active'] and first['runtime_kind']=='NODE_ESM' and first['scenario_version']=='BASELINE'
        assert not first['scenario_prepared'] and _start(client).json()['data']['project_id']==first['project_id']
        response=client.post('/api/experience/official-sample/reset',json={'schema_version':'1','consent':True})
        response=_completed(client,response)
        assert response.status_code==200,response.text
        second=response.json()['data'];assert second['project_id']!=first['project_id']
        assert source.is_dir() and core.projects.get(first['project_id']).status is ProjectStatus.ARCHIVED
        stopped=client.post('/api/experience/official-sample/stop');assert stopped.status_code==200,stopped.text
        assert not stopped.json()['data']['active'] and stopped.json()['data']['recovery_state']=='EXITED'
        assert stopped.json()['data']['workspace_retained']
        assert core.projects.get(second['project_id']).status is not ProjectStatus.ARCHIVED

def test_prepare_requires_approval_then_prepares_accounts_but_leaves_proof_adoption_to_user(tmp_path):
    from tests.backend.workflows._support_current_official_sample import use_memory_sample_login
    app,_=_app(tmp_path)
    with TestClient(app) as client:
        project=_start(client).json()['data']['project_id'];core=app.state.context
        use_memory_sample_login(core)
        assert client.post('/api/experience/official-sample/prepare').status_code!=200
        assert core.test_identities.list(project)==()
        assert client.post('/api/experience/official-sample/boundary-proposal').status_code!=200
        proposed=client.post('/api/experience/official-sample/boundary-proposal',json={'exhibition_download':True})
        assert proposed.status_code==200,proposed.text
        proposal=proposed.json()['data']['proposal']
        approved=client.post(f"/api/projects/{project}/business-boundaries/proposals/{proposal['proposal_id']}/approve",json={
            'schema_version':'1','expected_fingerprint':proposal['proposal_fingerprint'],'reason':'核对展馆权限要求'})
        assert approved.status_code==200,approved.text
        prepared=client.post('/api/experience/official-sample/prepare');assert prepared.status_code==200,prepared.text
        assert not prepared.json()['data']['scenario_prepared']
        identities=core.test_identities.list(project);assert len(identities)==2 and all(item.status.value=='PREPARED' for item in identities)
        assert not client.get(f'/api/projects/{project}/check-preview').json()['data']['can_execute']
        proofs=client.get(f'/api/projects/{project}/proof-preparation').json()['data']
        assert len(proofs['sources'])==4 and not proofs['read_scopes'] and not any(item['adopted'] for item in proofs['sources'])
        assert client.post('/api/experience/official-sample/version',json={'schema_version':'1','version':'FIXED'}).status_code!=200
        assert client.post('/api/experience/official-sample/observation',json={'schema_version':'1','available':False}).status_code!=200
        with core.uow_factory() as work:assert work.runs.list_for_project(project)==()

def test_active_check_blocks_switch_and_stop_uses_public_cancellation(tmp_path):
    from tests.backend.workflows._support_current_official_sample import prepare_sample
    app,_=_app(tmp_path)
    with TestClient(app) as client:
        core=app.state.context;project=prepare_sample(core);preview=core.checks.preview(project)
        submitted=core.checks.submit(project,expected_plan_fingerprint=preview.plan_fingerprint,idempotency_key='active-switch-guard')
        response=client.post('/api/experience/official-sample/version',json={'schema_version':'1','version':'VULNERABLE'})
        assert response.status_code!=200
        assert core.official_experience.status().scenario_version=='BASELINE'
        stopped=client.post('/api/experience/official-sample/stop');assert stopped.status_code==200,stopped.text
        assert core.check_results.status(submitted.run.run_id).job.state=='CANCELLED'
        assert not stopped.json()['data']['active']
