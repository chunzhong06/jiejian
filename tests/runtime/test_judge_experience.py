"""同一隔离示例核对评委入口、两种错误修改及原题修复，不调用模型。"""
import json
import re
from urllib.parse import urlencode
import pytest
from playwright.sync_api import expect
from tests.support.browser_review import navigate, settled, report_ready
from tests.support.official import OfficialScenario, until

pytestmark=[pytest.mark.runtime,pytest.mark.repair]


def test_judge_can_follow_real_effects_and_named_repair(runtime_server,browser_page):
    server,page=runtime_server,browser_page
    scenario=OfficialScenario(server.client)
    captures=[]

    def capture(name,variants=False):
        def save(suffix):
            settled(page)
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
            page.mouse.move(1400,20)
            page.screenshot(path=str(server.output/f'{name}-{suffix}.png'),full_page=True)
            captures.append(f'{name}-{suffix}.png')
        save('light')
        if variants:
            page.get_by_role('button',name='切换深色',exact=True).click()
            expect(page.locator('html')).to_have_attribute('data-studio-theme','dark')
            save('dark')
            page.set_viewport_size({'width':420,'height':920})
            save('narrow')
            page.set_viewport_size({'width':1512,'height':980})
            page.get_by_role('button',name='切换浅色',exact=True).click()

    navigate(page,server.origin,'/workspace')
    expect(page.get_by_role('heading',name='请求被拒绝，就没有越权吗？')).to_be_visible()
    capture('welcome',True)
    navigate(page,server.origin,'/settings?section=tools')
    expect(page.get_by_role('link',name='选择或建立应用')).to_be_visible()
    assert page.get_by_role('combobox',name='访问范围').count()==0
    capture('tools-empty')
    navigate(page,server.origin,'/environment')
    capture('example-entry')
    page.get_by_role('button',name='开始示例体验',exact=True).click()
    expect(page.get_by_role('link',name='确认访问要求',exact=True)).to_be_visible(timeout=90000)
    current=scenario.request('GET','/api/experience/official-sample?lightweight=true')
    scenario.project_id=project=current['project_id']
    page.get_by_role('link',name='确认访问要求',exact=True).click()
    expect(page.get_by_role('table',name='示例权限要求')).to_be_visible()
    page.get_by_role('button',name='批准规则并继续',exact=True).click()
    expect(page.get_by_role('heading',name='示例规则已确认',exact=True)).to_be_visible()
    page.get_by_role('link',name='准备示例材料',exact=True).click()

    def execute(version,change=None):
        # 后续修改也经过同一真实材料授权与冻结检查；不直接操作目标。
        if change:navigate(page,server.origin,'/preparation?'+urlencode({'prepare_example':'1','change_id':change,'project_id':project}))
        expect(page.get_by_text('确认后开始准备',exact=True)).to_be_visible()
        page.get_by_role('checkbox',name='允许上述操作、来源读取及材料采用',exact=True).check()
        page.get_by_role('button',name='允许并开始准备',exact=True).click()
        until(lambda:scenario.request('GET',f'/api/projects/{project}/preparation'),lambda value:value['preparation_complete'],seconds=120)
        navigate(page,server.origin,'/reports?'+urlencode({'view':'plan','project_id':project,**({'change_id':change} if change else {})}))
        page.get_by_role('button',name='预览这次检查',exact=True).click()
        expect(page.get_by_role('heading',name='确认这次检查',exact=True)).to_be_visible()
        page.get_by_role('button',name='开始检查',exact=True).click()
        page.wait_for_function("new URLSearchParams(location.hash.split('?')[1]??'').has('run_id')")
        run=page.evaluate("new URLSearchParams(location.hash.split('?')[1]).get('run_id')")
        status=until(lambda:scenario.request('GET',f'/api/runs/{run}'),lambda value:value['run']['lifecycle'] not in {'QUEUED','RUNNING'},seconds=120)
        assert status['result_integrity']=='VALID'
        story=scenario.request('GET',f'/api/runs/{run}/result-story')
        assert story['verdict']==('PASS' if version in {'BASELINE','FIXED'} else 'BLOCK')
        scenario.stages.append({'version':version,'run_id':run,'verdict':story['verdict']})
        (server.output/'journey-checkpoint.json').write_text(json.dumps({'project_id':project,'stages':scenario.stages},ensure_ascii=False,indent=2),encoding='utf-8')
        navigate(page,server.origin,'/reports?'+urlencode({'project_id':project,'run_id':run}))
        report_ready(page)
        expect(page.locator('.jj-business-outcome')).to_be_visible()
        capture(version.lower(),True)
        return run,story

    initial,_=execute('BASELINE')
    page.get_by_role('link',name='查看错误修改',exact=True).click()
    expect(page.get_by_role('link',name='查看开放后撤回的修改',exact=True)).to_be_visible()
    capture('change-choice')
    page.get_by_role('button',name='加载这次错误修改',exact=True).click()
    page.get_by_role('button',name='取消',exact=True).click()
    assert scenario.request('GET','/api/experience/official-sample/development')['implementation']=='BASELINE'
    page.get_by_role('button',name='加载这次错误修改',exact=True).click()
    page.get_by_role('button',name='确认加载这份修改',exact=True).click()
    expect(page.locator('.jj-page')).to_have_attribute('data-route',re.compile('/preparation'))
    change=scenario.request('GET','/api/experience/official-sample')['current_change_id']
    wrong,_=execute('VULNERABLE',change)
    page.get_by_role('link',name='查看开放后撤回的修改',exact=True).click()
    capture('deeper-choice')
    page.get_by_role('button',name='加载开放后撤回的修改',exact=True).click()
    page.get_by_role('button',name='确认加载这份修改',exact=True).click()
    expect(page.locator('.jj-page')).to_have_attribute('data-route',re.compile('/preparation'))
    change=scenario.request('GET','/api/experience/official-sample')['current_change_id']
    deeper,story=execute('EXPOSE_REVOKE',change)
    affected=next(item for item in story['actions'] if item['case_verdict']=='VULNERABLE')
    assert affected['fact_comparison']['http_surface']['http_status']==403
    assert affected['fact_comparison']['http_surface']['recovery_verified']
    assert any(effect['business_label']=='内部包曾向操作账号开放' and effect['assessment_state']=='CONFIRMED' for effect in affected['fact_comparison']['effects'])
    repairs=scenario.request('GET',f'/api/projects/{project}/repair')
    # 同一问题再次出现仍沿首个可处理原题；最新报告的冻结合同可能只供历史阅读。
    contract=next(task['contract'] for task in repairs['tasks'] if task['task_reference']==repairs['primary_task_reference'])
    reference={key:contract[key] for key in ('source_run_id','source_case_id','repair_fingerprint')}
    issue='/issues?'+urlencode({'source_run_id':reference['source_run_id'],'source_case_id':reference['source_case_id'],'repair_reference':reference['repair_fingerprint'],'section':'repair','project_id':project})
    navigate(page,server.origin,issue)
    page.get_by_role('button',name='加载这份预置修复',exact=True).click()
    page.get_by_role('button',name='确认加载修复',exact=True).click()
    expect(page.get_by_role('heading',name='已登记的修改',exact=True)).to_be_visible(timeout=30000)
    change=page.evaluate("new URLSearchParams(location.hash.split('?')[1]).get('change_id')")
    repaired,fixed=execute('FIXED',change)
    assert fixed['repair_verification']['status']=='VERIFIED'
    navigate(page,server.origin,issue+'&change_id='+change)
    expect(page.get_by_role('list',name='具名复验结果')).to_be_visible()
    expect(page.get_by_text('原问题已解决',exact=True)).to_be_visible()
    capture('named-repair',True)
    (server.output/'journey.json').write_text(json.dumps({'project_id':project,'stages':scenario.stages,'reference':reference,'repair_change':change,'screens':captures},ensure_ascii=False,indent=2),encoding='utf-8')
