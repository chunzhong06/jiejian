# 普通应用整链L5：独立真实HTTP控制面与生产前端，批准不通过内部服务注入。
import json
import os
import threading
import time
from pathlib import Path
from uuid import uuid4
import pytest
import uvicorn
from playwright.sync_api import sync_playwright
from product.backend.api import create_app
from tests.fixtures.runtime.runtime_environment import runtime_identity_environment,PROJECT_ROOT
from tests.acceptance.sample_test.clients.http import ApiClient
from tests.acceptance.sample_test.current_gui import CurrentGui
from tests.acceptance.sample_test.ordinary import available_port,run_journey

pytestmark=[pytest.mark.l5,pytest.mark.browser,pytest.mark.process,pytest.mark.slow]


def _run_gui(tmp_path,*,resume=None):
    frontend=Path(os.environ['JIEJIAN_FRONTEND_DIST']).resolve()
    assert (frontend/'index.html').is_file(),'普通GUI验收需要实际生产构建'
    var=tmp_path/'var' if resume is None else resume;port=available_port();origin=f'http://127.0.0.1:{port}'
    if resume is not None:
        assert resume.is_relative_to((PROJECT_ROOT/'var/test/sample-test').resolve())
        failed=json.loads((resume/'audit/sample-test/failure.json').read_text(encoding='utf-8'))
        assert all(failed['resources'].values()),'只能接续已确认回收的隔离验收目录'
    environment=runtime_identity_environment(var,extra={key:os.environ[key] for key in ('PLAYWRIGHT_BROWSERS_PATH','JIEJIAN_NODE_EXECUTABLE') if key in os.environ})
    # 真实登录子进程与控制面使用同一生产秘密存储；仅创建并清理本次新项目的引用。
    app=create_app(var,control_origin=origin,frontend_dir=frontend,environ=environment,official_sample_root=None if resume is None else PROJECT_ROOT/'samples/web/digital_gallery')
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',access_log=False,timeout_graceful_shutdown=5))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    deadline=time.monotonic()+30
    while not server.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(.1)
    audit=PROJECT_ROOT/'var/audit/testing'/(('ordinary-' if resume is None else 'gallery-followup-')+uuid4().hex);audit.mkdir(parents=True)
    failed=False
    try:
        assert server.started,'普通应用控制面未就绪'
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1100},reduced_motion='reduce')
            page.goto(origin)
            client=ApiClient(origin);client.bind_page(page);gui=CurrentGui(page,client,audit)
            try:
                if resume is None:
                    result=run_journey(client,gui,app.state.context,tmp_path/'independent-workbench',playwright.chromium.executable_path)
                else:
                    from tests.acceptance.sample_test.gallery import resume_last_stage
                    result=resume_last_stage(client,gui,playwright.chromium.executable_path)
                    result['prior_gui_artifacts']=str(resume/'audit/sample-test')
                (audit/'report.json').write_text(json.dumps({'status':'PASSED',**result},ensure_ascii=False),encoding='utf-8')
            except Exception:
                failed=True
                gui.capture('failure-current-page')
                (audit/'report.json').write_text(json.dumps({'status':'FAILED','gui_checkpoints':gui.records},ensure_ascii=False),encoding='utf-8')
                raise
            finally:
                browser.close()
                app.state.context.identity_preparations.close()
                project=getattr(gui,'ordinary_project_id',None)
                if project:
                    for identity in app.state.context.test_identities.list(project):
                        if identity.auth_method is not None:app.state.context.test_identities.reset(identity.identity_id)
    finally:
        server.should_exit=True;thread.join(timeout=30)
        if thread.is_alive():
            # 清理失败单列，不能遮住首个业务/交互失败。
            (audit/'cleanup-error.json').write_text(json.dumps({'control_thread_exited':False}),encoding='utf-8')
            if not failed:raise AssertionError('普通应用控制面未完成清理')


@pytest.mark.skipif(os.environ.get('JIEJIAN_RUN_ORDINARY_L5')!='1',reason='普通应用GUI须显式选择')
def test_ordinary_rules_before_runtime_real_materials_changes_and_history(tmp_path):
    _run_gui(tmp_path)


@pytest.mark.skipif(not os.environ.get('JIEJIAN_GALLERY_RESUME_VAR'),reason='仅显式接续已有四轮GUI检查点')
def test_remaining_gallery_preview_from_verified_checkpoint(tmp_path):
    _run_gui(tmp_path,resume=Path(os.environ['JIEJIAN_GALLERY_RESUME_VAR']).resolve())
