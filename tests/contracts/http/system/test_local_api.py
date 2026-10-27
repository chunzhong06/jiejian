# 验证本地会话、Host、Origin、严格输入和错误回执，不执行任何目标操作。
import pytest

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
