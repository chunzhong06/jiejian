"""真实控制面、Worker/Runner与浏览器共同验证新增线索和跨权限版本的原题接续。"""
import copy
import json
import re
from uuid import uuid4
import pytest
from playwright.sync_api import expect
from tests.support.browser_review import report_ready, settled

pytestmark=[pytest.mark.runtime,pytest.mark.repair]


def test_new_business_and_unrelated_rules_preserve_original_repair(official,runtime_server,browser_page):
    root=f'/api/projects/{official.project_id}'

    def approve(permissions, draft, reason):
        proposal=official.request('POST',root+'/business-boundaries/maintenance-proposals',dict(schema_version='1',
            expected_boundary_state_fingerprint=draft['boundary_state_fingerprint'],actors=draft['actors'],
            actions=draft['actions'],permissions=permissions,provenance=reason))['proposal']
        official.request('POST',root+'/business-boundaries/proposals/'+proposal['proposal_id']+'/approve',dict(
            schema_version='1',expected_fingerprint=proposal['proposal_fingerprint'],reason=reason))

    boundary=official.request('GET',root+'/business-boundaries')
    internal=next(item['action_id'] for item in boundary['actions'] if item['display_name']=='取得内部完整包')
    selected=[{key:item[key] for key in ('intent_id','revision','intent_hash')} for item in boundary['permission_intents']
        if item['business_action_id']==internal]
    # 先沿示例的真实起始检查进入修改阶段，再由选中范围冻结原题A及其正常对照。
    baseline=official.check('BASELINE')
    assert baseline.status['run']['verdict']=='PASS'
    official.load('VULNERABLE')
    original=official.check('ORIGINAL_A',selected=selected)
    assert original.status['run']['verdict']=='BLOCK'
    original_bytes=runtime_server.client.get(f'/api/runs/{original.run_id}/result-story').content

    draft=official.request('GET',root+'/business-boundaries/maintenance-draft')
    unrelated=next(item for item in draft['permissions'] if item['business_action_item_id'] != next(
        action['item_id'] for action in draft['actions'] if action['action_id']==internal) and item['expectation']=='ALLOW')
    later=copy.deepcopy(unrelated)
    source='src_'+uuid4().hex
    document={'openapi':'3.0.3','paths':{'/api/future/bulk-export':{'get':{
        'summary':'导出全部资料','responses':{'200':{'description':'后续版本的业务线索'}}}}}}
    preview=official.request('POST',root+'/api-sources/preview',dict(kind='OPENAPI',raw=json.dumps(document,ensure_ascii=False)))
    accepted=official.request('POST',root+'/api-sources/accept',dict(candidate_id=preview['candidate_id'],source_id=source,
        name='后续业务资料',expected_revision=0,expected_fingerprint=preview['fingerprint']))
    request=accepted['requests'][0]
    coverage=official.request('GET',root+'/discovery-coverage')
    assert next(item for item in coverage['items'] if item['request_id']==request['item_id'])['status']=='PENDING'
    pending=official.check('A_WITH_PENDING_BUSINESS',selected=selected)
    assert pending.status['run']['verdict']=='BLOCK'
    pending_snapshot=copy.deepcopy(pending.story['discovery_coverage'])
    assert next(item for item in pending_snapshot['items'] if item['request_id']==request['item_id'])['status']=='PENDING'

    # 人通过原接口来源工作面明确“不纳入本轮”，不调用私有完成开关。
    browser_page.goto(runtime_server.origin+'/#/application?view=sources&project_id='+official.project_id+
        '&source_id='+source+'&request_id='+request['item_id'],wait_until='domcontentloaded')
    expect(browser_page.get_by_role('heading',name='导出全部资料',exact=True)).to_be_visible()
    browser_page.get_by_role('button',name='此线索不纳入当前要求',exact=True).click()
    expect(browser_page.get_by_text(re.compile('这条接口线索已明确不纳入当前要求'))).to_be_visible()
    settled(browser_page)
    browser_page.screenshot(path=str(runtime_server.output/'new-business-reviewed.png'),full_page=True)
    assert official.request('GET',f'/api/runs/{pending.run_id}/result-story')['discovery_coverage']==pending_snapshot

    draft=official.request('GET',root+'/business-boundaries/maintenance-draft')
    permissions=copy.deepcopy(draft['permissions'])
    next(item for item in permissions if item['item_id']==unrelated['item_id'])['effective_state']='RETIRED'
    later.update(item_id='pperm_'+uuid4().hex[:16],intent_id=None,expected_current_revision=None,effective_state='ACTIVE')
    approve([*permissions,later],draft,'新增无关的公开业务规则B，沿用原内部包要求A')
    current=official.request('GET',root+'/business-boundaries')
    assert current['policy_epoch']>original.story['policy_epoch']
    assert all(any(all(item[key]==reference[key] for key in reference) for item in current['permission_intents']) for reference in selected)

    fixed_change=official.load('FIXED',repair=original)
    fixed=official.check('REPAIRED_A_AFTER_NEW_RULE_B',fixed_change)
    assert fixed.status['result_integrity']=='VALID' and fixed.status['run']['verdict']=='PASS'
    assert fixed.story['repair_verification']['status']=='VERIFIED'
    current_coverage=official.request('GET',root+'/discovery-coverage')
    assert next(item for item in current_coverage['items'] if item['request_id']==request['item_id'])['status']=='EXCLUDED'
    assert fixed.story['policy_epoch']>original.story['policy_epoch']
    assert all(item['match_status']=='MATCHED' for item in fixed.story['repair_comparison'])
    omitted=[item for item in fixed.story['delivery_summary'] if item['kind']=='UNCHECKED' and item['permission']]
    assert omitted and all(item['historical_name_available'] and item['label']!='本次未选要求' for item in omitted)
    unresolved=[item for item in fixed.story['delivery_summary'] if item['kind']=='UNRESOLVED']
    assert all(item['review_url'] for item in unresolved)
    assert runtime_server.client.get(f'/api/runs/{original.run_id}/result-story').content==original_bytes
    complete=official.check('ALL_CURRENT_RULES_AFTER_REPAIR')
    assert complete.status['run']['verdict']=='PASS' and len(complete.story['actions'])>len(fixed.story['actions'])
    browser_page.goto(runtime_server.origin+'/#/reports?project_id='+official.project_id+'&run_id='+fixed.run_id,wait_until='domcontentloaded')
    report_ready(browser_page,evidence_label='查看依据')
    expect(browser_page.get_by_text('正常对照 0 条',exact=True)).to_have_count(0)
    browser_page.get_by_text('本次检查的适用范围',exact=True).click()
    expect(browser_page.get_by_role('region',name='本次检查的适用范围')).to_contain_text('1 项明确不纳入')
    browser_page.screenshot(path=str(runtime_server.output/'cross-policy-repair-report.png'),full_page=True)
    browser_page.get_by_text('本次交付摘要',exact=True).click()
    expect(browser_page.get_by_role('link',name='核对要求并安排检查',exact=True).first).to_be_visible()
    settled(browser_page)
    browser_page.locator('.jj-delivery-summary').screenshot(path=str(runtime_server.output/'actionable-delivery.png'))
    visual=[]
    for width,theme in ((960,'light'),(420,'light'),(420,'dark'),(1512,'dark')):
        browser_page.set_viewport_size({'width':width,'height':980})
        if theme=='dark' and browser_page.locator('html').get_attribute('data-studio-theme')!='dark':
            browser_page.get_by_role('button',name='切换雾蓝深色',exact=True).click()
        if width==1512:
            browser_page.get_by_text('完整适用条件与记录引用',exact=True).click()
        settled(browser_page)
        overflow=browser_page.evaluate('document.documentElement.scrollWidth>innerWidth')
        assert not overflow
        browser_page.screenshot(path=str(runtime_server.output/f'repair-{width}-{theme}.png'),full_page=True)
        visual.append(dict(width=width,theme=theme,document_overflow=overflow))
    (runtime_server.output/'visual.json').write_text(json.dumps(visual),encoding='utf-8')
    (runtime_server.output/'continuity.json').write_text(json.dumps(dict(original=original.run_id,pending=pending.run_id,
        repaired=fixed.run_id,all_current=complete.run_id,original_epoch=original.story['policy_epoch'],
        current_epoch=fixed.story['policy_epoch'],verification=fixed.story['repair_verification'],
        old_publication_unchanged=True,old_pending_snapshot_unchanged=True,
        unchanged_api_review_retained=True),ensure_ascii=False,indent=2),encoding='utf-8')
