# 仅验证当前生产前端的通知交互与维护标题栏；接口状态模拟，不启动真实检查或执行清理。
import json
from pathlib import Path
from functools import partial
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from threading import Thread
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect

from uuid import uuid4
import platform
from tests.support.verification.reporting import write_report


def run(root: Path) -> int:
    out=root/"var/audit/testing"/("browser-"+uuid4().hex);out.mkdir(parents=True)
    receipt=json.loads((root/'var/runtime/source/receipt.json').read_text(encoding='utf-8-sig'))
    project={'project_id':'ui-check','name':'通知局部验证','status':'READY','target_type':'WEB'}
    active={'run':{'project_id':'ui-check','run_id':'ui-run','lifecycle':'RUNNING','verdict':None,'plan_fingerprint':'x','policy_epoch':1,'created_at_us':1,'finished_at_us':None},'progress':None,'job':None,'result_integrity':'NOT_PUBLISHED'}
    report={'scope':'production frontend with mocked read-only responses','checks':[],'errors':[],'writes':[]}
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(root/'var/runtime/frontend')))
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=receipt['playwright']['executable'],headless=True)
            try:
                for width,theme in [(1280,'light'),(1280,'dark'),(390,'light'),(390,'dark')]:
                    state={'done':False,'reads':0}
                    def api(route):
                        path=urlparse(route.request.url).path
                        if route.request.method!='GET':report['writes'].append(path);route.abort();return
                        result={**active,'run':{**active['run'],'lifecycle':'COMPLETED','verdict':'PASS'},'result_integrity':'VALID'} if state['done'] else active
                        if path=='/api/projects':data=[project]
                        elif path=='/api/llm/profiles':data=[]
                        elif path=='/api/llm/settings':data={'enabled':False,'default_profile_name':None,'updated_at_us':0}
                        elif path=='/api/system/status':data={'api':'available','worker':'running','browser':'available','version':'1.1.14'}
                        elif path=='/api/system/maintenance':data={'schema_version':'1','entries':{key:{'path':'var/test','bytes':0,'files':0} for key in ['assistant','logs','temporary']},'protected':{'data':'var/data'}}
                        elif path=='/api/mcp/access':data={'paired':False,'connection_state':'UNPAIRED','project_grants':[],'enabled':False}
                        elif path.endswith('/workspace'):data={'project':project,'connection':{'endpoint_status':'CONFIRMED','source_analysis_status':'COMPLETED'},'actors':[],'actions':[],'areas':[],'primary_task':None,'active_check':None if state['done'] else active,'latest_result':None}
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
                    header=page.locator('.runtime-maintenance > .ant-card-head')
                    button=header.get_by_role('button',name='刷新状态',exact=True)
                    button.click();expect(button).to_be_enabled()
                    geometry=header.evaluate('''e=>{const h=e.getBoundingClientRect(),b=e.querySelector('button').getBoundingClientRect();return {top:b.top-h.top,bottom:h.bottom-b.bottom,inside:b.left>=h.left&&b.right<=h.right,overflow:document.documentElement.scrollWidth>innerWidth+1}}''')
                    assert geometry['top']>=15 and geometry['bottom']>=15 and geometry['inside'] and not geometry['overflow'],geometry
                    header.screenshot(path=str(out/f'header-{width}-{theme}.png'))
                    state['done']=True
                    expect(toast).to_be_visible(timeout=8000)
                    expect(toast).to_contain_text('检查完成，权限验证通过')
                    expect(toast.get_by_role('button',name='查看结果',exact=True)).to_be_visible()
                    toast.screenshot(path=str(out/f'completion-{width}-{theme}.png'))
                    page.get_by_role('button',name='关闭检查提示',exact=True).click();expect(toast).to_have_count(0)
                    assert state['reads']>=2
                    report['checks'].append({'width':width,'theme':theme,'progress_closed_and_completion_reappeared':True,'header':geometry})
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
                    start=ep.get_by_role('button',name='接入自己的应用',exact=True)
                    expect(start).to_be_visible()
                    assert ep.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    ep.screenshot(path=str(out/f'workspace-{width}-{theme}.png'),full_page=True)
                    start.click()
                    alert=ep.locator('.ant-alert-with-description').filter(has_text='接入前，请先在本机启动应用')
                    expect(alert).to_be_visible()
                    offset=alert.evaluate("e=>{const i=e.querySelector('.ant-alert-icon svg').getBoundingClientRect(),t=e.querySelector('.ant-alert-message'),b=t.getBoundingClientRect();return Math.abs(i.y+i.height/2-b.y-parseFloat(getComputedStyle(t).lineHeight)/2)}")
                    assert offset<1.5
                    ep.screenshot(path=str(out/f'access-{width}-{theme}.png'),full_page=True)
                    report['checks'].append({'width':width,'theme':theme,'pages':['system','workspace','application-setup'],'icon_offset':offset})
                    empty.close()
                assert not report['errors'] and not report['writes'],report
                report['status']='PASSED'
                report['browser_version']=browser.version
                report['platform']=platform.platform()
            finally:browser.close()
    finally:
        server.shutdown();server.server_close();thread.join(3)
        write_report(out/'report.json', {'schema_version':'1',**report})
    print('浏览器验收报告：'+str(out/'report.json'))
    return 0
