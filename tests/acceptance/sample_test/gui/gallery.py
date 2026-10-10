# 通过真实GUI核对Node示例的登录、文件参照与采用；仅操作本轮新建账号和受控窗口。
import hashlib
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode
from playwright.sync_api import expect
from tests.acceptance.sample_test.harness.state import SampleTestError
from tests.acceptance.sample_test.harness.lifecycle import _wait_for
from tests.acceptance.sample_test.windows import window_snapshot,visible_top_level_windows,Desktop,_invoke_button,_wait_text,belongs_to_login_preparation


def propose(gui,project):
    gui._goto('/permissions')
    gui.page.get_by_role('radio',name='允许下载展示版',exact=True).check()
    payload,body=gui._response('/api/experience/official-sample/boundary-proposal',lambda:gui.page.get_by_role('button',name='使用已提供的权限提案',exact=True).click())
    if body!={'exhibition_download':True}:raise SampleTestError('GALLERY_MEANING_CHOICE_MISSING')
    proposal=payload['proposal']
    if proposal['project_id']!=project or len(proposal['proposed_actions'])!=3 or len(proposal['proposed_permissions'])!=5 or proposal['unresolved_questions']:
        raise SampleTestError('GALLERY_PROPOSAL_SCOPE_INVALID')
    pdf=next(item['item_id'] for item in proposal['proposed_actions'] if item['display_name']=='下载公开展示版')
    reviewer=next(item['item_id'] for item in proposal['proposed_actors'] if item['display_name']=='评审')
    if not any(item['business_action_item_id']==pdf and item['subject_actor_item_id']==reviewer and item['expectation']=='ALLOW' for item in proposal['proposed_permissions']):
        raise SampleTestError('GALLERY_HUMAN_CHOICE_NOT_IN_RULE')
    gui.approve(project,SimpleNamespace(**proposal));gui._mark('meaning-choice')


def _login_window(before,chromium,preparation_id,account,create):
    deadline=time.monotonic()+30;window=None
    while time.monotonic()<deadline:
        matches=[item for item in visible_top_level_windows() if item.handle not in before and '数字展馆协作空间' in item.title
            and str(item.image).casefold()==str(Path(chromium).resolve()).casefold()
            and belongs_to_login_preparation(item.process_id,preparation_id)]
        if len(matches)>1:raise SampleTestError('GALLERY_LOGIN_WINDOW_AMBIGUOUS')
        if matches:window=Desktop(backend='uia').window(handle=matches[0].handle);break
        time.sleep(.2)
    if window is None:raise SampleTestError('GALLERY_LOGIN_WINDOW_UNAVAILABLE')
    owner=account=='curator'
    _invoke_button(window,'负责人登录' if owner else '评审登录')
    _wait_text(window,'负责人 · curator' if owner else '评审 · judge',timeout=15)
    if create and owner:
        _invoke_button(window,'创建示例展馆')
        window.child_window(title_re='(?s).*虚构展馆资料和文件已创建.*',control_type='Text').wait('exists',timeout=15)


def login(gui,project,chromium,*,create=False):
    identities=gui.client.call('GET',f'/api/projects/{project}/test-identities')
    for identity in identities:
        gui._goto('/tests?materials=1&identities=1')
        row=gui.page.locator('.identity-account-row').filter(has_text=identity['label'])
        if identity['auth_method'] is not None:
            row.get_by_role('button',name='清除登录状态' if identity['status']=='PREPARED' else '清除旧状态',exact=True).click()
            gui._response(f"/api/test-identities/{identity['identity_id']}/reset",lambda:gui.page.get_by_role('dialog').get_by_role('button',name='清除登录状态',exact=True).click())
        before=window_snapshot()
        preparation,_=gui._response(f"/api/test-identities/{identity['identity_id']}/preparations",lambda:row.get_by_role('button',name='打开登录浏览器',exact=True).click())
        _login_window(before,chromium,preparation['preparation_id'],identity['label'].split(' · ')[0],create)
        confirm=gui.page.get_by_role('button',name='我已完成登录',exact=True)
        # AntD加载按钮会吞掉点击；前一个账号的工作区回读结束后才确认本次登录。
        expect(confirm).to_have_attribute('aria-busy','false',timeout=60_000)
        expect(confirm).to_be_enabled(timeout=60_000)
        gui._response(f"/api/identity-preparations/{preparation['preparation_id']}/confirm",lambda:confirm.click())
        _wait_for(lambda:gui.client.call('GET',f"/api/test-identities/{identity['identity_id']}"),lambda value:value['status']=='PREPARED',timeout=30,label='实际账号登录保存')
        gui._mark('identity-login')
    return {str(i):item['identity_id'] for i,item in enumerate(identities)}


