# 验证本地会话、Host、Origin、严格输入和错误回执，不执行任何目标操作。
import pytest


def test_explicit_body_budget_stops_at_overflow_without_reading_remaining_chunks():
    import asyncio
    from starlette.requests import Request
    from product.backend.domain.errors import JiejianError
    from product.backend.interfaces.http.body import read_bounded_body

    async def scenario():
        chunks=iter([b'ab',b'cde',b'never-read'])
        consumed=[]
        async def receive():
            value=next(chunks);consumed.append(value)
            return {'type':'http.request','body':value,'more_body':True}
        request=Request({'type':'http','headers':[(b'content-length',b'1')]},receive)
        with pytest.raises(JiejianError) as failure:
            await read_bounded_body(request,limit=4,message='保持原错误提示')
        assert failure.value.code=='INPUT_INVALID'
        assert consumed==[b'ab',b'cde']
    asyncio.run(scenario())


def test_body_budget_accepts_exact_limit_and_disconnect_never_returns_partial_input():
    import asyncio
    from starlette.requests import ClientDisconnect,Request
    from product.backend.interfaces.http.body import read_bounded_body

    async def scenario():
        async def complete():return {'type':'http.request','body':b'abcd','more_body':False}
        assert await read_bounded_body(Request({'type':'http'},complete),limit=4,message='large')==b'abcd'
        messages=iter([{'type':'http.request','body':b'ab','more_body':True},{'type':'http.disconnect'}])
        async def interrupted():return next(messages)
        with pytest.raises(ClientDisconnect):
            await read_bounded_body(Request({'type':'http'},interrupted),limit=4,message='large')
    asyncio.run(scenario())


@pytest.mark.parametrize('operation',['environment','authentication','candidate','flow','scenario','openapi-context','openapi-parse'])
def test_slow_configuration_operations_leave_other_requests_responsive(operation):
    import asyncio,json
    from threading import Event,get_ident
    from types import SimpleNamespace
    import httpx
    from fastapi import FastAPI
    from product.backend.interfaces.http.routers.applications.workbench import build_workbench_router
    from product.backend.interfaces.http.routers.preparation.preparation import build_preparation_router
    from product.backend.interfaces.http.routers.preparation.test_identities import build_test_identities_router
    from product.protocols.preparation.operation_flow import operation_resource_injection
    from product.protocols.web.workflow import HttpWorkflowBinding

    target=dict(base_url='http://127.0.0.1:18080',allowed_origins=['http://127.0.0.1:18080'],allowed_hosts=['127.0.0.1'],allowed_ports=[18080],allow_private_network=True)
    identity='tid_'+'1'*32
    step=dict(id='read',purpose='TARGET',identity_id='CASE_SUBJECT',request_template=dict(method='GET',path='/items/{case_resource_id}',input_slots=[dict(slot_id='case_resource_id',source='CASE_RESOURCE_ID',consumer='PATH')]),classifier=dict(accepted=[dict(kind='STATUS_IN',statuses=[200])],denied=[dict(kind='STATUS_IN',statuses=[403])]),depends_on_step_ids=[])
    draft=dict(id='ofl_'+'1'*32,revision=1,business_action_id='bac_'+'1'*32,action_revision=1,subject_test_identity_id=identity,resource_owner_test_identity_id=identity,source_fingerprint='a'*64,actual_resource_id='item-1',target_step_id='read',steps=[step])
    workflow=HttpWorkflowBinding.model_validate_json(json.dumps(dict(workflow_id='workflow',source_flow_id=draft['id'],action_id=draft['business_action_id'],target_step_id='read',steps=[step])))
    flow={key:value for key,value in draft.items() if key not in {'steps','target_step_id'}}|dict(project_id='example',provenance='MANUAL',target_scope=target,workflow=workflow.model_dump(mode='json'),resource_injection=operation_resource_injection(workflow).model_dump(mode='json'))
    scenario=dict(id='bsc_'+'1'*32,project_id='example',revision=1,label='业务场景',experiments=[dict(id='normal',label='正常对照',kind='NORMAL',invocations=[dict(id='read',label='读取',items=[dict(id='item',permission=dict(intent_id='pin_'+'1'*32,revision=1,intent_hash='a'*64),resource_id='item-1')])])])
    auth=dict(schema_version='1',expected_updated_at_us=0,profile=dict(verification=dict(path='/me',subject_path=['id'],role_path=['role'],expected_subject='owner',expected_role='owner')))
    endpoint,body={
        'environment':('/api/projects/example/environments',dict(configuration=dict(environment_id='env_'+'1'*32,revision=1,name='环境',target=target),expected_revision=0)),
        'authentication':('/api/test-identities/'+identity+'/authentication',auth),
        'candidate':('/api/projects/example/operation-flows/candidate',draft),
        'flow':('/api/projects/example/operation-flows',flow),
        'scenario':('/api/projects/example/business-scenarios',scenario),
        'openapi-context':('/api/projects/example/operation-flows/openapi',{}),
        'openapi-parse':('/api/projects/example/operation-flows/openapi',{}),
    }[operation]
    entered,release=Event(),Event()
    threads=[]
    def slow(*args,**kwargs):
        threads.append(get_ident());entered.set()
        assert release.wait(3),'configuration work blocked the event loop'
        return args[-1] if operation in {'candidate','flow','scenario','authentication'} else {}
    flows=SimpleNamespace(candidate=slow,save=slow,context=slow if operation=='openapi-context' else lambda _: {},openapi_candidates=slow if operation=='openapi-parse' else lambda _: {})
    context=SimpleNamespace(operation_flows=flows,proof_preparation=SimpleNamespace(),business_scenarios=SimpleNamespace(save=slow),application_environments=SimpleNamespace(save=slow),test_identities=SimpleNamespace(configure_authentication=slow))
    app=FastAPI();app.include_router(build_workbench_router(context));app.include_router(build_preparation_router(context));app.include_router(build_test_identities_router(context))
    @app.get('/ping')
    async def ping():return {'responsive':True}
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            method='POST' if operation in {'environment','candidate','openapi-context','openapi-parse'} else 'PUT'
            pending=asyncio.create_task(client.request(method,endpoint,json=body))
            try:
                assert await asyncio.to_thread(entered.wait,2)
                response=await asyncio.wait_for(client.get('/ping'),1)
                assert response.json()=={'responsive':True} and not pending.done()
                assert threads and all(thread!=get_ident() for thread in threads)
            finally:
                release.set()
                result=await pending
            assert result.status_code==200,result.text
    asyncio.run(run())


