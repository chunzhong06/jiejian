# 核对生产前端的接入、检查阶段与协助入口；API由本地夹具拦截，不停止用户实例。
import json
import re
from copy import deepcopy
from urllib.parse import parse_qs, urlparse
from playwright.sync_api import expect
from tests.acceptance.ui.hover_feedback import permission_editor


def verify_check_process_and_access(browser, origin, out, report):
    for width, theme in [(1280, "light"), (600, "dark")]:
        project = {"project_id": "progress-ui", "name": "阶段与接入验证", "status": "READY", "target_type": "WEB", "official_sample": True}
        stage = {"name": "QUEUED", "stop_calls": 0, "sample": True}
        run = {"run_id": "progress-run", "project_id": project["project_id"], "lifecycle": "QUEUED",
               "verdict": None, "plan_fingerprint": "a" * 64, "policy_epoch": 2,
               "created_at_us": 1780000000000000, "finished_at_us": None}

        def status():
            queued = stage["name"] == "QUEUED"
            return {"run": {**run, "lifecycle": "QUEUED" if queued else "RUNNING"},
                    "job": {"job_id": "progress-job", "state": "QUEUED" if queued else "RUNNING", "attempt": 0 if queued else 1, "cancel_requested": False},
                    "progress": None if queued else {"phase": stage["name"], "completed_cases": 3 if stage["name"] == "FINALIZING" else 1 if stage["name"] == "EXECUTING" else 0,
                        "planned_cases": 3, "current_case": {"case_id": "case-control", "action_label": "导出项目资料", "expectation": "ALLOW",
                        "planned_subject_label": "项目负责人", "planned_resource_owner_label": "项目负责人", "resource_id": "test-resource", "effect_labels": ["交付包形成"]} if stage["name"] == "EXECUTING" else None},
                    "result_integrity": "NOT_PUBLISHED"}

        def api(route):
            target = urlparse(route.request.url).path
            if route.request.method != "GET":
                if target == "/api/experience/official-sample/stop":
                    stage["stop_calls"] += 1
                    assert route.request.post_data_json.get("operation_id")
                    stage["sample"] = False
                else:
                    report["writes"].append(target)
                    route.abort()
                    return
            if target == "/api/projects":
                data = [project]
            elif target == "/api/llm/profiles":
                data = []
            elif target == "/api/llm/settings":
                data = {"enabled": False, "default_profile_name": None, "updated_at_us": 0}
            elif target == "/api/system/status":
                data = {"api": "available", "worker": "running", "browser": "available", "version": "1.2.0"}
            elif target == "/api/mcp/access":
                data = {"paired": False, "connection_state": "UNPAIRED", "project_grants": [], "enabled": False}
            elif target.endswith("/workspace"):
                data = {"project": project, "connection": {"endpoint_status": "CONFIRMED", "source_analysis_status": "COMPLETED"},
                        "actors": [], "actions": [], "areas": [], "primary_task": None, "active_check": status(), "latest_result": None}
            elif target.endswith("/check-preview"):
                data = {"project_id": project["project_id"], "can_execute": True, "plan_fingerprint": "a" * 64, "action_count": 1, "case_count": 3,
                        "actions": [], "gaps": []}
            elif target.endswith("/runs"):
                data = [status()]
            elif target == "/api/runs/progress-run":
                data = status()
            elif target.startswith("/api/experience/official-sample"):
                data = {"available": True, "active": stage["sample"], "display_name": "协作空间", "project_id": project["project_id"],
                        "lifecycle": "RUNNING" if stage["sample"] else "STOPPED", "recovery_state": "OWNED_RUNNING" if stage["sample"] else "EXITED"}
            else:
                data = {}
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"schema_version": "1", "data": data}))

        context = browser.new_context(viewport={"width": width, "height": 1000}, reduced_motion="reduce")
        try:
            context.add_init_script('localStorage.setItem("jiejian.project",' + json.dumps(json.dumps(project)) + ');localStorage.setItem("jiejian.theme",' + json.dumps(theme) + ');')
            page = context.new_page()
            page.route("**/api/**", api)
            page.on("pageerror", lambda error: report["errors"].append(type(error).__name__))
            page.goto(origin + "/#/tests?run_id=progress-run")
            expected = [("QUEUED", "等待执行器领取"), ("PREPARING", "正在准备本轮检查"), ("EXECUTING", "正在执行并观察业务结果"), ("FINALIZING", "正在核验并发布结果")]
            for name, title in expected:
                stage["name"] = name
                if name != "QUEUED":
                    page.get_by_role("button", name="刷新检查结果", exact=True).click()
                expect(page.get_by_role("heading", name=title, exact=True)).to_be_visible()
                expect(page.get_by_text("尚未取得检查项进度", exact=True)).to_have_count(0)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
                page.locator(".check-run-process").screenshot(path=str(out / f"stages-{name}-{width}-{theme}.png"))
            page.get_by_role("button", name="查看等待阶段", exact=True).click()
            expect(page.get_by_role("heading", name="检查请求已保存", exact=True)).to_be_visible()
            page.get_by_role("button", name="查看准备阶段", exact=True).click()
            expect(page.get_by_text("3 项验证", exact=True)).to_be_visible()
            page.get_by_role("button", name="返回最新阶段", exact=True).click()
            expect(page.get_by_role("heading", name="正在核验并发布结果", exact=True)).to_be_visible()
            page.get_by_role("button", name="切换应用，当前：阶段与接入验证", exact=True).click()
            page.get_by_text("接入新应用", exact=True).click()
            expect(page.get_by_role("heading", name="接入本地应用", exact=True)).to_be_visible()
            expect(page.get_by_role("heading", name="选择应用文件夹", exact=True)).to_be_visible()
            expect(page.get_by_text("审阅已提供的权限提案", exact=True)).to_have_count(0)
            assert stage["stop_calls"] == 1
            assert page.url.endswith("#/application?new=1")
            assert page.evaluate('localStorage.getItem("jiejian.project")') is None
            page.screenshot(path=str(out / f"connect-new-{width}-{theme}.png"), full_page=True)
            report["checks"].append({"width": width, "theme": theme, "pages": ["check-progress-4-stages", "new-application"],
                                    "official_stop_mock_calls": stage["stop_calls"], "target_requests": 0})
        finally:
            context.close()


