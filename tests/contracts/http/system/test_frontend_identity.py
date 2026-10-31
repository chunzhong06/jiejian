# 核对实际服务目录的构建身份与HTML缓存策略，不依赖环境中的旧前端路径。

import pytest
import hashlib
import json

from tests.support.builders.control_plane import TestClient, create_app


def test_system_identity_matches_served_frontend_and_html_revalidates(tmp_path):
    frontend=tmp_path/'frontend';frontend.mkdir();(frontend/'assets').mkdir()
    content={'index.html':'<html>ready</html>','assets/index-12345678.js':'console.log("app")'}
    for name,text in content.items():(frontend/name).write_text(text,encoding='utf8')
    (frontend/'frontend-manifest.json').write_text(json.dumps({'schema_version':'1','build_id':'b'*64,
        'assets':[{'path':name,'sha256':hashlib.sha256(text.encode()).hexdigest()} for name,text in content.items()]}),encoding='utf8')
    with TestClient(create_app(tmp_path/'var',start_worker=False,environ={},frontend_dir=frontend)) as client:
        identity=client.get('/api/system/status').json()['data']['frontend_identity']
        assert identity['status']=='CONFIRMED' and identity['build_id']=='b'*64
        assert client.get('/').headers['cache-control']=='no-cache'
        assert client.get('/frontend-manifest.json').headers['cache-control']=='no-cache'
        assert 'immutable' in client.get('/assets/index-12345678.js').headers['cache-control']
        (frontend/'index.html').write_text('replaced',encoding='utf8')
        assert client.get('/api/system/status').json()['data']['frontend_identity']['status']=='UNCONFIRMED'

def test_light_status_and_update_routes_keep_the_local_control_boundary(tmp_path):
    with TestClient(create_app(tmp_path/'var', start_worker=False, environ={})) as client:
        summary = client.get('/api/system/summary').json()['data']
        assert summary['api'] == 'available' and 'environment' not in summary
        assert client.post('/api/system/updates/preview', json={'directory': str(tmp_path)},
                           headers={'Origin': 'https://external.example'}).status_code == 403
        response = client.post('/api/system/updates/preview', json={'directory': str(tmp_path)})
        assert response.status_code == 400
        assert response.json()['error']['code'] == 'INPUT_INVALID'
        assert client.get('/api/system/updates/upd_' + 'a'*32).status_code == 400


pytestmark = [pytest.mark.level3]
