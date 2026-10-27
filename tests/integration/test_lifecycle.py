# 即使部分启动或关闭失败，生命周期仍释放其他已建立资源。
from types import SimpleNamespace
from contextlib import asynccontextmanager
import pytest
from fastapi.testclient import TestClient
from product.backend.interfaces.http.app import create_app
from tests.support.secrets import MemorySecrets

def instrument(tmp_path,monkeypatch,*,startup_failure=False,shutdown_failure=False):
    calls=[]
    app=create_app(tmp_path/'instance',control_origin='http://127.0.0.1:18771',secret_store=MemorySecrets())
    core=app.state.context
    original_close=core.close
    worker=core.worker
    runtime=core.runtime_worker
    example=core.official_experience
    def start():
        calls.append('start')
        if startup_failure:raise RuntimeError('startup fixture')
    def stop():
        calls.append('worker')
        if shutdown_failure:raise RuntimeError('shutdown fixture')
    @asynccontextmanager
    async def session():
        calls.append('session-enter')
        try:yield
        finally:calls.append('session-exit')
    monkeypatch.setattr(app.state.mcp_server.session_manager,'run',session)
    monkeypatch.setattr(core,'worker',SimpleNamespace(start=start,stop=stop))
    monkeypatch.setattr(core,'runtime_worker',SimpleNamespace(start=lambda:calls.append('runtime-start'),stop=lambda:calls.append('runtime')))
    monkeypatch.setattr(core,'official_experience',SimpleNamespace(close=lambda:calls.append('example')))
    monkeypatch.setattr(core,'close',lambda:calls.append('close'))
    def release():
        core.worker=worker
        core.runtime_worker=runtime
        core.official_experience=example
        original_close()
    return app,calls,release

def test_start_failure_releases_established_resources(tmp_path,monkeypatch):
    app,calls,release=instrument(tmp_path,monkeypatch,startup_failure=True)
    try:
        with pytest.raises(RuntimeError,match='startup fixture'):
            with TestClient(app):pass
        assert set(calls)=={'session-enter','start','worker','example','runtime','session-exit','close'}
        assert len(calls)==len(set(calls))
        assert calls.index('session-enter')<calls.index('start')<calls.index('worker')
        assert calls[-1]=='close'
    finally:release()

def test_shutdown_failure_does_not_skip_remaining_cleanup(tmp_path,monkeypatch):
    app,calls,release=instrument(tmp_path,monkeypatch,shutdown_failure=True)
    try:
        with pytest.raises(RuntimeError,match='shutdown fixture'):
            with TestClient(app):pass
        assert {'worker','example','runtime','session-exit','close'}<=set(calls)
        assert all(calls.count(name)==1 for name in ['worker','example','runtime','session-exit','close'])
        assert calls[-1]=='close'
    finally:release()