def verify_source_and_assist(browser, origin, out, report):
    for width, theme in [(2560, "light"), (2560, "dark"), (1280, "light"), (600, "dark")]:
        project = {"project_id": "source-ui", "name": "离线整理验证", "status": "DRAFT", "target_type": "WEB"}
        requests = []
        understanding = {"project_id": project["project_id"], "source_root": "D:/ui-fixture/source",
                         "confirmed_endpoint": None, "source_analysis_authorized": False, "source_fingerprint": None,
                         "analysis_completed_at_us": None, "role_candidates": [], "action_candidates": [], "revision": 0}
        candidate_id = 'rcd_' + '1' * 32
        permission = {'item_id':'p1', 'subject_actor_item_id':'member', 'resource_owner_actor_item_id':'member',
                      'business_action_item_id':'download', 'relation':'OWNS', 'protected_effect_item_ids':['received']}
        meaning = {'candidate':{'candidate_id':candidate_id, 'project_id':project['project_id'], 'revision':2,
            'basis_id':'rb_ui_current', 'submitted_via':'MCP', 'content':{'original_text':'成员可以预览公开内容，下载范围需要确认。',
            'actors':[{'item_id':'member','display_name':'成员'}],
            'actions':[{'item_id':'download','display_name':'下载展示版','effect_catalog':[{'item_id':'received','business_label':'展示版完整收到'}]}],
            'permissions':[{**permission,'expectation':'DENY'}], 'examples':[{'description':'成员下载公开展示版','permission_item_id':'p1','uncovered_reason':None}],
            'unresolved_questions':[], 'unsupported_constraints':[], 'scenarios':[{'scenario_id':'scene','scenario_fingerprint':'a'*64,
                'original_excerpt':'下载范围需要确认','question':'成员能否下载公开展示版？','options':[
                    {'option_id':'allow','label':'允许下载展示版','explanation':'可以离线查看公开内容。','replacements':[{**permission,'expectation':'ALLOW'}]},
                    {'option_id':'deny','label':'仅允许在线预览','explanation':'可以查看公开内容，不提供下载。','replacements':[{**permission,'expectation':'DENY'}]}]}]}},
            'assessment':'NEEDS_CHANGES','issues':[{'code':'NEEDS_DECISION','message':'含义仍待核对'}], 'decision':None,
            'proposal_id':None, 'scenario_decisions':[], 'reuse':{'message':'正式批准后再核对当前材料。','actions':[]}}
        old_meaning = deepcopy(meaning)
        old_meaning['candidate']['revision'] = 1
        old_meaning['candidate']['content']['scenarios'] = []
        old_meaning['candidate']['content']['unresolved_questions'] = ['成员能否下载公开展示版？']
        old_meaning['issues'] = [{'code':'NEEDS_CLARIFICATION','message':'成员能否下载公开展示版？'}]

        def api(route):
            target = urlparse(route.request.url).path
            requests.append(target)
            if route.request.method == 'POST' and target.endswith('/rule-preview'):
                data = {'project_id':project['project_id'], 'availability':'AVAILABLE',
                    'coverage':'ALLOW' if route.request.post_data_json.get('situation') else None, 'matches':[],
                    'actors':[{'id':'member','label':'成员'}],
                    'actions':[{'id':'download','label':'下载展示版','effects':[{'id':'received','label':'展示版完整收到'}]}]}
                route.fulfill(status=200, content_type='application/json', body=json.dumps({'schema_version':'1','data':data}))
                return
            if route.request.method != "GET":
                report["writes"].append(target)
                route.abort()
                return
            if target == "/api/projects":
                data = [project]
            elif target.endswith("/application-understanding"):
                data = understanding
            elif target.endswith("/workspace"):
                data = {"project": project, "connection": {"endpoint_status": "NEEDS_CONFIRMATION", "source_analysis_status": "NOT_AUTHORIZED"},
                        "actors": [], "actions": [], "areas": [], "primary_task": None, "active_check": None, "latest_result": None}
            elif target.endswith("/business-boundaries/editor"):
                data = permission_editor(project["project_id"])
            elif target.endswith("/rule-context"):
                data = {"project_id": project["project_id"], "basis_id": "rb_ui_current", "candidates": [], "next_offset": None}
            elif target.endswith('/rule-candidates/' + candidate_id):
                data = old_meaning if parse_qs(urlparse(route.request.url).query).get('revision') == ['1'] else meaning
            elif '/business-boundaries/rules/' in target:
                data = {'project_id':project['project_id'],'intent_id':'pin_'+'1'*32,'revision':1,'current':True,
                    'expectation':'ALLOW','sentence':'成员可以下载自己的公开展示版。','action_id':'download','action_revision':1,
                    'action_label':'下载展示版','effects':[{'effect_id':'received','label':'展示版完整收到','description':'核对当前公开内容是否完整收到。'}],
                    'approval':{'approved_at_us':1,'reason':'本机确认','approved_by':'用户'},'materials':[],
                    'preparation_complete':False,'latest_result':None,'history_has_more':False,'unreadable_history':False,
                    'preparation_url':'/tests?materials=1','check_url':'/tests','history_url':'/history'}
            elif target == "/api/mcp/access":
                data = {"schema_version": "1", "paired": True, "accepting_connections": True, "endpoint": origin + "/mcp",
                        "connection_state": "CREDENTIAL_READY", "default_level": "READ", "project_grants": [],
                        "client_connected": False, "client_name": None, "client_version": None,
                        "last_seen_at_us": None, "last_authenticated_at_us": None, "last_auth_failure_at_us": None}
            elif target == "/api/llm/profiles":
                data = []
            elif target == "/api/llm/settings":
                data = {"enabled": False, "default_profile_name": None, "updated_at_us": 0}
            elif target == "/api/system/status":
                data = {"api": "available", "worker": "running", "browser": "available", "version": "1.2.0"}
            else:
                data = {"available": True, "active": False, "display_name": "协作空间", "project_id": None, "lifecycle": "NOT_STARTED"}
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"schema_version": "1", "data": data}))

        context = browser.new_context(viewport={"width": width, "height": 1100}, reduced_motion="reduce")
        try:
            context.add_init_script('localStorage.setItem("jiejian.project",' + json.dumps(json.dumps(project)) + ');localStorage.setItem("jiejian.theme",' + json.dumps(theme) + ');')
            page = context.new_page()
            page.route("**/api/**", api)
            page.on("pageerror", lambda error: report["errors"].append(type(error).__name__))
            page.goto(origin + "/#/application")
            expect(page.get_by_role("heading", name="分析权限组与关键业务动作", exact=True)).to_be_visible()
            assert not any("endpoint-candidates" in item for item in requests)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            page.screenshot(path=str(out / f"source-only-{width}-{theme}.png"), full_page=True)
            page.goto(origin + "/#/permissions")
            page.get_by_role('button', name='整理权限候选', exact=True).click()
            inbox = page.get_by_role("region", name="对话规则候选", exact=True)
            expect(inbox.get_by_role("button", name="读取候选", exact=True)).to_be_visible()
            inbox.get_by_role("button", name="Agent 协助", exact=True).click()
            expect(page.get_by_role("button", name="读取整理结果", exact=True)).to_have_count(0)
            expect(page.get_by_role("heading", name="整理这项应用的权限要求", exact=True)).to_be_visible()
            expect(page.get_by_role("button", name="复制协助请求", exact=True)).to_be_disabled()
            page.get_by_text("查看协助请求", exact=True).click()
            expect(page.locator('.agent-assist-panel pre')).to_contain_text("jiejian_rule_context")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            page.screenshot(path=str(out / f"agent-assist-{width}-{theme}.png"), full_page=True)
            page.get_by_role("button", name="连接 Agent", exact=True).click()
            connection = page.get_by_role('dialog', name='连接 Agent', exact=True)
            expect(connection.get_by_role('heading', name='你正在使用哪个客户端？')).to_be_visible()
            page.keyboard.press('Escape')
            expect(connection).to_have_count(0)
            expect(page.get_by_role("button", name="Agent 协助", exact=True)).to_be_visible()
            assert 'view=candidates' in page.url
            page.goto(origin + '/#/permissions?candidate=' + candidate_id + '&revision=1')
            next_step = page.get_by_role('region', name='候选修订下一步', exact=True)
            expect(next_step.get_by_role('heading', name='还有 1 条问题等待 Agent 整理')).to_be_visible()
            expect(page.get_by_role('region', name='含义核对', exact=True)).to_have_count(0)
            next_step.screenshot(path=str(out / f'rule-revision-next-{width}-{theme}.png'))
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
            refresh = page.get_by_role('button', name='读取候选', exact=True)
            refresh.focus()
            refresh.press('Enter')
            expect(page).to_have_url(re.compile(r'revision=2'))
            choices = page.get_by_role('region', name='含义核对', exact=True)
            expect(choices.get_by_role('radio')).to_have_count(4)
            assert choices.get_by_role('radio').evaluate_all('(items) => items.every(item => !item.checked)')
            choices.get_by_role('radio', name=re.compile('允许下载展示版')).check()
            expect(choices.get_by_text('针对的结果：展示版完整收到', exact=True)).to_be_visible()
            choices.screenshot(path=str(out / f'rule-meaning-{width}-{theme}.png'))
            choices.get_by_role('radio', name=re.compile('不是这个意思')).check()
            choices.get_by_role('textbox', name='请说明你的意思', exact=True).fill('只允许下载已经公开的部分。')
            expect(choices.get_by_role('button', name='保存说明', exact=True)).to_be_enabled()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
            choices.screenshot(path=str(out / f'rule-correction-{width}-{theme}.png'))
            page.goto(origin + '/#/permissions?intent_id=pin_' + '1'*32 + '&revision=1')
            page.get_by_text('试一下这些规则怎样适用', exact=True).click()
            for name, label in [('谁来操作','成员'),('资源属于谁','成员'),('资源关系','自己的资源'),('执行什么动作','下载展示版'),('观察哪个结果','展示版完整收到')]:
                page.get_by_role('combobox', name=name, exact=True).click()
                page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').get_by_text(label, exact=True).click()
            page.get_by_role('button', name='查看规则如何适用', exact=True).click()
            expect(page.get_by_text('这组规则允许这个角色执行该动作，并取得所选结果。', exact=True)).to_be_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
            page.locator('.rule-coverage-preview').screenshot(path=str(out / f'rule-coverage-{width}-{theme}.png'))
            report["checks"].append({"width": width, "theme": theme, "pages": ["source-only", "agent-assist", "rule-meaning", "rule-correction", "rule-coverage"], "target_requests": 0, "agent_calls": 0})
        finally:
            context.close()

