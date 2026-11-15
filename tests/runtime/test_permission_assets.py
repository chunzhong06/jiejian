"""在真实浏览器沿要求、决定、材料与报告往返，不由截图替代业务运行。"""
import json
import pytest
from playwright.sync_api import expect
from tests.support.browser_review import navigate,settled,report_ready

pytestmark=[pytest.mark.runtime,pytest.mark.baseline]


def test_requirement_review_returns_to_exact_preparation_and_published_result(official,runtime_server,browser_page):
    page=browser_page
    project=official.project_id
    prefix=f'/api/projects/{project}/business-boundaries'
    epoch=official.request('GET',prefix)['policy_epoch']
    navigate(page,runtime_server.origin,'/permissions?project_id='+project)
    page.get_by_text('查看相关问题与已保存决定',exact=True).click()
    page.get_by_role('button',name='核对这项要求',exact=True).first.click()
    expect(page.get_by_label('实际业务含义',exact=True)).to_be_visible()
    page.get_by_role('combobox',name='如何处理',exact=True).press('ArrowDown')
    page.get_by_role('option',name='当前业务不适用',exact=True).click()
    page.get_by_label('实际业务含义',exact=True).fill('本次只核对已确认的本人和跨角色要求，同角色其他账号另排。')
    page.get_by_label('判断依据',exact=True).fill('这次准备的示例账号对应现有要求，保留未纳入原因。')
    page.get_by_role('button',name='保存业务决定',exact=True).click()
    expect(page.get_by_text('已保存决定',exact=True)).to_be_visible()
    assert official.request('GET',prefix)['policy_epoch']==epoch
    page.evaluate("scrollTo(0,0)");settled(page)
    page.screenshot(path=str(runtime_server.output/'boundary-decision.png'),full_page=True)

    rule=official.request('GET',prefix)['permission_intents'][0]['intent_id']
    navigate(page,runtime_server.origin,'/permissions?project_id='+project+'&rule_id='+rule)
    expect(page.get_by_role('heading',name='怎样验证这项要求',exact=True)).to_be_visible()
    page.get_by_role('link',name='准备并核对这项要求',exact=True).click()
    expect(page.get_by_role('region',name='检查准备工作面',exact=True)).to_be_visible()
    assert 'rule_id='+rule in page.url and 'return_to=' in page.url
    page.get_by_text('本次材料处理方案',exact=True).click()
    expect(page.get_by_role('table')).to_be_visible()
    page.evaluate("scrollTo(0,0)");settled(page)
    page.screenshot(path=str(runtime_server.output/'combined-preparation.png'),full_page=True)

    result=official.check('ASSET_WORKFLOW')
    assert result.status['result_integrity']=='VALID' and result.story['verdict']=='PASS'
    assert any(item['kind']=='NORMAL' for item in result.story['delivery_summary'])
    navigate(page,runtime_server.origin,'/reports?project_id='+project+'&run_id='+result.run_id)
    report_ready(page)
    page.get_by_text('本次交付摘要',exact=True).click()
    expect(page.get_by_text('实际运行与交付对应',exact=True)).to_be_visible()
    for width in (1512,420):
        page.set_viewport_size(dict(width=width,height=980));page.evaluate('scrollTo(0,0)');settled(page)
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
        page.screenshot(path=str(runtime_server.output/f'delivery-{width}.png'),full_page=True)
    (runtime_server.output/'assets-acceptance.json').write_text(json.dumps(dict(project_id=project,run_id=result.run_id,
        saved_decision_kept_formal_epoch=True,exact_rule_preparation=True,verdict=result.story['verdict']),ensure_ascii=False),encoding='utf-8')
