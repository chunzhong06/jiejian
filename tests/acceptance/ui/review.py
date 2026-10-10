# 验证生产前端的通知、权限行可见反馈与清理预览；不执行业务写入或清理。
import json
import re
import time
from pathlib import Path
from functools import partial
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from threading import Thread
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect

from uuid import uuid4
import platform
from tests.support.verification.reporting import write_report
from tests.acceptance.ui.hover_feedback import permission_editor, verify_permission_feedback
from tests.acceptance.ui.check_process_and_access import verify_check_process_and_access, verify_source_and_assist
from tests.acceptance.ui.material_suggestions import verify_material_suggestions
from tests.acceptance.ui.reference_files import verify_reference_files
from tests.acceptance.ui.result_records import verify_result_records


def run(root: Path, *, scopes=None, materials_only=False, references_only=False, records_only=False, history_only=False, runtime_dir=None) -> int:
    from tests.support.verification.catalog import ui_scopes
    legacy = [name for name, enabled in [("materials", materials_only), ("references", references_only), ("results", records_only), ("history", history_only)] if enabled]
    selected = set(ui_scopes(root, list(scopes or legacy), []))
    if selected - {"core", "process", "materials", "references", "results", "history"}:
        raise ValueError("UI_SCOPE_WITHOUT_RUNNER")
    started = time.monotonic()
    out=root/"var/audit/testing"/("browser-"+uuid4().hex);out.mkdir(parents=True)
    runtime=Path(runtime_dir) if runtime_dir is not None else root/'var/runtime'
    receipt=json.loads((runtime/'source/receipt.json').read_text(encoding='utf-8-sig'))
    project={'project_id':'ui-check','name':'通知局部验证','status':'READY','target_type':'WEB'}
    active={'run':{'project_id':'ui-check','run_id':'ui-run','lifecycle':'RUNNING','verdict':None,'plan_fingerprint':'x','policy_epoch':1,'created_at_us':1,'finished_at_us':None},'progress':None,'job':None,'result_integrity':'NOT_PUBLISHED'}
    maintenance={'schema_version':'1','entries':{key:{'path':'var/test','bytes':0,'files':0} for key in ['assistant','logs','temporary']},'protected':{'data':'var/data'},'inventory':[
        {'category':'builds','label':'前端构建','relative_path':'共享启动目录/frontend/builds/previous-version-with-long-id','state':'CLEANABLE','reason':'启动登记且无引用','bytes':22000000,'files':6},
        {'category':'builds','label':'当前前端','relative_path':'runtime/frontend','state':'PROTECTED','reason':'当前服务使用','bytes':None,'files':None},
        {'category':'temporary','label':'未登记文件','relative_path':'temp/manual-file','state':'UNKNOWN','reason':'没有生成方登记','bytes':None,'files':None}]}
    manifest=json.loads((runtime/'frontend/frontend-manifest.json').read_text(encoding='utf-8'))
    report={'status':'RUNNING','scope':'production frontend with mocked read-only responses','selected_scopes':sorted(selected),
            'build_id':manifest['build_id'],'visual_acceptance':'NOT_REVIEWED','checks':[],'errors':[],'writes':[]}
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(runtime/'frontend')))
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=receipt['playwright']['executable'],headless=True)
            try:
                for width,theme in ([(1280,'light'),(1280,'dark'),(390,'light'),(390,'dark')] if 'core' in selected else []):
                    state={'done':False,'reads':0}
                    def api(route):
                        path=urlparse(route.request.url).path
                        if route.request.method!='GET':
                            body=route.request.post_data_json
                            if path=='/api/system/maintenance/clear-all' and body.get('dry_run') is True and body.get('confirmed') is False:
                                data={'schema_version':'1','plan_id':'ui-plan','scope':'clear-all','operation':'clear-all','generated_at_us':1,'expires_at_us':999999999,'dry_run':True,'estimated_bytes':22000000,'targets':[{'item_id':'old-build','label':'前端构建','relative_path':maintenance['inventory'][0]['relative_path'],'estimated_bytes':22000000}], 'removed':[],'results':[],'counts':{'DELETED':0,'ALREADY_MISSING':0,'SKIPPED_IN_USE':0,'SKIPPED_CHANGED':0,'FAILED':0},'protected':maintenance['protected'],'status':maintenance}
                                route.fulfill(status=200,content_type='application/json',body=json.dumps({'schema_version':'1','data':data}));return
                            report['writes'].append(path);route.abort();return
                        result={**active,'run':{**active['run'],'lifecycle':'COMPLETED','verdict':'PASS'},'result_integrity':'VALID'} if state['done'] else active
                        if path=='/api/projects':data=[project]
                        elif path=='/api/llm/profiles':data=[]
                        elif path=='/api/llm/settings':data={'enabled':False,'default_profile_name':None,'updated_at_us':0}
                        elif path=='/api/system/status':data={'api':'available','worker':'running','browser':'available','version':'1.1.14'}
                        elif path=='/api/system/maintenance':data=maintenance
                        elif path=='/api/mcp/access':data={'paired':True,'connection_state':'CONNECTED','project_grants':[],'accepting_connections':True,'client_connected':True,'client_name':'测试客户端','endpoint':'http://127.0.0.1/mcp','default_level':'READ'}
                        elif path.endswith('/workspace'):data={'project':project,'connection':{'endpoint_status':'CONFIRMED','source_analysis_status':'COMPLETED'},'actors':[],'actions':[],'areas':[],'primary_task':None,'active_check':None if state['done'] else active,'latest_result':None}
                        elif path.endswith('/business-boundaries/editor'):data=permission_editor(project['project_id'])
                        elif path.endswith('/rule-context'):data={'project_id':project['project_id'],'candidates':[],'next_offset':None}
                        elif path=='/api/runs/ui-run':state['reads']+=1;data=result
                        else:data={'available':True,'active':False,'display_name':'协作空间','project_id':None,'lifecycle':'NOT_STARTED'}
                        route.fulfill(status=200,content_type='application/json',body=json.dumps({'schema_version':'1','data':data}))
                    context=browser.new_context(viewport={'width':width,'height':1000},reduced_motion='reduce')
                    context.add_init_script('localStorage.setItem("jiejian.project",'+json.dumps(json.dumps(project))+');localStorage.setItem("jiejian.theme",'+json.dumps(theme)+');')
                    page=context.new_page();page.route('**/api/**',api);page.on('pageerror',lambda e:report['errors'].append(type(e).__name__))
                    page.goto(f'http://127.0.0.1:{server.server_port}/#/settings/system')
                    toast=page.get_by_role('region',name='检查动态');expect(toast).to_be_visible()
                    page.get_by_role('button',name='关闭检查提示',exact=True).click();expect(toast).to_have_count(0)
                    # 刷新维护数据仍能操作，关闭只影响浮层，不调用取消或重新提交接口。
                    header=page.locator('.maintenance-heading')
                    button=header.get_by_role('button',name='重新扫描',exact=True)
                    button.click();expect(button).to_be_enabled()
                    geometry=header.evaluate('''e=>{const h=e.getBoundingClientRect(),b=e.querySelector('button').getBoundingClientRect();return {top:b.top-h.top,bottom:h.bottom-b.bottom,inside:b.left>=h.left&&b.right<=h.right,overflow:document.documentElement.scrollWidth>innerWidth+1}}''')
                    assert geometry['top']>=0 and geometry['bottom']>=0 and geometry['inside'] and not geometry['overflow'],geometry
                    header.screenshot(path=str(out/f'header-{width}-{theme}.png'))
                    page.get_by_role('button',name='预览清理',exact=True).click()
                    dialog=page.get_by_role('dialog',name='确认清理范围');expect(dialog).to_be_visible()
                    dialog.get_by_role('checkbox').uncheck()
                    expect(dialog.get_by_role('button',name='清理所选')).to_be_disabled()
                    dialog.screenshot(path=str(out/f'cleanup-preview-{width}-{theme}.png'))
                    dialog.get_by_role('button',name=re.compile(r'取\s*消')).click()
                    state['done']=True
                    expect(toast).to_be_visible(timeout=8000)
                    expect(toast).to_contain_text('检查完成，权限验证通过')
                    expect(toast.get_by_role('button',name='查看结果',exact=True)).to_be_visible()
                    toast.screenshot(path=str(out/f'completion-{width}-{theme}.png'))
                    page.get_by_role('button',name='关闭检查提示',exact=True).click();expect(toast).to_have_count(0)
                    assert state['reads']>=2
                    page.emulate_media(reduced_motion='no-preference')
                    page.goto(f'http://127.0.0.1:{server.server_port}/#/permissions')
                    feedback=verify_permission_feedback(page,out,f'{width}-{theme}')
                    report['checks'].append({'width':width,'theme':theme,'permission_feedback':feedback})
                    # 复现用户报告的版本说明占位和二级导航远离正文；只读三种视图留图审阅。
                    page.emulate_media(reduced_motion='reduce')
                    for title in ['权限规则','业务动作','业务角色']:
                        page.get_by_role('navigation',name='权限要求视图').get_by_role('button',name=title,exact=True).click()
                        expect(page.get_by_role('textbox',name='搜索业务角色' if title=='业务角色' else '搜索业务动作')).to_be_visible()
                        if title!='权限规则':
                            # 标签与右侧第一行文字对齐，长规则换行也不把标签移到整段中央。
                            offsets=page.locator('.definition-linked-rule').evaluate_all('''rows=>rows.map(row=>{
                              const box=element=>{const range=document.createRange();range.selectNodeContents(element);return range.getClientRects()[0]};
                              const badge=box(row.firstElementChild),text=box(row.lastElementChild);
                              return Math.abs(badge.y+badge.height/2-text.y-text.height/2);
                            })''')
                            if not offsets or max(offsets)>2:
                                page.screenshot(path=str(out/f'role-alignment-failure-{width}-{theme}.png'),full_page=True)
                                styles=page.locator('.definition-linked-rule').first.evaluate('''row=>[row,...row.children].map(e=>({font:getComputedStyle(e).font,line:getComputedStyle(e).lineHeight,align:getComputedStyle(e).alignItems,self:getComputedStyle(e).alignSelf,box:e.getBoundingClientRect().toJSON()}))''')
                                raise AssertionError(('RULE_TEXT_ALIGNMENT',offsets,styles))
                            report['checks'].append({'width':width,'theme':theme,'view':title,'rule_text_offsets':offsets})
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                        page.evaluate('window.scrollTo(0,0)')
                        page.screenshot(path=str(out/f'permissions-{title}-{width}-{theme}.png'),full_page=True)
                    page.goto(f'http://127.0.0.1:{server.server_port}/#/tools')
                    manage=page.get_by_role('button',name='管理连接',exact=True)
                    expect(manage).to_be_visible()
                    manage.click()
                    management=page.get_by_role('region',name='管理连接',exact=True)
                    expect(management).to_be_visible()
                    distance=management.evaluate("e=>e.getBoundingClientRect().top-document.querySelector('.connection-header').getBoundingClientRect().bottom")
                    assert 0<=distance<=48, ('CONNECTION_MANAGEMENT_TOO_FAR',distance)
                    page.screenshot(path=str(out/f'connection-management-{width}-{theme}.png'),full_page=True)
                    report['checks'].append({'width':width,'theme':theme,'connection_management_gap':distance,'permission_views':3})
                    report['checks'].append({'width':width,'theme':theme,'progress_closed_and_completion_reappeared':True,'header':geometry})
                    page.evaluate('window.scrollTo(0,0)');page.wait_for_timeout(300)
                    page.screenshot(path=str(out/f'system-{width}-{theme}.png'), full_page=True)
                    context.close()
                    # 新上下文代表尚未接入应用的用户；直接使用产品页面和控件，不增加测试入口。
                    empty=browser.new_context(viewport={'width':width,'height':1000},reduced_motion='reduce')
                    empty.add_init_script('localStorage.setItem("jiejian.theme",'+json.dumps(theme)+');')
                    ep=empty.new_page()
                    def empty_api(route):
                        if urlparse(route.request.url).path=='/api/projects':
                            route.fulfill(status=200,content_type='application/json',body=json.dumps({'schema_version':'1','data':[]}))
                        else:api(route)
                    ep.route('**/api/**',empty_api)
                    ep.on('pageerror',lambda e:report['errors'].append(type(e).__name__))
                    ep.goto(f'http://127.0.0.1:{server.server_port}/#/workspace')
                    start=ep.get_by_role('button',name='选择应用目录',exact=True)
                    expect(start).to_be_visible()
                    assert ep.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    ep.screenshot(path=str(out/f'workspace-{width}-{theme}.png'),full_page=True)
                    start.click()
                    alert=ep.locator('.ant-alert-with-description').filter(has_text='应用还没运行，也可以先整理规则')
                    expect(alert).to_be_visible()
                    offset=alert.evaluate("e=>{const i=e.querySelector('.ant-alert-icon svg').getBoundingClientRect(),t=e.querySelector('.ant-alert-message'),b=t.getBoundingClientRect();return Math.abs(i.y+i.height/2-b.y-parseFloat(getComputedStyle(t).lineHeight)/2)}")
                    assert offset<1.5
                    ep.screenshot(path=str(out/f'access-{width}-{theme}.png'),full_page=True)
                    report['checks'].append({'width':width,'theme':theme,'pages':['system','workspace','application-setup'],'icon_offset':offset})
                    empty.close()
                if 'process' in selected:
                    verify_check_process_and_access(browser, f'http://127.0.0.1:{server.server_port}', out, report)
                    verify_source_and_assist(browser, f'http://127.0.0.1:{server.server_port}', out, report)
                if 'materials' in selected:verify_material_suggestions(browser, f'http://127.0.0.1:{server.server_port}', out, report)
                if 'references' in selected:verify_reference_files(browser,f'http://127.0.0.1:{server.server_port}',out,report)
                if selected & {'results','history'}:verify_result_records(browser,f'http://127.0.0.1:{server.server_port}',out,report,from_history='history' in selected)
                assert report['checks'] and not report['errors'] and not report['writes'],report
                report['status']='PASSED'
                report['browser_version']=browser.version
                report['platform']=platform.platform()
            finally:browser.close()
    except Exception as error:
        # 浏览器错误可能携带响应与用户输入，只保存类型；原堆栈仍在本地控制台。
        report.update(status='FAILED',failure_type=type(error).__name__)
        raise
    finally:
        server.shutdown();server.server_close();thread.join(3)
        report['seconds']=round(time.monotonic()-started,3)
        write_report(out/'report.json', {'schema_version':'1',**report})
    print('浏览器验收报告：'+str(out/'report.json'))
    return 0