def test_slow_project_read_does_not_block_the_event_loop():
    import asyncio
    from threading import Event
    from types import SimpleNamespace
    import httpx
    from fastapi import FastAPI
    from product.backend.interfaces.http.routers.applications.projects import build_projects_router

    entered, release = Event(), Event()
    def slow_read(**kwargs):
        entered.set()
        assert release.wait(5)
        return []

    async def run():
        app = FastAPI()
        app.include_router(build_projects_router(SimpleNamespace(projects=SimpleNamespace(list_for_display=slow_read))))
        @app.get('/health')
        async def health():
            return {'ready': True}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            reading = asyncio.create_task(client.get('/api/projects'))
            try:
                assert await asyncio.to_thread(entered.wait, 3)
                response = await client.get('/health')
                assert response.json() == {'ready': True}
                assert not reading.done()
            finally:
                release.set()
                await reading
    asyncio.run(run())

def authorize(api):
    response=api.client.get('/')
    assert response.status_code==200
    cookie=response.headers.get('set-cookie','').casefold()
    assert 'httponly' in cookie and 'samesite=strict' in cookie

def test_api_requires_a_browser_session(api):
    assert api.client.get('/api/projects').status_code==403
    authorize(api)
    response=api.client.get('/api/projects')
    assert response.status_code==200
    assert response.json()=={'schema_version':'1','data':[]}

def test_host_is_checked_even_with_a_valid_session(api):
    authorize(api)
    assert api.client.get('/api/projects',headers={'host':'example.invalid'}).status_code==403

@pytest.mark.parametrize('origin',[None,'https://example.invalid','http://127.0.0.1:18772'])
def test_mutations_reject_missing_or_foreign_origin(api,origin):
    authorize(api)
    headers={'origin':origin} if origin else {}
    response=api.client.post('/api/applications/connect',headers=headers,json={})
    assert response.status_code==403

def test_authenticated_invalid_input_has_a_structured_error(api):
    authorize(api)
    response=api.client.post('/api/applications/connect',headers={'origin':api.origin},json={})
    assert response.status_code==422
    value=response.json()
    assert value['schema_version']=='1' and value['error']['code']

def test_connect_is_visible_through_the_same_control_plane(api,source):
    authorize(api)
    headers={'origin':api.origin}
    first=api.client.post('/api/applications/connect',headers=headers,json={'schema_version':'1','source_root':str(source),'project_name':'本地展馆'})
    assert first.status_code==201
    second=api.client.post('/api/applications/connect',headers=headers,json={'schema_version':'1','source_root':str(source)})
    assert second.status_code==201
    projects=api.client.get('/api/projects').json()['data']
    assert len(projects)==1 and projects[0]['name']=='本地展馆'

def test_unknown_project_does_not_fall_back_to_another_project(api):
    authorize(api)
    response=api.client.get('/api/projects/app_'+'0'*32)
    assert response.status_code==404
    assert 'error' in response.json() and 'data' not in response.json()
