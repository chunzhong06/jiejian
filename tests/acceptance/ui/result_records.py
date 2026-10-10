# 从协议展示夹具验证生产结果页面；验证布局和定位，不把模拟响应当作实际权限实验。
import json
from types import SimpleNamespace
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import expect
from product.backend.workflows.checks.reading.story import CheckStoryBuilder
from product.backend.workflows.checks.reading.records import record_index,record_view
from tests.fixtures.checks.reading import reading_package


def verify_result_records(browser,origin,out,report,*,from_history=False):
    package=reading_package();story=CheckStoryBuilder(SimpleNamespace(package=lambda _:package)).build(package.result.run_id,include_repair=False).model_dump(mode='json')
    project=dict(project_id=package.request.project_id,name='证据阅读布局',status='READY',target_type='WEB')
    document=next(item for item in package.evidence if item.case.permission.expectation=='DENY')
    case=document.case.case_id;run=document.run_id;evidence_id=document.evidence_id
    state=dict(run=dict(run_id=run,project_id=project['project_id'],lifecycle='COMPLETED',verdict='BLOCK',policy_epoch=1,plan_fingerprint='a'*64,created_at_us=1,finished_at_us=20),job=None,progress=None,result_integrity='VALID')
    for width,theme in [(2560,'light'),(2560,'dark'),(1280,'light'),(600,'dark')]:
        def api(route):
            url=urlparse(route.request.url);path=url.path;query=parse_qs(url.query)
            if route.request.method!='GET':report['writes'].append(path);route.abort();return
            if path=='/api/projects':data=[project]
            elif path.endswith('/check-history/rules'):
                permission=document.case.permission
                data=dict(project_id=project['project_id'],items=[dict(intent_id=permission.intent_id,revision=permission.revision,intent_hash=permission.intent_hash,
                    expectation=permission.expectation,effective_state='ACTIVE',relation=permission.relation,action_label='开放项目资料',subject_label='评审账号',owner_label='项目负责人',
                    latest_run_id=run,case_results=[dict(case_id=case,verdict='VULNERABLE')],result_integrity='VALID',index_matches=True)],next_cursor=None,
                    coverage=dict(project_id=project['project_id'],checkpoint=0,generation=0,processed=0,failed=0,missing=1,status='NEEDS_SCAN'))
            elif path.endswith('/check-history'):
                data=dict(project_id=project['project_id'],items=[dict(status=state,action_labels=['开放项目资料'],change_id=None,source_run_id=None,
                    matching_cases=[case],matching_verdicts=['VULNERABLE'])],next_cursor=None)
            elif path.endswith('/workspace'):data=dict(project=project,connection=dict(endpoint_status='CONFIRMED',source_analysis_status='COMPLETED'),actors=[],actions=[],areas=[],primary_task=None,active_check=None,latest_result=state)
            elif '/records' in path:
                ref=path.split('/evidence/')[1].split('/')[0]
                data=(record_index(package,ref,query['case_id'][0]) if path.endswith('/records') else record_view(package,ref,query['case_id'][0],path.rsplit('/',1)[1])).model_dump(mode='json')
            elif '/evidence/' in path:data=next(item for item in package.evidence if item.evidence_id==path.rsplit('/',1)[1]).model_dump(mode='json')
            elif path.endswith('/result-story'):data=story
            elif path.endswith('/runs/'+run):data=state
            elif path.endswith('/runs'):data=[state]
            elif path.endswith('/check-preview'):data=dict(project_id=project['project_id'],can_execute=False,gaps=[],actions=[])
            elif path=='/api/mcp/access':data=dict(paired=False,connection_state='UNPAIRED',project_grants=[],enabled=False)
            elif path=='/api/llm/profiles':data=[]
            elif path=='/api/llm/settings':data=dict(enabled=False,default_profile_name=None,updated_at_us=0)
            elif path=='/api/system/status':data=dict(api='available',worker='running',browser='available',version='1.2.0')
            else:data=dict(available=True,active=False,project_id=None,lifecycle='NOT_STARTED')
            route.fulfill(status=200,content_type='application/json',body=json.dumps(dict(schema_version='1',data=data)))
        context=browser.new_context(viewport=dict(width=width,height=1200),reduced_motion='reduce')
        try:
            context.add_init_script('localStorage.setItem("jiejian.project",'+json.dumps(json.dumps(project))+');localStorage.setItem("jiejian.theme",'+json.dumps(theme)+');')
            page=context.new_page();page.route('**/api/**',api);page.on('pageerror',lambda error:report['errors'].append(str(error)))
            if from_history:
                page.goto(origin+'/#/history')
                expect(page.get_by_role('navigation',name='检查导航')).to_be_visible()
                expect(page.get_by_role('heading',name='检查历史',exact=True)).to_be_visible()
                row=page.locator('.history-record');expect(row).to_be_visible()
                expect(page.get_by_text('部分旧记录尚未支持按规则筛选',exact=True)).to_be_visible()
                expect(page.get_by_role('navigation',name='历史查看方式')).to_have_count(0)
                if width>=1000:
                    aligned=page.locator('.history-records').evaluate("""e=>{const c=x=>{const r=x.getBoundingClientRect();return r.left+r.width/2};return [2,3,4].map(n=>Math.abs(c(e.querySelector('.history-columns>:nth-child('+n+')'))-c(e.querySelector('.history-record>:nth-child('+n+')'))))}""")
                    assert all(delta<1 for delta in aligned),aligned
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                page.screenshot(path=str(out/f'history-{width}-{theme}.png'),full_page=True)
                page.get_by_role('combobox',name='筛选权限规则',exact=True).press('ArrowDown')
                page.get_by_text(f'评审账号对项目负责人拥有的资源，不得开放项目资料 · 修订 {document.case.permission.revision}',exact=True).click()
                expect(page.get_by_text('含权限问题',exact=True)).to_be_visible()
                row.focus();page.keyboard.press('Enter')
            else:page.goto(origin+f'/#/tests?run_id={run}&case_id={case}')
            expect(page.get_by_role('navigation',name='检查项详情')).to_be_visible()
            facts_width=page.locator('.result-investigation-body').evaluate('(e)=>e.getBoundingClientRect().width')
            page.get_by_role('button',name='证据记录',exact=True).click()
            body=page.locator('.result-records-body');expect(body).to_be_visible()
            if width==2560:assert body.evaluate('(e)=>e.getBoundingClientRect().width')<facts_width
            page.get_by_role('button',name='查看必要证明记录',exact=True).click()
            panel=page.get_by_role('region',name='怎样验证这项要求');expect(panel).to_be_visible()
            expect(page.get_by_role('button',name='Agent 协助',exact=True)).to_have_count(1)
            expect(panel.get_by_role('heading',name='怎样取得这条证据')).to_be_visible()
            expect(panel.get_by_role('heading',name='为什么得到这个判断')).to_be_visible()
            expect(panel.get_by_text('之后：评审可访问',exact=True)).to_be_visible()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            page.screenshot(path=str(out/f'evidence-reading-{width}-{theme}.png'),full_page=True)
            link=panel.get_by_role('region',name='对应的原始记录').get_by_role('button',name='第 1 次独立提交',exact=True)
            link.focus();page.keyboard.press('Enter')
            expect(panel.get_by_role('heading',name='第 1 次独立提交',exact=True)).to_be_visible()
            assert 'record_id=' in page.url and 'evidence_id=' in page.url
            page.reload();expect(panel.get_by_role('heading',name='第 1 次独立提交',exact=True)).to_be_visible()
            panel.get_by_text('打开这条封存片段',exact=True).click();expect(panel.locator('pre').last).to_contain_text('commit-1')
            page.get_by_role('button',name='← 返回证据目录',exact=True).click()
            page.get_by_role('button',name='执行过程',exact=True).click()
            node=page.get_by_role('button',name='查看持久业务变化的发布证据',exact=True)
            node.click();expect(panel.get_by_role('heading',name='提交业务变化',exact=True)).to_be_visible()
            if from_history:
                page.locator('.result-location').get_by_role('button',name='检查历史',exact=True).click()
                expect(page.get_by_role('combobox',name='筛选权限规则')).to_be_visible()
                assert 'intent_id=' in page.url
                expect(page.get_by_role('region',name='历史检查列表')).to_be_visible()
                page.get_by_role('button',name='清除筛选',exact=True).click()
                assert 'intent_id=' not in page.url
                page.screenshot(path=str(out/f'history-return-{width}-{theme}.png'),full_page=True)
            report['checks'].append(dict(width=width,theme=theme,records_compact=True,deep_link_reload=True,keyboard=True,fragment=True,overflow=False))
        finally:context.close()
