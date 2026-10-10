# 使用生产构建验证五类材料建议布局及精确返回；响应为本地只读夹具，不执行用户应用。
import json
import re
from copy import deepcopy
from urllib.parse import urlparse
from playwright.sync_api import expect


def verify_material_suggestions(browser,origin,out,report):
    for width,theme in [(2560,'light'),(2560,'dark'),(1280,'light'),(600,'dark')]:
        project={'project_id':'suggestion-ui','name':'资料协作应用','status':'READY','target_type':'WEB'}
        state={'approved':False,'stale':False,'missing':False}
        materials=[{'kind':'identity','account_requirement':'准备负责人和协作者两个独立的测试账号。'},
            {'kind':'execution','normal_steps':['打开测试项目的资料页。','使用负责人账号点击发布资料。']},
            {'kind':'resource','resource_concept':'建立仅用于测试的项目资料','fields':[{'field':'state','requirement':'初始值为草稿'}],
                'preparation_steps':['通过应用现有的创建入口建立一份合成资料，不需要等待真实生产内容。']},
            {'kind':'evidence','capability':'MANAGED_TRANSACTION_RECORDS','observable_result':'业务存储中的资料状态确实变成已发布。','field_hints':['state']},
            {'kind':'recovery','expected_state':'核对资料恢复到草稿，保留已有检查记录。'}]

        def suggestion():
            current=not state['stale']
            return {'state':'CURRENT' if current else 'STALE','current_basis_id':'psb_ui','latest_revision':1,'review_url':'#/tests?materials=1',
                'suggestion':{'project_id':project['project_id'],'suggestion_id':'psg_ui','revision':1,'basis_id':'psb_ui','submitted_via':'MCP',
                    'content':{'unresolved_questions':[], 'items':[{'item_id':str(index),'target':{'kind':'CANDIDATE','candidate_id':'rcd_ui','revision':2},
                        'material':material,'description':['核对需要哪些账号','演示正常业务操作','准备初始测试资料','确认用什么记录证明结果','准备恢复办法'][index],
                        'source':{'classification':'HYPOTHESIS','candidate_ids':[],'explanation':'按这次业务要求整理，实际字段仍需核对。'},
                        'handler':'USER' if index==0 else 'AGENT','depends_on':[],'gap':None} for index,material in enumerate(materials)]}},
                'items':[{'item_id':str(index),'current':current,'return_url':'#/tests?materials=1','source_locations':[],
                    'resolved_target':{'state':'APPROVED' if state['approved'] else 'WAITING_APPROVAL','action_id':'action-publish' if state['approved'] else None,
                        'action_revision':1 if state['approved'] else None,'action_label':'发布资料','actor_label':'项目负责人','effect_label':None}}
                    for index in range(5)]}

        action={'action_id':'action-publish','action_revision':1,'display_name':'发布资料','permissions':[], 'assurance_contract':{'allow_controls':[]},
            'preparation_complete':False,'reason_codes':[],
            'identity_requirements':{'status':'NEEDS_USER','reason_codes':[],'allocation_mode':'EXACT','slots':[{
                'requirement':{'slot_id':'owner','actor_id':'owner','actor_revision':1,'ordinal':1},'actor_display_name':'项目负责人',
                'test_identity_id':None,'status':'NEEDS_USER','reason_codes':[]}]},
            'execution':{'status':'SATISFIED','reason_codes':[]},'resources':[{'owner_slot_id':'owner','owner_test_identity_id':None,'status':'NEEDS_USER','reason_codes':[]}],
            'effect_evidence':[{'effect_id':'published','status':'NEEDS_USER','reason_codes':[]}],'recovery':{'status':'NEEDS_USER','reason_codes':[]}}

        def api(route):
            path=urlparse(route.request.url).path
            if route.request.method!='GET':report['writes'].append(path);route.abort();return
            if path=='/api/projects':data=[project]
            elif path.endswith('/workspace'):
                data={'project':project,'connection':{'endpoint_status':'NEEDS_CONFIRMATION','source_analysis_status':'COMPLETED'},
                    'actors':[],'actions':[],'areas':[],'primary_task':None,'active_check':None,'latest_result':None}
            elif path.endswith('/check-preview'):data={'project_id':project['project_id'],'can_execute':False,'gaps':[],'actions':[]}
            elif path.endswith('/runs'):data=[]
            elif path.endswith('/preparation/draft'):data={'schema_version':'1','revision':0,'action_id':None,'material':None}
            elif path.endswith('/preparation'):data={'project_id':project['project_id'],'preparation_complete':False,'actions':[action] if state['approved'] else []}
            elif path.endswith('/proof-preparation'):data={'project_id':project['project_id'],'basis_id':'pb_other',
                'suggestion_context':{'project_id':project['project_id'],'state':'CURRENT','basis_id':'psb_ui','latest':suggestion()}}
            elif '/proof-preparation/suggestions/' in path:
                if state['missing']:
                    route.fulfill(status=404,content_type='application/json',body=json.dumps({'schema_version':'1','error':{'code':'RECORD_NOT_FOUND','message':'记录不存在'}}));return
                data=suggestion()
            elif path=='/api/mcp/access':data={'paired':True,'accepting_connections':True,'connection_state':'CONNECTED','project_grants':[{'project_id':project['project_id'],'level':'READ'}]}
            elif path=='/api/llm/profiles':data=[]
            elif path=='/api/llm/settings':data={'enabled':False,'default_profile_name':None,'updated_at_us':0}
            elif path=='/api/system/status':data={'api':'available','worker':'running','browser':'available','version':'1.2.0'}
            else:data={'available':True,'active':False,'display_name':'协作空间','project_id':None,'lifecycle':'NOT_STARTED'}
            route.fulfill(status=200,content_type='application/json',body=json.dumps({'schema_version':'1','data':deepcopy(data)}))

        context=browser.new_context(viewport={'width':width,'height':1440 if width==2560 else 1000},reduced_motion='reduce')
        try:
            context.add_init_script('localStorage.setItem("jiejian.project",'+json.dumps(json.dumps(project))+');localStorage.setItem("jiejian.theme",'+json.dumps(theme)+');')
            page=context.new_page();page.route('**/api/**',api);page.on('pageerror',lambda error:report['errors'].append(type(error).__name__))
            address=origin+'/#/tests?materials=1&suggestion_id=psg_ui&suggestion_revision=1&material_kind=resource'
            page.goto(address)
            table=page.get_by_role('table',name='预先整理的材料',exact=True)
            expect(table).to_be_visible();expect(table.get_by_role('row')).to_have_count(5 if width<700 else 6)
            expect(table.get_by_text(materials[2]['preparation_steps'][0],exact=True)).to_be_visible()
            if width>=700:
                centers=table.evaluate("""e=>{const center=x=>{const r=x.getBoundingClientRect();return r.left+r.width/2};
                    return [2,4].map(n=>Math.abs(center(e.querySelector('.material-table-head>span:nth-child('+n+')'))-center(e.querySelector('.material-row>span:nth-child('+n+')'))))}""")
                assert all(delta<1 for delta in centers),centers
            expect(page.get_by_role('button',name='Agent 协助',exact=True)).to_have_count(1)
            expect(page.get_by_role('button',name='读取建议',exact=True)).to_have_count(1)
            page.get_by_role('button',name='Agent 协助',exact=True).click()
            page.get_by_text('查看协助请求',exact=True).click()
            expect(page.locator('.agent-assist-panel pre')).to_contain_text('jiejian_preparation_suggestion_save')
            expect(page.locator('.agent-assist-panel pre')).to_contain_text('psb_ui')
            expect(page.get_by_role('button',name='复制协助请求',exact=True)).to_be_disabled()
            page.get_by_role('button',name='Agent 协助',exact=True).click()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            page.evaluate('window.scrollTo(0,0)');page.wait_for_timeout(200)
            page.screenshot(path=str(out/f'material-suggestions-pending-{width}-{theme}.png'),full_page=True)
            state['approved']=True;page.reload()
            table=page.get_by_role('table',name='检查材料清单',exact=True);expect(table).to_be_visible()
            expect(page.get_by_role('table',name='预先整理的材料',exact=True)).to_have_count(0)
            expect(table.get_by_text(materials[2]['preparation_steps'][0],exact=True)).to_be_visible()
            row=table.get_by_role('row').filter(has_text='动作录制')
            row.get_by_role('button',name='查看',exact=True).focus()
            page.keyboard.press('Enter')
            expect(table.get_by_text(materials[1]['normal_steps'][0],exact=True)).to_be_visible()
            page.wait_for_timeout(350)
            layout=page.evaluate("""()=>{const rect=s=>document.querySelector(s).getBoundingClientRect();
                const copy=rect('.material-focus-copy'),next=rect('.material-focus-next'),main=rect('.material-suggestion-content'),basis=rect('.material-suggestion-basis');
                const header=rect('.editorial-header'),table=rect('.material-table'),picker=rect('.materials-action-picker'),tools=rect('.agent-assist-toggle');
                const revision=rect('.materials-context>.editorial-muted'),notes=rect('.material-suggestion-notes'),detail=rect('.material-row-detail');
                return {taskSideBySide:next.left>=copy.right,taskStacked:next.top>=copy.bottom,
                    adviceSideBySide:basis.left>=main.right,adviceStacked:basis.top>=main.bottom,
                    revisionCenterDelta:Math.abs(picker.top+picker.height/2-revision.top-revision.height/2),
                    notesCenterDelta:Math.abs(notes.left+notes.width/2-detail.left-detail.width/2),notesWidth:notes.width,
                    headerDelta:Math.abs(header.left-table.left),toolsTogether:tools.top<picker.bottom&&tools.bottom>picker.top}}""")
            assert layout['headerDelta']<1,layout
            assert layout['revisionCenterDelta']<1 and layout['notesCenterDelta']<1 and layout['notesWidth']<=704,layout
            assert layout['taskSideBySide' if width>=700 else 'taskStacked'],layout
            assert layout['adviceSideBySide' if width>=700 else 'adviceStacked'],layout
            if width>=1280:assert layout['toolsTogether'],layout
            if width==1280:
                page.locator('.agent-assist-heading').screenshot(path=str(out/'material-toolbar-aligned.png'))
                page.locator('.material-suggestion-notes').screenshot(path=str(out/'material-advice-compact.png'))
            # 键盘会把操作行滚入视口；全页截图前回顶部，使粘性导航留在真实页首。
            page.evaluate('window.scrollTo(0,0)');page.wait_for_timeout(200)
            page.screenshot(path=str(out/f'material-suggestions-approved-{width}-{theme}.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            if width==1280:
                # 检查真实中间帧；折叠后稳定容器仍须衔接高度，快速反向不能留下固定高度。
                page.emulate_media(reduced_motion='no-preference')
                expect(page.locator('html')).to_have_attribute('data-motion','full')
                row.get_by_role('button',name='收起',exact=True).click()
                page.wait_for_function("Array.from(document.querySelectorAll('.material-group')).some(e=>e.getAnimations().some(a=>a.effect.getKeyframes().some(f=>f.height)))",timeout=3000)
                row.get_by_role('button',name='查看',exact=True).click()
                expect(table.get_by_text(materials[1]['normal_steps'][0],exact=True)).to_be_visible()
                page.wait_for_timeout(350)
                assert table.evaluate("e=>!Array.from(e.querySelectorAll('.material-group')).some(n=>n.style.height)")
                page.emulate_media(reduced_motion='reduce')
                expect(page.locator('html')).to_have_attribute('data-motion','soft')
                row.get_by_role('button',name='收起',exact=True).click()
                page.wait_for_timeout(40)
                assert table.evaluate("e=>!e.getAnimations({subtree:true}).some(a=>a.effect.getKeyframes().some(f=>f.height||f.transform))")
            state['stale']=True;page.reload()
            expect(page.get_by_text('规则、源码或材料已经变化，以下原建议仅供回看；请让 Agent 按当前依据重新整理。',exact=True)).to_be_visible()
            state['missing']=True;page.reload()
            expect(page.get_by_text('无法读取指定的材料建议。请核对原链接，或返回当前材料。',exact=True)).to_be_visible()
            expect(page.get_by_role('table',name='检查材料清单',exact=True)).to_be_visible()
            expect(page.get_by_text('核对需要哪些账号',exact=True)).to_have_count(0)
            page.get_by_role('button',name='返回当前材料',exact=True).click()
            expect(page).not_to_have_url(re.compile('suggestion_id='))
            report['checks'].append({'width':width,'theme':theme,'pages':['pending-rules','approved-materials','stale-advice','missing-exact-reference'],
                'keyboard_expansion':True,'layout':layout,'motion_checked':width==1280,'writes':0})
        finally:context.close()
