"""从空工作区经人工确认到真实起点结果；截图记录正式界面而非模拟数据。"""
import json
import pytest
from playwright.sync_api import expect
from tests.support.browser_review import navigate, settled, report_ready
from tests.support.official import OfficialScenario, until

pytestmark=[pytest.mark.runtime,pytest.mark.baseline]


def test_official_example_explains_requirements_and_connects_the_baseline(runtime_server,browser_page):
    server,page=runtime_server,browser_page
    captures=[]
    def capture(name):
        settled(page)
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
        page.screenshot(path=str(server.output/(name+'.png')),full_page=True)
        captures.append(name+'.png')

    def variants(name):
        capture(name+'-light')
        page.get_by_role('button',name='切换深色',exact=True).click()
        expect(page.locator('html')).to_have_attribute('data-studio-theme','dark')
        capture(name+'-dark')
        page.set_viewport_size({'width':760,'height':980})
        capture(name+'-narrow')
        page.set_viewport_size({'width':1512,'height':980})
        page.get_by_role('button',name='切换浅色',exact=True).click()
        expect(page.locator('html')).to_have_attribute('data-studio-theme','light')

    page.goto(server.origin)
    expect(page.get_by_role('heading',name='请求被拒绝，就没有越权吗？')).to_be_visible()
    variants('welcome')
    page.get_by_role('link',name='体验官方示例',exact=True).click()
    expect(page.get_by_role('heading',name='官方示例',exact=True)).to_be_visible()
    variants('example')
    page.get_by_role('button',name='开始示例体验',exact=True).click()
    expect(page.get_by_role('heading',name='先确认谁能访问哪份资料',exact=True)).to_be_visible(timeout=90000)
    project=server.client.get('/api/experience/official-sample?lightweight=true').json()['data']['project_id']
    variants('current-task')
    page.get_by_role('link',name='确认访问要求',exact=True).click()
    expect(page.get_by_role('table',name='示例权限要求')).to_be_visible()
    variants('rules')
    page.get_by_role('button',name='批准规则并继续',exact=True).click()
    expect(page.get_by_role('heading',name='示例规则已确认',exact=True)).to_be_visible()
    page.get_by_role('link',name='准备示例材料',exact=True).click()
    expect(page.get_by_text('确认后开始准备',exact=True)).to_be_visible()
    variants('preparation-preview')
    page.get_by_role('checkbox',name='允许上述操作、来源读取及材料采用',exact=True).check()
    page.get_by_role('button',name='允许并开始准备',exact=True).click()
    scenario=OfficialScenario(server.client)
    scenario.project_id=project
    until(lambda:scenario.request('GET',f'/api/projects/{project}/preparation'),lambda value:value['preparation_complete'],seconds=120)
    preview=scenario.request('GET',f'/api/projects/{project}/check-preview')
    assert preview['can_execute']
    navigate(page,server.origin,f'/reports?view=plan&project_id={project}')
    page.get_by_role('button',name='预览这次检查',exact=True).click()
    expect(page.get_by_role('heading',name='确认这次检查',exact=True)).to_be_visible()
    variants('execution-preview')
    page.get_by_role('button',name='开始检查',exact=True).click()
    page.wait_for_function("new URLSearchParams(location.hash.split('?')[1]??'').has('run_id')")
    run_id=page.evaluate("new URLSearchParams(location.hash.split('?')[1]).get('run_id')")
    status=until(lambda:scenario.request('GET',f'/api/runs/{run_id}'),lambda value:value['run']['lifecycle'] not in {'QUEUED','RUNNING'},seconds=120)
    assert status['result_integrity']=='VALID' and status['run']['verdict']=='PASS'
    navigate(page,server.origin,f'/reports?project_id={project}&run_id={run_id}')
    report_ready(page)
    expect(page.get_by_role('link',name='查看错误修改',exact=True)).to_be_visible()
    variants('baseline-result')
    page.get_by_role('button',name='切换深色',exact=True).click()
    expect(page.locator('html')).to_have_attribute('data-studio-theme','dark')
    navigate(page,server.origin,f'/workspace?project_id={project}')
    expect(page.get_by_role('heading',name='正常起点已形成，接着看一次错误修改',exact=True)).to_be_visible()
    capture('baseline-task-dark')
    page.get_by_role('link',name='查看错误修改',exact=True).click()
    expect(page.get_by_role('button',name='加载这次错误修改',exact=True)).to_be_visible()
    # 阅读下一步不加载源码；正式转换仍须独立确认及服务端前置检查。
    journey=scenario.request('GET','/api/experience/official-sample/development')
    assert journey['implementation']=='BASELINE' and journey['stage']=='BASELINE_RESULT' and journey['run_id']==run_id
    capture('next-change-dark')
    (server.output/'journey.json').write_text(json.dumps(dict(project_id=project,run_id=run_id,verdict=status['run']['verdict'],stage=journey['stage'],captures=captures),ensure_ascii=False,indent=2),encoding='utf-8')