def proofs(gui,project):
    prefix=f'/api/projects/{project}/proof-preparation'
    sources=gui.client.call('GET',prefix)['sources']
    if len(sources)!=4:raise SampleTestError('GALLERY_PROOF_SOURCES_MISSING')
    for source in sources:
        gui._goto('/tests?'+urlencode(dict(materials=1,proof_sources=1,source=source['source_id'])))
        if source['config']['source_kind']=='REFERENCE_FILE' and not source['config']['reference_artifact']:
            gui.page.get_by_role('button',name='预览获取操作',exact=True).click()
            modal=gui.page.get_by_role('dialog',name='正常取得一份参照',exact=True)
            modal.get_by_role('checkbox',name='允许本次正常操作及所列恢复',exact=True).check()
            receipt,_=gui._response(prefix+'/reference-captures',lambda:modal.get_by_role('button',name='允许并开始本次取样',exact=True).click())
            capture=_wait_for(lambda:gui.client.call('GET',prefix+'/reference-captures/'+receipt['result']['capture_id']),lambda value:value['state'] in {'SUCCEEDED','FAILED','CANCELLED'},timeout=60,label='正常取样')
            if capture['report']['state']!='CANDIDATE':raise SampleTestError('GALLERY_REFERENCE_NOT_OBTAINED')
            with gui.page.expect_download() as download:gui.page.get_by_role('link',name='保存文件并核对内容',exact=True).click()
            target=gui.audit_dir/('reference-'+capture['asset_id']+'.bin');download.value.save_as(target)
            context=gui.client.call('GET',prefix);asset=next(item for item in context['reference_inputs'] if item['asset_id']==capture['asset_id'])
            if (target.stat().st_size,hashlib.sha256(target.read_bytes()).hexdigest())!=(asset['manifest']['size'],asset['manifest']['sha256']):raise SampleTestError('GALLERY_REFERENCE_BYTES_MISMATCH')
            gui._response(prefix+'/sources',lambda:gui.page.get_by_role('button',name='以此参照继续',exact=True).click())
            gui._mark('reference-capture-and-confirm')
        context=gui.client.call('GET',prefix);current=next(item for item in context['sources'] if item['source_id']==source['source_id'])
        if not current['read_scope_confirmed']:
            gui.page.get_by_role('button',name='确认读取范围',exact=True).click()
            modal=gui.page.get_by_role('dialog',name='确认来源读取范围',exact=True)
            modal.get_by_role('checkbox',name='我已核对以上范围与影响',exact=True).check()
            gui._response(prefix+'/read-scopes',lambda:modal.get_by_role('button',name='允许这些读取',exact=True).click())
            gui._mark('proof-scope')
        receipt,_=gui._response(prefix+'/preflights',lambda:gui.page.get_by_role('button',name='开始预检查',exact=True).click())
        result=_wait_for(lambda:gui.client.call('GET',prefix+'/preflights/'+receipt['result']['preflight_id']),lambda value:value['state'] in {'SUCCEEDED','FAILED','CANCELLED'},timeout=60,label='来源预检查')
        if result['report']['assessment']!='USABLE':raise SampleTestError('GALLERY_PROOF_NOT_USABLE')
        if not current['adopted']:
            gui.page.get_by_role('button',name='预览采用影响',exact=True).click()
            modal=gui.page.get_by_role('dialog',name='采用这项证明来源',exact=True)
            modal.get_by_role('checkbox').check()
            gui._response(prefix+'/adoptions',lambda:modal.get_by_role('button',name='确认采用',exact=True).click())
            gui._mark('proof-adoption')
    gui.capture('gallery-materials')
    gui._mark('prepare')


def evidence(gui,result):
    case=next(item for item in result['story']['actions'] if item['permission']['expectation']=='DENY')
    run=result['run_id'];gui._goto('/history?'+urlencode(dict(run_id=run,case_id=case['case_id'],tab='records')))
    gui.page.get_by_role('button',name='证据记录',exact=True).click()
    gui.page.get_by_role('button',name='查看必要证明记录',exact=True).first.click()
    panel=gui.page.get_by_role('region',name='怎样验证这项要求')
    expect(panel.get_by_role('heading',name='怎样取得这条证据',exact=True)).to_be_visible(timeout=60_000)
    expect(panel.get_by_role('heading',name='为什么得到这个判断',exact=True)).to_be_visible()
    links=panel.locator('details').filter(has_text='打开这条封存片段')
    expect(links).to_have_count(1);links.first.locator('summary').click();expect(links.first.locator('pre')).to_be_visible()
    gui.capture('gallery-evidence')
    gui._mark('evidence-reading')
    gui.page.reload();expect(panel.get_by_role('heading',name='怎样取得这条证据',exact=True)).to_be_visible(timeout=60_000);gui._mark('evidence-deep-link')
    gui.page.locator('.result-location').get_by_role('button',name='检查历史',exact=True).click()
    expect(gui.page.get_by_role('heading',name='检查历史',exact=True)).to_be_visible()
    expect(gui.page.get_by_role('navigation',name='历史查看方式')).to_have_count(0)
    gui._mark('single-history')
