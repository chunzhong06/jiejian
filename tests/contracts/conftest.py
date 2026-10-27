# 本地 API 契约使用内存秘密与独立数据库，不启动执行 Worker。
from types import SimpleNamespace
import pytest

@pytest.fixture
def api(tmp_path):
    from fastapi.testclient import TestClient
    from product.backend.interfaces.http.app import create_app
    from tests.support.secrets import MemorySecrets
    frontend=tmp_path/'frontend'
    frontend.mkdir()
    (frontend/'index.html').write_text('<!doctype html><title>界鉴</title>',encoding='utf-8')
    origin='http://127.0.0.1:18771'
    app=create_app(tmp_path/'http-instance',control_origin=origin,frontend_dir=frontend,start_worker=False,secret_store=MemorySecrets())
    with TestClient(app,base_url=origin) as client:
        yield SimpleNamespace(client=client,app=app,origin=origin)
