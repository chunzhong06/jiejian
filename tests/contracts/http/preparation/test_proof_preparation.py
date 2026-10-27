# 验证所有准备写入口先经过本机会话/同源防护，空项目读取不执行目标或生成权限事实。
import pytest
import json
import hashlib
from fastapi import FastAPI
from fastapi.testclient import TestClient as RawClient
from types import SimpleNamespace
from product.backend.interfaces.http.routers.preparation.proof_sources import build_proof_sources_router
from tests.support.builders.control_plane import TestClient, create_app, TEST_CONTROL_ORIGIN


def test_slow_source_read_does_not_block_other_api_requests():
    import anyio,httpx,time
    from product.backend.interfaces.http.routers.preparation.proof_sources import require_local_proof_session
    completed=[]
    def slow(project):
        time.sleep(.3)
        completed.append(True)
        return {'project_id':project,'sources':[]}
    app=FastAPI()
    app.include_router(build_proof_sources_router(SimpleNamespace(proof_preparation=SimpleNamespace(context=slow))))
    app.dependency_overrides[require_local_proof_session]=lambda:None
    @app.get('/ping')
    async def ping():return {'responsive':True}
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            async def read():
                result=await client.get('/api/projects/example/proof-preparation?view=sources')
                assert result.status_code==200
            async with anyio.create_task_group() as group:
                group.start_soon(read)
                await anyio.sleep(.03)
                response=await client.get('/ping')
                assert response.status_code==200 and not completed
    anyio.run(scenario)


@pytest.mark.parametrize('suffix',['sources','read-scopes','read-scopes/revoke','preflights','preflights/cancel','adoptions','suggestions','reference-inputs','reference-inputs/cancel','reference-captures','reference-captures/preview','reference-captures/cancel'])
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


def test_private_reference_transport_and_download_headers(tmp_path,monkeypatch):
    with TestClient(create_app(tmp_path/'var',start_worker=False,environ={})) as client:
        core=client.app.state.context;seen=[];raw=b'private test reference'
        monkeypatch.setattr(core.proof_artifacts,'upload',lambda project,command,content:seen.append((project,content)) or {'state':'COMPLETE'})
        monkeypatch.setattr(core.proof_artifacts,'read',lambda project,asset:raw)
        path='/api/projects/any/proof-preparation/reference-inputs'
        body={'operation_id':'1'*32,'basis_id':'pb_'+'1'*64,'action_id':'bac_'+'1'*32,'action_revision':1,
            'resource_binding_id':'res_'+'1'*32,'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'confirmed':True}
        headers={'Content-Type':'application/octet-stream','X-Jiejian-Reference':json.dumps(body)}
        response=client.post(path,content=raw,headers=headers)
        assert response.status_code==200,response.text
        assert seen==[('any',raw)]
        assert client.post(path,content=raw+b'x',headers=headers).status_code==400
        assert client.post(path,content=raw,headers={'Content-Type':'application/octet-stream','X-Jiejian-Reference':'bad'}).status_code==400
        response=client.get(path+'/pai_'+'2'*32+'/file')
        assert response.content==raw and response.headers['x-content-type-options']=='nosniff'
        assert response.headers['content-disposition'].startswith('attachment;') and response.headers['cache-control']=='no-store'
        # 同一ASGI应用只拥有一个lifespan，第二个客户端仅验证无会话读取。
        external=RawClient(client.app,base_url=TEST_CONTROL_ORIGIN)
        try:
            assert external.get(path+'/pai_'+'2'*32+'/file').status_code==403
        finally:external.close()


def test_json_capture_and_source_commands_preserve_strict_nested_types(tmp_path,monkeypatch):
    with TestClient(create_app(tmp_path/'var',start_worker=False,environ={})) as client:
        core=client.app.state.context;seen=[]
        claim=dict(identity_id='tid_'+'1'*32,application_subject_id='owner',application_role='owner',
            request_path='/session/current',subject_path=['id'],role_path=['role'])
        selection=dict(basis_id='pb_'+'1'*64,action_id='bac_'+'1'*32,action_revision=1,
            allow_intent_id='pin_'+'1'*32,resource_binding_id='res_'+'1'*32,collection='tickets',identity_claims=[claim])
        monkeypatch.setattr(core.reference_captures,'preview',lambda project,body:
            seen.append(body) or SimpleNamespace(model_dump=lambda **kwargs:{'plan_hash':'2'*64}))
        monkeypatch.setattr(core.reference_captures,'start',lambda project,body:seen.append(body) or {'state':'PENDING'})
        monkeypatch.setattr(core.proof_preparation,'save',lambda project,body:seen.append(body) or {'state':'CANDIDATE'})
        prefix='/api/projects/any/proof-preparation'
        response=client.post(prefix+'/reference-captures/preview',json=selection)
        assert response.status_code==200,response.text
        assert response.json()['data']=={'plan_hash':'2'*64}
        assert seen[-1].identity_claims[0].subject_path==('id',)
        start=dict(operation_id='1'*32,basis_id=selection['basis_id'],selection=selection,plan_hash='2'*64,plan_created_at_us=1,confirmed=True)
        assert client.post(prefix+'/reference-captures',json=start).status_code==200
        config=dict(action_id=selection['action_id'],action_revision=1,effect_id='bef_'+'1'*32,
            source_kind='REFERENCE_FILE',observation_identity_id=claim['identity_id'],resource_binding_id=selection['resource_binding_id'],
            collection='tickets',relative_path_template='/collections/tickets/{resource_id}',identity_claims=[claim],
            mappings={'resource_id':['resource_id'],'owner_id':['owner_id']},reference_resource_id='ticket-a',reference_owner_identity_id=claim['identity_id'])
        saved=client.post(prefix+'/sources',json=dict(operation_id='2'*32,basis_id=selection['basis_id'],config=config))
        assert saved.status_code==200,saved.text
        assert seen[-1].config.mappings['resource_id']==('resource_id',)
        for invalid in ({**selection,'action_revision':'1'}, {**selection,'identity_claims':[{**claim,'subject_path':['token']}]}, {**selection,'script':'anything'}):
            assert client.post(prefix+'/reference-captures/preview',json=invalid).status_code==422
        assert len(seen)==3

pytestmark = [pytest.mark.level3]
