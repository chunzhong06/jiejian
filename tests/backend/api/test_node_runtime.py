# 普通应用预览不执行；显式启动后真实Worker形成回执，响应丢失与重开不重复启动。
import socket
import time
from uuid import uuid4

from tests.fixtures.control_plane import TestClient, create_app
from tests.fixtures.runtime_environment import runtime_identity_environment


def _connect(client, source):
    source.mkdir()
    (source/'app.mjs').write_text("import http from 'node:http'; http.createServer((q,r)=>r.end('hello')).listen(Number(process.env.PORT),'127.0.0.1');",encoding='utf-8')
    response=client.post('/api/applications/connect',json={'schema_version':'1','source_root':str(source)})
    assert response.status_code==201,response.text
    return response.json()['data']['understanding']


def _preview(client, record, **extra):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    body={'entry':'app.mjs','port':port,'revision':record['revision'],'consent_source_read':True}|extra
    return client.post(f"/api/projects/{record['project_id']}/controlled-runtime/preview",json=body)


def test_preview_requires_consent_detects_drift_and_never_starts(tmp_path):
    var=tmp_path/'var'
    app=create_app(var,start_worker=False,environ=runtime_identity_environment(var))
    with TestClient(app) as client:
        record=_connect(client,tmp_path/'source');prefix=f"/api/projects/{record['project_id']}/controlled-runtime"
        assert _preview(client,record,consent_source_read=False).status_code==409
        denied=client.put(f"/api/projects/{record['project_id']}/source-analysis-authorization",json={'schema_version':'1','revision':record['revision']})
        assert denied.status_code>=400
        response=_preview(client,record);assert response.status_code==200,response.text
        preview=response.json()['data']
        assert client.get(prefix).json()['data']['operation'] is None
        assert not (var/'runtime/node-artifacts').exists()
        payload={key:preview[key] for key in ('entry','port','revision','preview_fingerprint')}
        payload.update(operation_id=uuid4().hex,consent_execute=True)
        (tmp_path/'source/app.mjs').write_text('export const changed=true;',encoding='utf-8')
        assert client.post(prefix+'/start',json=payload).status_code==409
        assert client.get(prefix).json()['data']['operation'] is None


def test_api_load_receipt_survives_stop_and_reopen_without_reexecution(tmp_path):
    var=tmp_path/'var';environment=runtime_identity_environment(var)
    app=create_app(var,start_worker=False,environ=environment)
    with TestClient(app) as client:
        record=_connect(client,tmp_path/'source');prefix=f"/api/projects/{record['project_id']}/controlled-runtime"
        response=_preview(client,record);assert response.status_code==200,response.text
        preview=response.json()['data']
        payload={key:preview[key] for key in ('entry','port','revision','preview_fingerprint')}
        payload.update(operation_id=uuid4().hex,consent_execute=True)
        denied=client.post(prefix+'/start',json=payload|{'consent_execute':False});assert denied.status_code==409
        started=client.post(prefix+'/start',json=payload);assert started.status_code==202,started.text
        operation=started.json()['data']
        assert client.post(prefix+'/start',json=payload).json()['data']==operation
        app.state.context.runtime_worker.start()
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            current=client.get(prefix).json()['data']
            if current['operation']['state'] in {'SUCCEEDED','FAILED','CANCELLED'}:break
            time.sleep(.1)
        assert current['operation']['state']=='SUCCEEDED',current
        assert current['running'] and current['source_matches']
        receipt=current['operation']['receipt']
        stopped=client.post(prefix+'/stop',json={'instance_id':operation['instance_id']})
        assert stopped.status_code==200,stopped.text
        assert not stopped.json()['data']['running']
        assert stopped.json()['data']['operation']['receipt']==receipt
    with TestClient(create_app(var,start_worker=False,environ=environment)) as restored:
        state=restored.get(prefix).json()['data']
        assert not state['running']
        assert state['operation']['receipt']==receipt
        replay=restored.post(prefix+'/start',json=payload).json()['data']
        assert replay['instance_id']==operation['instance_id']
        assert not restored.get(prefix).json()['data']['running']


def test_cancel_queued_load_is_idempotent_and_does_not_touch_another_project(tmp_path):
    var=tmp_path/'var'
    with TestClient(create_app(var,start_worker=False,environ=runtime_identity_environment(var))) as client:
        record=_connect(client,tmp_path/'source')
        project=record['project_id'];prefix=f'/api/projects/{project}/controlled-runtime'
        preview=_preview(client,record).json()['data']
        payload={key:preview[key] for key in ('entry','port','revision','preview_fingerprint')}
        payload.update(operation_id=uuid4().hex,consent_execute=True)
        started=client.post(prefix+'/start',json=payload);assert started.status_code==202,started.text
        other=_connect(client,tmp_path/'other')
        assert client.post(f"/api/projects/{other['project_id']}/controlled-runtime/operations/{payload['operation_id']}/cancel").status_code==409
        route=prefix+'/operations/'+payload['operation_id']+'/cancel'
        cancelled=client.post(route);assert cancelled.status_code==200,cancelled.text
        assert cancelled.json()['data']['state']=='CANCELLED'
        assert client.post(route).json()['data']==cancelled.json()['data']
        assert not client.get(prefix).json()['data']['running']
