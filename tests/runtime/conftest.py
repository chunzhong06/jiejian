# 高等级验收只在显式环境中使用独立实例，浏览器与服务各自负责释放。
import json
import os
from pathlib import Path
from uuid import uuid4
import pytest

@pytest.fixture
def runtime_server():
    if os.environ.get('JIEJIAN_RUNTIME_ACCEPTANCE')!='1':pytest.skip('通过 sample-test 显式运行独立官方场景')
    from tests.support.runtime_server import launch
    output=Path(os.environ['JIEJIAN_ACCEPTANCE_OUTPUT'])/('scenario-'+uuid4().hex)
    with launch(output,Path(os.environ['JIEJIAN_FRONTEND_DIST'])) as server:
        yield server

@pytest.fixture
def official(runtime_server):
    from tests.support.official import OfficialScenario
    scenario=OfficialScenario(runtime_server.client)
    try:
        scenario.start()
        yield scenario
    finally:
        summary={'schema_version':'1','project_id':scenario.project_id,'stages':scenario.stages,'operations':scenario.operations}
        (runtime_server.output/'scenario.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')

@pytest.fixture
def browser_page(runtime_server):
    from playwright.sync_api import sync_playwright
    errors=[]
    with sync_playwright() as engine:
        browser=engine.chromium.launch(executable_path=os.environ['JIEJIAN_PLAYWRIGHT_EXECUTABLE'],headless=True)
        try:
            context=browser.new_context(viewport={'width':1512,'height':980},device_scale_factor=1)
            page=context.new_page()
            page.set_default_timeout(30000)
            page.on('pageerror',lambda error:errors.append(type(error).__name__))
            yield page
            assert errors==[],'浏览器出现脚本错误'
        finally:
            browser.close()
            (runtime_server.output/'browser.json').write_text(json.dumps({'schema_version':'1','page_errors':errors}),encoding='utf-8')
