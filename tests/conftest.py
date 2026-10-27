# 提供独立数据库、内存秘密及显式本地目标；真实进程场景按等级启用。
import pytest
import os
from secrets import token_urlsafe
from threading import Thread
from types import SimpleNamespace

def pytest_addoption(parser):
    parser.addoption('--run-level4',action='store_true',help='显式执行本地进程与真实目标场景')

def pytest_runtest_setup(item):
    if item.get_closest_marker('level4') and not item.config.getoption('--run-level4'):
        pytest.skip('真实流程需要显式 --run-level4；普通验证只收集不启动')

@pytest.fixture
def isolated_environment(monkeypatch,tmp_path):
    for name in tuple(os.environ):
        if name.startswith('JIEJIAN_'):monkeypatch.delenv(name,raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path

@pytest.fixture
def web_test_target_factory(request):
    from tests.support.builders.web_test_target import create_web_test_target
    running=[]
    def start(*,fail_cleanup=False,echo_identity=None,request_delay_seconds=0.0):
        tokens={name:f'{name}-{token_urlsafe(18)}' for name in ('member','reader')}
        observer=token_urlsafe(18)
        passwords={name:token_urlsafe(18) for name in tokens}
        sessions={name:token_urlsafe(18) for name in tokens}
        server=create_web_test_target(tokens=tokens,observer_token=observer,passwords=passwords,sessions=sessions,
            fail_cleanup=fail_cleanup,echo_secret=tokens.get(echo_identity) if echo_identity else None,request_delay_seconds=request_delay_seconds)
        thread=Thread(target=server.serve_forever,daemon=True)
        thread.start();running.append((server,thread))
        return SimpleNamespace(server=server,port=server.server_port,tokens=tokens,passwords=passwords,environ={
            'JIEJIAN_WEB_TEST_MEMBER_TOKEN':tokens['member'],'JIEJIAN_WEB_TEST_READER_TOKEN':tokens['reader'],'JIEJIAN_WEB_TEST_OBSERVER_TOKEN':observer})
    def stop():
        for server,thread in running:
            server.shutdown();server.server_close();thread.join(timeout=5)
            assert not thread.is_alive(),'本用例的本地目标未停止'
    request.addfinalizer(stop)
    return start

@pytest.fixture
def core(tmp_path):
    from product.backend.bootstrap.application import ApplicationCore
    from tests.support.secrets import MemorySecrets
    application=ApplicationCore(tmp_path/'instance',secret_store=MemorySecrets())
    try:yield application
    finally:application.close()

@pytest.fixture
def source(tmp_path):
    folder=tmp_path/'application'
    folder.mkdir()
    (folder/'package.json').write_text('{"name":"local-fixture","scripts":{"start":"node server.mjs"}}',encoding='utf-8')
    (folder/'server.mjs').write_text('export const name = "local fixture";\n',encoding='utf-8')
    return folder
