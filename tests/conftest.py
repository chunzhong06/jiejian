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


@pytest.fixture(scope='session')
def readonly_official_review():
    """只读布局与菜单巡检共享业务准备；每个用例仍创建独立浏览器上下文。"""
    import json
    from pathlib import Path
    from uuid import uuid4
    from tests.support.runtime_server import launch
    from tests.support.official import OfficialScenario
    root=Path(__file__).resolve().parents[1]
    receipt=json.loads((root/'var/runtime/source/receipt.json').read_text('utf-8'))
    output=root/'var/audit/readonly-review'/uuid4().hex
    with launch(output,Path(receipt['frontend']['dist'])) as server:
        scenario=OfficialScenario(server.client)
        scenario.start()
        yield server,scenario,receipt


@pytest.fixture(scope='module')
def readonly_collaboration_review():
    """只为只读组件巡检准备同一协作任务；消费者各自拥有浏览器，不可提交业务命令。"""
    import json
    from pathlib import Path
    from time import perf_counter
    from uuid import uuid4
    from tests.support.runtime_server import launch
    from tests.support.builders.preparation.action_preparation import build_preparation_harness
    root=Path(__file__).resolve().parents[1]
    receipt=json.loads((root/'var/runtime/source/receipt.json').read_text('utf-8'))
    output=root/'var/audit/readonly-collaboration'/uuid4().hex
    seed=output/'seed';seed.mkdir(parents=True)
    started=perf_counter()
    harness=build_preparation_harness(seed)
    project,action,workspace=harness.project_id,harness.action,harness.var_dir
    try:
        with harness.core.uow_factory() as work:
            record=work.projects.get(project)
            work.projects.replace(record.model_copy(update={'name':'文档协作系统'}))
            work.commit()
    finally:harness.close()
    with launch(output/'runtime',Path(receipt['frontend']['dist']),workspace=workspace) as server:
        response=server.client.post(f'/api/projects/{project}/collaboration',json=dict(operation_id=uuid4().hex,
            goal='补齐更新文档的接口流程，整理执行步骤、结果核对与恢复安排。',purpose='SETUP',references={}))
        assert response.status_code==200,response.text
        task=response.json()['data']['task_id']
        response=server.client.post(f'/api/projects/{project}/collaboration/{task}/questions',json=dict(question_id=uuid4().hex,
            question='文档归档后还允许成员修改吗？',options=['仅负责人可以','所有成员可以']))
        assert response.status_code==200,response.text
        (output/'preparation.json').write_text(json.dumps(dict(seconds=perf_counter()-started,server_count=1,
            task_count=1,write_requests=2),indent=2),encoding='utf-8')
        yield server,project,action,task,receipt
