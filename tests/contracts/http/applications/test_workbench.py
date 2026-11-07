"""真实 HTTP JSON 边界保留严格协议，导入回执只包含净化结构。"""
import json
from uuid import uuid4
from tests.support.builders.control_plane import TestClient, create_app


def test_source_free_environment_and_import_round_trip(tmp_path):
    app = create_app(tmp_path / 'instance', start_worker=False)
    with TestClient(app) as client:
        created = client.post('/api/applications', json={'operation_id':uuid4().hex, 'name':'业务系统'})
        assert created.status_code == 201, created.text
        project = created.json()['data']['project_id']
        root = '/api/projects/' + project
        environment = dict(environment_id='env_' + uuid4().hex, revision=1, name='本地测试',
            target=dict(base_url='http://127.0.0.1:18081', allowed_origins=['http://127.0.0.1:18081'],
                allowed_hosts=['127.0.0.1'], allowed_ports=[18081], allow_private_network=True))
        saved = client.post(root + '/environments', json={'configuration':environment, 'expected_revision':0})
        assert saved.status_code == 200, saved.text
        active = client.post(root + '/environments/' + environment['environment_id'] + '/activate',
            json={'revision':1,'expected_revision':0})
        assert active.status_code == 200, active.text
        assert active.json()['data']['source_root'] is None
        assert active.json()['data']['environment']['deployment_verification'] == 'UNVERIFIED'
        secret = 'not-for-source-assets'
        raw = json.dumps({'log':{'entries':[{'request':{'method':'GET','url':'http://127.0.0.1/orders?token='+secret},
            'response':{'content':{'text':secret}}}]}})
        preview = client.post(root + '/api-sources/preview', json={'kind':'HAR','raw':raw})
        assert preview.status_code == 200, preview.text
        candidate = preview.json()['data']
        assert secret not in preview.text
        accepted = client.post(root + '/api-sources/accept',json=dict(candidate_id=candidate['candidate_id'],
            source_id='src_'+uuid4().hex,name='已授权流量',expected_revision=0,expected_fingerprint=candidate['fingerprint']))
        assert accepted.status_code == 200, accepted.text
        assert secret not in client.get(root+'/api-sources').text
        source_id=accepted.json()['data']['source_id']
        second=client.post(root+'/api-sources/accept',json=dict(candidate_id=candidate['candidate_id'],
            source_id='src_'+uuid4().hex,name='第二份资料',expected_revision=0,expected_fingerprint=candidate['fingerprint']))
        assert second.status_code==200
        summary=client.get(root+'/api-sources/summary')
        assert summary.status_code==200,summary.text
        assert summary.json()['data']==dict(project_id=project,source_count=2,request_count=2)
        assert len(summary.content)<len(client.get(root+'/api-sources').content)
        filtered=client.get(root+'/api-sources',params={'source_id':source_id}).json()['data']
        assert [item['source_id'] for item in filtered['sources']]==[source_id]
        assert all(item['source_id']==source_id for item in filtered['request_references'])
        other=client.post('/api/applications',json={'operation_id':uuid4().hex,'name':'其他应用'}).json()['data']['project_id']
        assert client.get('/api/projects/'+other+'/api-sources',params={'source_id':source_id}).json()['data']['sources']==[]
        assert client.get('/api/projects/'+other+'/api-sources/summary').json()['data']==dict(project_id=other,source_count=0,request_count=0)
        assert client.get(root+'/api-sources',params={'source_id':'invalid'}).status_code==422



def test_workbench_projection_contracts_are_precise_and_keep_wire_bytes(tmp_path):
    import pytest
    from pydantic import ValidationError
    from product.backend.interfaces.http.envelope import data_response
    from product.backend.interfaces.http.routers.preparation.projections import OperationContextProjection
    app = create_app(tmp_path/'instance', start_worker=False)
    with TestClient(app) as client:
        project=client.post('/api/applications',json=dict(operation_id=uuid4().hex,name='合同核对')).json()['data']['project_id']
        payload=app.state.context.operation_flows.context(project)
        response=client.get(f'/api/projects/{project}/operation-flows')
        assert response.status_code==200 and response.content==data_response(payload).body
        assert response.json()['data']==dict(project_id=project,source_fingerprint=None,endpoint=None,recordings=[],actions=[],flows=[])
        with pytest.raises(ValidationError):
            data_response({**payload,'unregistered':True},projection=OperationContextProjection)
        schema=app.openapi()
        for path,name in [('/api/projects/{project_id}/operation-flows','OperationContextProjection'),
            ('/api/projects/{project_id}/proof-preparation/sources/{source_id}/adoption-preview','ProofAdoptionProjection')]:
            reference=schema['paths'][path]['get']['responses']['200']['content']['application/json']['schema']['$ref'].split('/')[-1]
            data=schema['components']['schemas'][reference]['properties']['data']
            assert data['$ref'].endswith('/'+name)
        nested=schema['components']['schemas']['FlowRevisionProjection']['properties']['document']
        assert nested['$ref'].endswith('/OperationFlow')
