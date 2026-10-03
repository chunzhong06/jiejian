# 核对实际服务目录的构建身份与HTML缓存策略，不依赖环境中的旧前端路径。
import hashlib
import json

from tests.fixtures.control_plane import TestClient, create_app


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
