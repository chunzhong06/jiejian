# 默认验收的真实GUI操作；用户动作只触发一次，公开API用于核对而不重复写入。
from contextlib import ExitStack
import re
from urllib.parse import parse_qs, quote, urlencode, urlsplit


class CurrentGui:
    """在本轮控制会话中操作当前页面，并记录实际通过的技术交互。"""

    def __init__(self, page, client, audit_dir):
        self.page, self.client, self.audit_dir = page, client, audit_dir
        self.records = []

    def _mark(self, event):
        self.records.append({"event": event, "status": "PASSED"})

    def _goto(self, path):
        self.page.goto(self.client.origin + "/#" + path, wait_until="domcontentloaded")

    def _response(self, path, action, *, accepted=(200, 201, 202), method="POST"):
        from .official import SampleTestError
        with self.page.expect_response(lambda response: response.request.method == method
                and response.url.split("?", 1)[0] == self.client.origin + path, timeout=120_000) as response:
            action()
        actual = response.value
        if actual.status not in accepted:
            raise SampleTestError(f"GUI_ACTION_REJECTED: path={path} status={actual.status}")
        envelope = actual.json()
        if not isinstance(envelope, dict) or "data" not in envelope:
            raise SampleTestError("GUI_ACTION_RECEIPT_INVALID")
        return envelope["data"], actual.request.post_data_json

    def start(self):
        self._goto("/workspace")
        self.page.get_by_role("button", name="启动官方示例", exact=True).click()
        self.page.get_by_role("dialog", name="启动官方示例？").wait_for()
        result, _ = self._response("/api/experience/official-sample/start",
            lambda: self.page.get_by_role("button", name="启动问题版", exact=True).click())
        self.page.locator('[aria-label="权限规则文档"]').wait_for()
        self._mark("start")
        return result

    def propose(self):
        self._goto("/permissions")
        result, _ = self._response("/api/experience/official-sample/boundary-proposal",
            lambda: self.page.get_by_role("button", name="使用已提供的权限提案", exact=True).click())
        self.page.get_by_role("heading", name="待确认业务边界", exact=True).wait_for()
        return result

    def approve(self, project, proposal):
        from .official import SampleTestError
        self._goto("/permissions")
        self.page.get_by_role("heading", name="待确认业务边界", exact=True).wait_for()
        self.page.get_by_role("textbox", name="确认或放弃原因").fill("确认本次受控示例的权限或纯实现重绑，保留原题要求")
        result, body = self._response(f"/api/projects/{project}/business-boundaries/proposals/{proposal.proposal_id}/approve",
            lambda: self.page.get_by_role("button", name="确认这组业务边界", exact=True).click())
        if body.get("expected_fingerprint") != proposal.proposal_fingerprint:
            raise SampleTestError("GUI_APPROVAL_REFERENCE_MISMATCH")
        self._mark("human-approve")
        return result

    def maintenance(self, project):
        self._goto("/permissions")
        self.page.get_by_role("button", name="调整当前业务边界", exact=True).click()
        result, _ = self._response(f"/api/projects/{project}/business-boundaries/maintenance-proposals",
            lambda: self.page.get_by_role("button", name="生成待审调整提案", exact=True).click())
        self.page.get_by_role("heading", name="待确认业务边界", exact=True).wait_for()
        self._mark("maintenance-proposal")
        return result

    def prepare(self):
        from .official import SampleTestError
        experience = self.client.call("GET", "/api/experience/official-sample")
        project = experience.get("project_id")
        if not experience.get("active") or not project:
            raise SampleTestError("GUI_SAMPLE_PROJECT_MISSING")
        workspace = self.client.call("GET", f"/api/projects/{project}/workspace")
        task = workspace.get("primary_task") or {}
        if (workspace.get("project", {}).get("project_id") == project and task.get("route") == "/tests"
                and task.get("task_kind") in {"RUN_CURRENT_CHECK", "VIEW_CURRENT_RESULT", "VERIFY_REPAIR"}
                and task.get("can_execute")):
            materials = self.client.call("GET", f"/api/projects/{project}/preparation")
            preview = self.client.call("GET", f"/api/projects/{project}/check-preview")
            if (materials.get("project_id") == project and materials.get("preparation_complete") is True
                    and preview.get("project_id") == project and preview.get("can_execute") is True):
                # 条件变化不必使材料失效；复用普通准备与预览真相，不为了旧 Sample 标记再次安装。
                self._goto("/tests")
                self.page.get_by_role("button", name="开始检查", exact=True).wait_for()
                self._mark("prepare-reused")
                return experience
        kinds = {"REVIEW_RECORDING", "PREPARE_TEST_IDENTITY", "DEMONSTRATE_ACTION",
                 "PREPARE_ACTION_RESOURCE", "COMPLETE_EFFECT_EVIDENCE", "COMPLETE_RECOVERY"}
        if (workspace.get("project", {}).get("project_id") != project or task.get("route") != "/tests"
                or task.get("task_kind") not in kinds or not task.get("task_id") or not task.get("can_execute")):
            raise SampleTestError("GUI_PREPARATION_TASK_UNAVAILABLE")
        self._goto(task["route"] + "?" + urlencode({"task_id": task["task_id"]}))
        self.capture("preparation")
        result, _ = self._response("/api/experience/official-sample/prepare",
            lambda: self.page.get_by_role("button", name="使用已提供的测试材料", exact=True).click())
        if result.get("scenario_prepared"):
            self._goto("/tests")
            self.page.get_by_role("button", name="开始检查", exact=True).wait_for()
            self._mark("prepare")
        return result

    def switch(self, version, reference):
        from .official import SampleTestError
        labels = {"VULNERABLE": "切换到问题版", "EVIDENCE_LIMITED": "切换到证据受限版", "FIXED": "切换到修复版"}
        versions = {"VULNERABLE": "问题版", "EVIDENCE_LIMITED": "证据受限版", "FIXED": "修复版"}
        experience = self.client.call("GET", "/api/experience/official-sample")
        project = experience.get("project_id")
        if not experience.get("active") or not project or experience.get("scenario_version") not in versions:
            raise SampleTestError("GUI_SAMPLE_PROJECT_MISSING")
        repair = None
        if version == "FIXED":
            if not isinstance(reference, dict) or set(reference) != {"source_run_id", "source_case_id", "repair_fingerprint"}:
                raise SampleTestError("GUI_ORIGINAL_REPAIR_MISSING")
            repair = self.client.call("GET", f"/api/projects/{project}/repair")
            matches = [task for task in repair.get("tasks", []) if task.get("status") != "STALE"
                and {name: task["contract"].get(name) for name in reference} == reference]
            if repair.get("project_id") != project or len(matches) != 1:
                raise SampleTestError("GUI_ORIGINAL_REPAIR_AMBIGUOUS")
            original = self.client.call("GET", f"/api/runs/{reference['source_run_id']}")
            if original.get("result_integrity") != "VALID" or original.get("run", {}).get("verdict") != "BLOCK":
                raise SampleTestError("GUI_ORIGINAL_REPAIR_MISSING")
        self._goto("/workspace")
        outer = self.page.locator('details').filter(has=self.page.get_by_text("示例环境管理", exact=True))
        if outer.count() and outer.get_attribute("open") is None:
            outer.locator("summary").first.click()
        self.page.get_by_text("官方环境 · " + versions[experience["scenario_version"]], exact=True).click()
        if repair is not None and len(repair["tasks"]) > 1:
            eligible = [task for task in repair["tasks"] if task["status"] != "STALE"]
            selected = next(index for index, task in enumerate(eligible) if task is matches[0])
            self.page.get_by_role("combobox", name="选择待修复原题", exact=True).click()
            self.page.get_by_role("option", name=f"原问题 {selected + 1}", exact=True).click()
        self.page.get_by_role("button", name=labels[version], exact=True).click()
        result, body = self._response("/api/experience/official-sample/version",
            lambda: self.page.get_by_role("button", name="确认切换", exact=True).click())
        if body.get("version") != version or body.get("repair_reference") != reference:
            raise SampleTestError("GUI_VERSION_REFERENCE_MISMATCH")
        self._mark("switch-" + version.lower())
        return result

    def submit(self, project, expected_body, change_id, *, require_repair=False):
        from .official import SampleTestError
        repair = self.client.call("GET", f"/api/projects/{project}/repair") if change_id else None
        matches = [] if repair is None else [task for task in repair.get("tasks", []) if task.get("change_id") == change_id]
        if repair is not None and repair.get("project_id") != project:
            raise SampleTestError("GUI_REPAIR_PROJECT_MISMATCH")
        # 固定修复轮必须取得原题入口，缺任务不能退回普通变化检查。
        if require_repair and len(matches) != 1:
            raise SampleTestError("GUI_REPAIR_NOT_READY")
        if matches:
            if len(matches) != 1 or matches[0].get("status") != "READY_TO_VERIFY":
                raise SampleTestError("GUI_REPAIR_NOT_READY")
            self._goto("/changes?" + urlencode({"repair_reference": matches[0]["contract"]["repair_fingerprint"]}))
            self.page.get_by_role("button", name="复验原题", exact=True).click()
            def exact_change(url):
                route, _, query = urlsplit(str(url)).fragment.partition("?")
                return route == "/tests" and parse_qs(query).get("change_id") == [change_id]
            self.page.wait_for_url(exact_change)
            if not exact_change(self.page.url):
                raise SampleTestError("GUI_REPAIR_CHANGE_MISMATCH")
            self._mark("repair-via-changes")
        else:
            self._goto("/tests" + ("?" + urlencode({"change_id": change_id}) if change_id else ""))
        result, body = self._response(f"/api/projects/{project}/runs",
            lambda: self.page.get_by_role("button", name="开始检查", exact=True).click(), accepted=(202,))
        if (body.get("schema_version") != "2" or body.get("change_id") != change_id
                or body.get("expected_plan_fingerprint") != expected_body["expected_plan_fingerprint"]
                or not body.get("idempotency_key") or set(body) - {"schema_version", "change_id", "expected_plan_fingerprint", "idempotency_key"}):
            raise SampleTestError("GUI_CHECK_SUBMISSION_MISMATCH")
        self._mark("submit-check")
        self.capture("check-after-submit")
        return result

    def checkpoint(self, event, payload):
        from .official import SampleTestError
        if event.endswith("-result"):
            self._goto("/tests?" + urlencode({"run_id": payload["run_id"]}))
            self.page.get_by_role("heading", name=payload["story"]["judgement"], level=1, exact=True).wait_for()
            if event == "problem-result":
                self._decisive_evidence(payload)
                self._execution_path(payload)
            if event == "fixed-result":
                if (payload["story"].get("repair_verification") or {}).get("status") != "VERIFIED":
                    raise SampleTestError("GUI_ORIGINAL_REPAIR_NOT_VERIFIED")
                self.page.get_by_role("heading", name="原问题已经通过复验，要求保留的合法能力未受影响", exact=True).wait_for()
            self.page.screenshot(path=str(self.audit_dir / (event + ".png")), full_page=True)
        elif event in {"limited-ready", "fixed-ready"}:
            self._goto("/tests")
            if not payload.get("project_id"):
                raise SampleTestError("GUI_SAMPLE_PROJECT_MISSING")
            self.page.get_by_role("button", name="开始检查", exact=True).wait_for()
        elif event == "evidence-and-repair":
            runs = payload["runs"]
            if not runs:
                raise SampleTestError("GUI_ORIGINAL_REPAIR_MISSING")
            self._goto("/tests?" + urlencode({"run_id": runs[-1]["run_id"]}))
            self.page.get_by_role("heading", name="原问题已经通过复验，要求保留的合法能力未受影响", exact=True).wait_for()
            self.page.get_by_role("button", name="查看原问题", exact=True).click()
            self.page.get_by_role("heading", name=runs[0]["story"]["judgement"], level=1, exact=True).wait_for()
            self._breakpoint_evidence(runs[0])
            self.history_search(payload["project_id"], runs[0]["run_id"])
            self.history_open(runs[0])
            self.history_return(runs[0]["run_id"])
            self._goto("/changes")
            self.page.get_by_role("heading", name="原题复验通过", exact=True).first.wait_for()
            self.capture("repair")
        else:
            raise SampleTestError("GUI_CHECKPOINT_UNKNOWN")
        self._mark(event)

    def _decisive_evidence(self, payload):
        from .official import SampleTestError
        candidates = [(action, source) for action in payload["story"]["actions"]
            if action["permission"]["expectation"] == "DENY"
            for source in action.get("decisive_proof_chain", []) if source.get("evidence_refs")]
        if not candidates:
            raise SampleTestError("GUI_DECISIVE_EVIDENCE_MISSING")
        action, source = candidates[0]
        operations = 0
        if len(payload["story"]["actions"]) > 1:
            label = action["display_name"] + " · " + (action["fact_comparison"]["planned_identity"]["label"] or "计划账号") + " · 应当拒绝"
            selected = self.page.get_by_role("navigation", name="本轮权限考题", exact=True).get_by_role("button", name=label, exact=True)
            if selected.get_attribute("aria-current") != "true":
                selected.click()
                operations += 1
        refs = list(dict.fromkeys(source["evidence_refs"]))
        # 所有 GET 等待先注册再点击一次；不使用 API 读取来替代真实 Drawer 动作。
        with ExitStack() as stack:
            responses = []
            for reference in refs:
                url = self.client.origin + f"/api/runs/{quote(payload['run_id'], safe='')}/evidence/{quote(reference, safe='')}"
                responses.append(stack.enter_context(self.page.expect_response(
                    lambda response, expected=url: response.request.method == "GET" and response.url == expected)))
            self.page.locator('section[aria-label="最终业务结果"]').get_by_role("button",
                name="为什么这样判断？查看" + source["source_label"] + "证据", exact=True).first.click()
            operations += 1
        drawer = self._evidence_container()
        for question in ("在哪里看到", "看到什么", "因此支持什么", "不能单独证明什么"):
            drawer.get_by_text(question, exact=True).wait_for()
        for reference, response in zip(refs, responses):
            actual = response.value
            data = actual.json().get("data", {})
            if (actual.status != 200 or data.get("run_id") != payload["run_id"] or data.get("evidence_id") != reference
                    or data.get("case", {}).get("case_id") != action["case_id"] or data.get("action_id") != action["action_id"]):
                raise SampleTestError("GUI_DECISIVE_EVIDENCE_REFERENCE_MISMATCH")
        self.capture("decisive-evidence")
        self._close_evidence(drawer)
        self.records.append({"event": "decisive-evidence", "status": "PASSED", "run_id": payload["run_id"],
            "case_id": action["case_id"], "evidence_refs": refs, "open_operations": operations})

    def _evidence_container(self):
        panel = self.page.get_by_role("complementary", name="已发布证据", exact=True).or_(
            self.page.get_by_role("dialog", name="已发布证据", exact=True))
        panel.wait_for()
        return panel

    def _breakpoint_evidence(self, payload):
        from .official import SampleTestError
        actions = [item for item in payload["story"]["actions"] if item["permission"]["expectation"] == "DENY" and (item.get("breakpoint") or {}).get("evidence_refs")]
        if not actions:
            raise SampleTestError("GUI_ORIGINAL_BREAKPOINT_EVIDENCE_MISSING")
        action = actions[0]
        refs = list(dict.fromkeys(action["breakpoint"]["evidence_refs"]))
        with ExitStack() as stack:
            responses = [stack.enter_context(self.page.expect_response(lambda response, ref=ref:
                response.request.method == "GET" and response.url == self.client.origin + f"/api/runs/{payload['run_id']}/evidence/{ref}")) for ref in refs]
            self.page.get_by_role("button", name="为什么定位在这里？查看定位证据", exact=True).click()
        panel = self._evidence_container()
        for question in ("在哪里看到", "看到什么", "因此支持什么", "不能单独证明什么"):
            panel.get_by_text(question, exact=True).wait_for()
        for ref, response in zip(refs, responses, strict=True):
            data = response.value.json().get("data", {})
            if response.value.status != 200 or (data.get("run_id"), data.get("action_id"), data.get("case", {}).get("case_id"), data.get("evidence_id")) != (
                    payload["run_id"], action["action_id"], action["case_id"], ref):
                raise SampleTestError("GUI_ORIGINAL_BREAKPOINT_EVIDENCE_MISMATCH")
        panel.get_by_role("heading", name="观察记录", exact=True).first.wait_for()
        self.capture("original-evidence")
        self._close_evidence(panel)

    def _close_evidence(self, panel):
        panel.get_by_role("button", name=re.compile(r"^(关闭证据并返回事实|返回检查事实)$")).click()
        panel.wait_for(state="hidden")

    def capture(self, name):
        """只截取当前真实页面；文件名有界，不注入占位运行状态。"""
        from .official import SampleTestError
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", name):
            raise SampleTestError("GUI_CAPTURE_NAME_INVALID")
        self.page.screenshot(path=str(self.audit_dir / (name + ".png")), full_page=True)

    def _execution_path(self, payload):
        from .official import SampleTestError
        actions = [item for item in payload["story"]["actions"] if item["permission"]["expectation"] == "DENY"
            and (item.get("execution_path") or {}).get("events")]
        if not actions:
            raise SampleTestError("GUI_EXECUTION_PATH_MISSING")
        action = actions[0]
        label = action["display_name"] + " · " + (action["fact_comparison"]["planned_identity"]["label"] or "计划账号") + " · 应当拒绝"
        self.page.get_by_role("navigation", name="本轮权限考题", exact=True).get_by_role("button", name=label, exact=True).click()
        graph = self.page.locator('section[aria-label="已发布执行路径"]')
        path = action["execution_path"]
        if len(path["events"]) > 32:
            graph.get_by_role("button", name="展开完整执行路径", exact=True).click()
        edges = graph.locator("path[data-parent][data-child]").evaluate_all(
            "nodes => nodes.map(node => [node.dataset.parent, node.dataset.child])")
        expected = [[parent, event["event_id"]] for event in path["events"] for parent in event["parent_event_ids"]]
        if sorted(edges) != sorted(expected):
            raise SampleTestError("GUI_EXECUTION_PATH_EDGES_MISMATCH")
        exact = action.get("breakpoint") or {}
        marks = graph.locator("button.path-node").evaluate_all(
            "nodes => nodes.map(node => node.classList.contains('path-node-breakpoint'))")
        expected_marks = [exact.get("precision") == "EXACT" and event["event_id"] == exact.get("first_violation_event_id") for event in path["events"]]
        if marks != expected_marks:
            raise SampleTestError("GUI_EXECUTION_PATH_PRECISION_MISMATCH")
        event, refs = path["events"][0], list(dict.fromkeys(path["evidence_refs"]))
        if not refs:
            raise SampleTestError("GUI_EXECUTION_PATH_EVIDENCE_MISSING")
        with ExitStack() as stack:
            responses = [stack.enter_context(self.page.expect_response(lambda response, ref=ref:
                response.request.method == "GET" and response.url == self.client.origin + f"/api/runs/{payload['run_id']}/evidence/{ref}")) for ref in refs]
            graph.locator("button.path-node").nth(0).click()
        panel = self._evidence_container()
        panel.get_by_text(event["source_component"] + " · " + event["source_location"], exact=True).wait_for()
        for ref, response in zip(refs, responses, strict=True):
            data = response.value.json().get("data", {})
            if (response.value.status != 200 or data.get("run_id") != payload["run_id"] or data.get("evidence_id") != ref
                    or data.get("action_id") != action["action_id"] or data.get("case", {}).get("case_id") != action["case_id"]):
                raise SampleTestError("GUI_EXECUTION_PATH_EVIDENCE_MISMATCH")
        self.capture("execution-path-evidence")
        self._close_evidence(panel)
        self.records.append(dict(event="execution-path", status="PASSED", run_id=payload["run_id"], case_id=action["case_id"], evidence_refs=refs, complete=path["complete"]))

    def history_search(self, project, run_id):
        from .official import SampleTestError
        self._goto("/history")
        self.page.get_by_role("textbox", name="搜索检查历史", exact=True).fill(run_id)
        with self.page.expect_response(lambda response: response.request.method == "GET"
                and urlsplit(response.url).path == f"/api/projects/{project}/check-history"
                and parse_qs(urlsplit(response.url).query).get("query") == [run_id]) as response:
            self.page.get_by_role("button", name="搜索", exact=True).click()
        data = response.value.json().get("data", {})
        if response.value.status != 200 or data.get("project_id") != project or [item["status"]["run"]["run_id"] for item in data.get("items", [])] != [run_id]:
            raise SampleTestError("GUI_HISTORY_SEARCH_MISMATCH")
        self.page.locator(f'[data-run="{run_id}"]').wait_for()
        if self.page.locator("[data-run]:visible").evaluate_all("nodes => nodes.map(node => node.dataset.run)") != [run_id]:
            raise SampleTestError("GUI_HISTORY_ROWS_MISMATCH")
        self.capture("history")
        self._mark("history-search")

    def history_open(self, result):
        self.page.locator(f'[data-run="{result["run_id"]}"]').click()
        self._exact_history_result(result)

    def _exact_history_result(self, result):
        def matches(url):
            route, _, query = urlsplit(str(url)).fragment.partition("?")
            return route == "/history" and parse_qs(query).get("run_id") == [result["run_id"]]
        self.page.wait_for_url(matches)
        self.page.get_by_role("heading", name=result["story"]["judgement"], level=1, exact=True).wait_for()

    def history_return(self, query):
        from .official import SampleTestError
        self.page.get_by_role("button", name="返回检查历史", exact=True).click()
        self.page.get_by_role("textbox", name="搜索检查历史", exact=True).wait_for()
        if (self.page.get_by_role("textbox", name="搜索检查历史", exact=True).input_value() != query
                or self.page.locator("[data-run]:visible").evaluate_all("nodes => nodes.map(node => node.dataset.run)") != [query]):
            raise SampleTestError("GUI_HISTORY_RETURN_STATE_LOST")
        self._mark("history-return")

    def mcp_pair(self):
        self._goto("/tools")
        value, _ = self._response("/api/mcp/access/pair",
            lambda: self.page.get_by_role("button", name="准备本机连接", exact=True).click())
        return value

    def mcp_forget(self):
        self._goto("/tools")
        self.page.get_by_role("button", name="管理连接", exact=True).click()
        self.page.get_by_role("dialog", name="管理连接", exact=True).get_by_role("button", name="删除连接凭据", exact=True).click()
        self._response("/api/mcp/access/forget", lambda: self.page.get_by_role("dialog", name="确认删除连接凭据？", exact=True)
            .get_by_role("button", name="确认", exact=True).click())

    def mcp_level(self, project, level):
        from .official import SampleTestError
        labels = {"READ": "只查看", "PREPARE": "协助整理", "EXECUTE": "执行已确认任务"}
        projects = self.client.call("GET", "/api/projects")
        if len(projects) != 1 or projects[0].get("project_id") != project:
            raise SampleTestError("GUI_MCP_SAMPLE_PROJECT_AMBIGUOUS")
        self._goto("/tools")
        self.page.get_by_role("button", name="调整这次允许范围", exact=True).click()
        dialog = self.page.get_by_role("dialog", name="这次允许 AI 工具做到哪一步？", exact=True)
        dialog.get_by_role("radio", name=re.compile("^" + labels[level])).check()
        result, body = self._response(f"/api/mcp/access/projects/{project}",
            lambda: dialog.get_by_role("button", name="保存这次允许范围", exact=True).click(), method="PUT")
        grants = {item["project_id"]: item["level"] for item in result.get("project_grants", [])}
        if body != {"schema_version": "1", "level": level} or grants.get(project, "READ") != level:
            raise SampleTestError("GUI_MCP_GRANT_MISMATCH")
        self.records.append(dict(event="mcp-level-" + level.lower(), status="PASSED", project_id=project, scope=level))

    def mcp_connected(self, name):
        from .official import SampleTestError
        with self.page.expect_response(lambda response: response.request.method == "GET" and response.url == self.client.origin + "/api/mcp/access") as response:
            self.page.get_by_role("button", name="检查连接", exact=True).click()
        view = response.value.json().get("data", {})
        if response.value.status != 200 or not view.get("client_connected") or view.get("client_name") != name:
            raise SampleTestError("GUI_MCP_CLIENT_NOT_CONNECTED")
        self.page.get_by_text(name + " 已连接到界鉴", exact=True).wait_for()
        self._mark("mcp-connected")

    def mcp_change(self, change):
        from .official import SampleTestError
        self._goto("/changes")
        entry = self.page.locator("li.change-event").filter(has=self.page.get_by_role("heading", name=change["reason"], exact=True))
        entry.get_by_text(change["submitted_by"], exact=True).wait_for()
        # 原题已 VERIFIED 时，同一个人工表单的真实折叠标题为“登记新的代码变化”。
        manual = self.page.locator("details").filter(has=self.page.get_by_text(re.compile(r"^(手动接管代码变化登记|登记新的代码变化)$")))
        if manual.count() != 1 or manual.get_attribute("open") is not None:
            raise SampleTestError("GUI_MCP_MANUAL_FORM_NOT_CLOSED")
        self.capture("mcp-change")
        self.records.append(dict(event="mcp-change", status="PASSED", project_id=change["project_id"], change_id=change["change_id"]))

    def dismiss_completion(self):
        close = self.page.get_by_role("button", name="关闭检查完成提示", exact=True)
        if close.count():
            close.click()

    def mcp_completion(self, result, original_query):
        from .official import SampleTestError
        notice = self.page.locator(".check-activity-notice")
        notice.get_by_role("button", name="查看结果", exact=True).wait_for(timeout=180_000)
        if (urlsplit(self.page.url).fragment != "/history"
                or self.page.get_by_role("textbox", name="搜索检查历史", exact=True).input_value() != original_query):
            raise SampleTestError("GUI_MCP_COMPLETION_CHANGED_LOCATION")
        notice.get_by_role("button", name="查看结果", exact=True).click()
        self._exact_history_result(result)
        self.capture("mcp-result")
        self.history_return(original_query)
        self.records.append(dict(event="mcp-completion", status="PASSED", run_id=result["run_id"], scope="ordinary-full-check"))

    def shutdown(self):
        self.page.get_by_role("button", name="设置与更多", exact=False).click()
        self.page.get_by_role("menuitem", name="退出界鉴", exact=False).click()
        self.page.get_by_role("dialog", name="退出界鉴？", exact=True).wait_for()
        result, _ = self._response("/api/system/shutdown",
            lambda: self.page.get_by_role("button", name="安全退出", exact=True).click())
        self._mark("exit")
        return result
