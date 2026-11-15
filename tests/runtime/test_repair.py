# 复验场景独立建立基线，精确引用漏洞原题并核对修复及正常功能。
import pytest
import json
from urllib.parse import urlencode
from tests.support.browser_review import report_ready, capture_workflow, navigate, settled
from playwright.sync_api import expect

pytestmark=[pytest.mark.runtime,pytest.mark.repair]

def test_rule_problem_is_verified_against_its_original_check(official,runtime_server,browser_page):
    baseline=official.check('BASELINE')
    assert baseline.status['run']['verdict']=='PASS'
    change=official.load('VULNERABLE')
    problem=official.check('VULNERABLE',change)
    assert problem.status['run']['lifecycle']=='COMPLETED'
    assert problem.status['run']['verdict']=='BLOCK'
    assert any(item['breakpoint'] for item in problem.story['actions'])
    project=official.project_id
    contracts=official.request('GET',f'/api/runs/{problem.run_id}/repair-contracts')
    assert len(contracts)==1
    reference={key:contracts[0][key] for key in ('source_run_id','source_case_id','repair_fingerprint')}
    before=official.request('GET','/api/experience/official-sample/development')
    rejected=runtime_server.client.post('/api/experience/official-sample/version',json={
        'schema_version':'1','version':'FIXED','project_id':project,'expected_basis':before['transition_basis'],
        'repair_reference':{**reference,'repair_fingerprint':'f'*64}})
    assert rejected.status_code==409
    unchanged=official.request('GET','/api/experience/official-sample/development')
    assert unchanged['implementation']=='VULNERABLE' and unchanged['source_fingerprint']==before['source_fingerprint']
    issue_path='/issues?'+urlencode({'repair_reference':reference['repair_fingerprint'],'source_run_id':reference['source_run_id'],
        'source_case_id':reference['source_case_id'],'section':'repair','project_id':project})
    page=browser_page
    navigate(page,runtime_server.origin,issue_path)
    expect(page.get_by_role('button',name='加载这份预置修复',exact=True)).to_be_enabled()
    settled(page)
    page.screenshot(path=str(runtime_server.output/'repair-task-light.png'),full_page=True)
    page.get_by_role('button',name='加载这份预置修复',exact=True).click()
    page.get_by_role('button',name='取消',exact=True).click()
    assert official.request('GET','/api/experience/official-sample/development')['implementation']=='VULNERABLE'
    page.get_by_role('button',name='加载这份预置修复',exact=True).click()
    settled(page)
    page.screenshot(path=str(runtime_server.output/'repair-confirm-light.png'),full_page=True)
    page.get_by_role('button',name='确认加载修复',exact=True).click()
    expect(page.get_by_role('heading',name='已登记的修改',exact=True)).to_be_visible()
    fixed_change=page.evaluate("new URLSearchParams(location.hash.split('?')[1]).get('change_id')")
    assert fixed_change
    assert page.evaluate("new URLSearchParams(location.hash.split('?')[1]).get('repair_reference')")==reference['repair_fingerprint']
    expect(page.get_by_text('原问题已解决，正常功能保留',exact=True)).to_have_count(0)
    settled(page)
    page.screenshot(path=str(runtime_server.output/'repair-loaded-light.png'),full_page=True)
    fixed=official.check('FIXED',fixed_change)
    assert fixed.status['run']['lifecycle']=='COMPLETED'
    assert fixed.status['run']['verdict']=='PASS'
    assert fixed.status['result_integrity']=='VALID'
    assert fixed.story['repair_verification']['status']=='VERIFIED'
    (runtime_server.output/'repair-chain.json').write_text(json.dumps(dict(project_id=project,reference=reference,
        baseline_run=baseline.run_id,problem_run=problem.run_id,repair_run=fixed.run_id,repair_change=fixed_change,
        invalid_reference_rejected_before_source_change=True,verification=fixed.story['repair_verification']),ensure_ascii=False,indent=2),encoding='utf-8')
    browser_page.goto(runtime_server.origin+'/#/reports?run_id='+fixed.run_id,wait_until='domcontentloaded')
    report_ready(browser_page,evidence_label='查看依据')
    browser_page.screenshot(path=str(runtime_server.output/'repair-report.png'),full_page=True)
    capture_workflow(browser_page, runtime_server.origin, runtime_server.output, fixed.run_id,
        project_id=official.project_id,evidence_label='查看依据')
    page=browser_page
    page.set_viewport_size(dict(width=1078,height=980))
    navigate(page,runtime_server.origin,'/permissions?project_id='+official.project_id)
    expect(page.locator('.jj-collection-main')).to_be_visible()
    expect(page.locator('.jj-collection .jj-inspector')).to_have_count(0)
    page.screenshot(path=str(runtime_server.output/'rules-first-entry-1078.png'),full_page=True)
    selected=page.locator('.jj-object-select').first
    selected.press('Enter')
    expect(page.locator('.jj-collection .jj-inspector')).to_be_visible()
    page.get_by_role('button',name='收起详情',exact=True).press('Escape')
    expect(page.locator('.jj-collection-main')).to_be_visible()
    expect(selected).to_be_focused()
    navigate(page,runtime_server.origin,'/reports?view=plan&project_id='+official.project_id)
    page.get_by_role('button',name='查看本次范围',exact=True).click()
    expect(page.get_by_role('heading',name='调整检查范围',exact=True)).to_be_visible()
    page.get_by_role('button',name='选定规则',exact=True).click()
    names=page.locator('.jj-scope-rule-option strong')
    expect(names.first).to_be_visible()
    assert all(float(item.evaluate('node=>parseFloat(getComputedStyle(node).fontSize)'))>=14 for item in names.all())
    settled(page)
    page.screenshot(path=str(runtime_server.output/'check-scope-reading.png'),full_page=True)
    page.emulate_media(reduced_motion='reduce')
    page.set_viewport_size(dict(width=420,height=980))
    navigate(page,runtime_server.origin,'/reports?project_id='+official.project_id+'&run_id='+fixed.run_id)
    report_ready(page)
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
    page.screenshot(path=str(runtime_server.output/'repair-narrow-reduced-motion.png'),full_page=True)
