"""第三批真实修改与两种越权后果；其余工作面只读巡检，不新增模型或目标范围。"""
import json
from urllib.parse import urlencode
import pytest
from playwright.sync_api import expect
from tests.support.official import OfficialScenario,until
from tests.support.browser_review import navigate,settled,report_ready

pytestmark=[pytest.mark.runtime,pytest.mark.baseline]


def test_named_changes_and_published_business_effects(runtime_server,browser_page):
    server,page=runtime_server,browser_page
    scenario=OfficialScenario(server.client)
    scenario.start()
    initial=scenario.check('BASELINE')
    assert initial.story['verdict']=='PASS'
    project=scenario.project_id
    captures=[]

    def route(path):
        navigate(page,server.origin,path+('&' if '?' in path else '?')+urlencode({'project_id':project}))

    def capture(name):
        settled(page)
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),name
        page.mouse.move(1480,950)
        page.screenshot(path=str(server.output/(name+'.png')),full_page=True)
        captures.append(name+'.png')

    def variants(name):
        capture(name+'-light')
        page.get_by_role('button',name='切换雾蓝深色',exact=True).click()
        expect(page.locator('html')).to_have_attribute('data-studio-theme','dark')
        capture(name+'-dark')
        page.set_viewport_size({'width':760,'height':980})
        capture(name+'-narrow')
        page.set_viewport_size({'width':1512,'height':980})
        page.get_by_role('button',name='切换浅色',exact=True).click()

    def execute_loaded(version):
        current=scenario.request('GET','/api/experience/official-sample')
        assert current['scenario_version']==version
        change=current['current_change_id']
        # 修改加载会使旧会话失效；通过真实材料预览与原批次恢复，不额外登录掩盖问题。
        route('/preparation?prepare_example=1&change_id='+change)
        expect(page.get_by_text('确认后开始准备',exact=True)).to_be_visible()
        page.get_by_role('checkbox',name='允许上述操作、来源读取及材料采用',exact=True).check()
        page.get_by_role('button',name='允许并开始准备',exact=True).click()
        until(lambda:scenario.request('GET',f'/api/projects/{project}/preparation'),lambda item:item['preparation_complete'],seconds=120)
        route('/reports?view=plan&change_id='+change)
        page.get_by_role('button',name='预览这次检查',exact=True).click()
        expect(page.get_by_role('heading',name='确认这次检查',exact=True)).to_be_visible()
        page.get_by_role('button',name='开始检查',exact=True).click()
        page.wait_for_function("new URLSearchParams(location.hash.split('?')[1]??'').has('run_id')")
        run=page.evaluate("new URLSearchParams(location.hash.split('?')[1]).get('run_id')")
        status=until(lambda:scenario.request('GET',f'/api/runs/{run}'),lambda item:item['run']['lifecycle'] not in {'RUNNING','QUEUED'},seconds=120)
        assert status['result_integrity']=='VALID' and status['run']['verdict']=='BLOCK'
        story=scenario.request('GET',f'/api/runs/{run}/result-story')
        assert story['change_context']['change_id']==change
        route('/reports?run_id='+run)
        report_ready(page)
        expect(page.get_by_role('region',name='这份修改的实际业务后果')).to_be_visible()
        return {'version':version,'run_id':run,'change_id':change,'story':story}

    route('/reports?run_id='+initial.run_id)
    page.get_by_role('link',name='查看错误修改',exact=True).click()
    expect(page.get_by_role('heading',name='检查一次错误修改',exact=True)).to_be_visible()
    expect(page.get_by_role('button',name='加载这次错误修改',exact=True)).to_be_enabled()
    variants('change-task')
    journey=scenario.request('GET','/api/experience/official-sample/development')
    assert journey['implementation']=='BASELINE' and journey['run_id']==initial.run_id
    response=server.client.post('/api/experience/official-sample/version',json={'schema_version':'1','version':'VULNERABLE','project_id':project,'expected_basis':'stale'})
    assert response.status_code!=200
    assert scenario.request('GET','/api/experience/official-sample/development')['implementation']=='BASELINE'
    page.get_by_role('button',name='加载这次错误修改',exact=True).click()
    capture('change-confirm-light')
    page.get_by_role('button',name='取消',exact=True).click()
    assert scenario.request('GET','/api/experience/official-sample/development')['implementation']=='BASELINE'
    page.get_by_role('button',name='加载这次错误修改',exact=True).click()
    page.get_by_role('button',name='确认加载这份修改',exact=True).click()
    expect(page.locator('.jj-page')).to_have_attribute('data-route',__import__('re').compile('/preparation'))
    wrong=execute_loaded('VULNERABLE')
    variants('wrong-result')
    # 同一版本使用原稳定交付键回读，不能创建第二次源码转换。
    replay=scenario.request('POST','/api/experience/official-sample/version',{'schema_version':'1','version':'VULNERABLE','project_id':project,'expected_basis':journey['transition_basis']})
    assert replay['current_change_id']==wrong['change_id']
    page.get_by_role('link',name='查看开放后撤回的修改',exact=True).click()
    expect(page.get_by_role('button',name='加载开放后撤回的修改',exact=True)).to_be_enabled()
    variants('deeper-change')
    page.get_by_role('button',name='加载开放后撤回的修改',exact=True).click()
    page.get_by_role('button',name='确认加载这份修改',exact=True).click()
    expect(page.locator('.jj-page')).to_have_attribute('data-route',__import__('re').compile('/preparation'))
    deeper=execute_loaded('EXPOSE_REVOKE')
    target=next(item for item in deeper['story']['actions'] if item['permission']['expectation']=='DENY' and any(effect['business_label']=='内部完整包已被接收' for effect in item['fact_comparison']['effects']))
    assert target['fact_comparison']['http_surface']['http_status']==403
    assert target['fact_comparison']['http_surface']['recovery_verified']
    assert any(effect['business_label']=='内部包曾向操作账号开放' and effect['assessment_state']=='CONFIRMED' for effect in target['fact_comparison']['effects'])
    variants('denied-with-effect')
    # 当前示例和报告有真实记录后，只读走查所有主要工作面及集中设置。
    audit_paths=[('workbench','/workspace'),('permissions','/permissions'),('testing','/testing'),('issues','/issues'),('application','/application'),('environment','/environment'),('records','/reports'),('preparation','/preparation'),('changes','/changes'),('collaboration','/workspace?view=collaboration'),('settings-tools','/settings?section=tools'),('settings-storage','/settings?section=storage'),('settings-system','/settings?section=system')]
    for name,path in audit_paths:
        route(path);capture('audit-'+name+'-light')
    route('/reports?run_id='+deeper['run_id']+'&case_id='+target['case_id'])
    expect(page.get_by_role('button',name='关闭检查依据',exact=True)).to_be_visible()
    capture('expanded-evidence-light')
    page.emulate_media(reduced_motion='reduce')
    page.set_viewport_size({'width':760,'height':980})
    capture('expanded-evidence-narrow')
    (server.output/'journey.json').write_text(json.dumps(dict(project_id=project,baseline_run_id=initial.run_id,wrong=wrong,deeper=deeper,captures=captures,audit_paths=audit_paths),ensure_ascii=False,indent=2),encoding='utf-8')
