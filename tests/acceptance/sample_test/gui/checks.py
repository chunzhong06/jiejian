# 准备、执行和证据的真实页面操作。
from contextlib import ExitStack
import re
import time
from playwright.sync_api import expect
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from .session import GuiSession


class ChecksActions(GuiSession):
    def prepare(self):
        from tests.acceptance.sample_test.harness.state import SampleTestError
        experience = self.client.call("GET", "/api/experience/official-sample")
        project = experience.get("project_id")
        if not experience.get("active") or not project:
            raise SampleTestError("GUI_SAMPLE_PROJECT_MISSING")
        workspace = self.client.call("GET", f"/api/projects/{project}/workspace")
        task = workspace.get("primary_task") or {}
        reusable_task = (task.get("route") == "/tests" and task.get("task_kind") in {"RUN_CURRENT_CHECK", "VIEW_CURRENT_RESULT", "VERIFY_REPAIR"}
            or task.get("route") == "/changes" and task.get("task_kind") == "PREPARE_AGENT_REPAIR")
        if (workspace.get("project", {}).get("project_id") == project and reusable_task
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
        if experience.get('runtime_kind')=='NODE_ESM':
            from tests.acceptance.sample_test.harness.lifecycle import _wait_for
            # 当前产品由一次GUI确认启动持久批次，不能再点击已经退出的同步准备入口。
            self.page.get_by_role('button',name='一键准备示例材料',exact=True).click()
            modal=self.page.get_by_role('dialog',name='准备这份官方示例的检查材料',exact=True)
            prefix=f'/api/projects/{project}/proof-preparation/batches'
            receipt,_=self._response(prefix,lambda:modal.get_by_role('button',name='确认并一键准备',exact=True).click())
            result=_wait_for(lambda:self.client.call('GET',prefix+'/'+receipt['operation_id']),
                lambda value:value['state'] not in ('RUNNING','CANCELLING'),timeout=90,label='示例材料批次')
            if result['state']!='SUCCEEDED' or not self.client.call('GET',f'/api/projects/{project}/preparation')['preparation_complete']:
                raise SampleTestError('GUI_PREPARATION_BATCH_NOT_READY')
            self._mark('prepare')
            return self.client.call('GET','/api/experience/official-sample')
        result, _ = self._response("/api/experience/official-sample/prepare",
            lambda: self.page.get_by_role("button", name="使用已提供的测试材料", exact=True).click())
        if result.get("scenario_prepared"):
            # 等页面完成写后回读再显式返回；收到POST回执不代表React已同步准备模式。
            self.page.get_by_role("button", name="返回检查总览", exact=True).click()
            self.page.get_by_role("button", name="开始检查", exact=True).wait_for()
            self._mark("prepare")
        return result

    def submit(self, project, expected_body, change_id, *, require_repair=False):
        from tests.acceptance.sample_test.harness.state import SampleTestError
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
            self.page.get_by_role("button", name="准备复验原题", exact=True).wait_for()
            self.dismiss_completion()
            self.page.get_by_role("button", name="准备复验原题", exact=True).click()
            def exact_change(url):
                route, _, query = urlsplit(str(url)).fragment.partition("?")
                return route == "/tests" and parse_qs(query).get("change_id") == [change_id]
            self.page.wait_for_url(exact_change)
            if not exact_change(self.page.url):
                raise SampleTestError("GUI_REPAIR_CHANGE_MISMATCH")
            self.page.get_by_role("button", name="返回检查总览", exact=True).click()
            self.page.wait_for_url(lambda url: exact_change(url) and "materials" not in parse_qs(urlsplit(str(url)).fragment.partition("?")[2]))
            self._mark("repair-via-changes")
        else:
            self._goto("/tests" + ("?" + urlencode({"change_id": change_id}) if change_id else ""))
        import json
        # 页面先完成权威预览；提交回执的等待只覆盖实际点击之后。
        ready_at=time.monotonic()
        expect(self.page.get_by_role('button',name='开始检查',exact=True)).to_be_enabled(timeout=120_000)
        print(f'检查页面条件读取完成：{time.monotonic()-ready_at:.1f}秒',flush=True)
        self.dismiss_completion()
        try:
            result, body = self._response(f"/api/projects/{project}/runs",
                lambda: self.page.get_by_role("button", name="开始检查", exact=True).click(), accepted=(202,))
        except Exception:
            # 同一按钮的DOM文本用于区分无障碍名称、遮挡与禁用，不记录页面或请求正文。
            controls=self.page.locator('.task-focus-actions button').evaluate_all("""nodes=>nodes.map(node=>({
              text:node.textContent,html:node.outerHTML,disabled:node.disabled,
              hiddenAncestor:!!node.closest('[aria-hidden=true],[inert]')}))""")
            (self.audit_dir/'submit-control-failed.json').write_text(json.dumps(controls,ensure_ascii=False),encoding='utf-8')
            raise
        if (body.get("schema_version") != "2" or body.get("change_id") != change_id
                or body.get("expected_plan_fingerprint") != expected_body["expected_plan_fingerprint"]
                or not body.get("idempotency_key") or set(body) - {"schema_version", "change_id", "expected_plan_fingerprint", "idempotency_key"}):
            raise SampleTestError("GUI_CHECK_SUBMISSION_MISMATCH")
        self._mark("submit-check")
        self.capture("check-after-submit")
        return result

    def checkpoint(self, event, payload):
        from tests.acceptance.sample_test.harness.state import SampleTestError
        if event.endswith("-result"):
            self._goto("/tests?" + urlencode({"run_id": payload["run_id"]}))
            if event == "fixed-result" and (payload["story"].get("repair_verification") or {}).get("status") != "VERIFIED":
                raise SampleTestError("GUI_ORIGINAL_REPAIR_NOT_VERIFIED")
            title = "原题复验通过" if event == "fixed-result" else payload["story"]["judgement"]
            self.page.get_by_role("heading", name=title, level=1, exact=True).wait_for()
            if event == "problem-result":
                self._decisive_evidence(payload)
                self._execution_path(payload)
            if event == "fixed-result":
                if (payload["story"].get("repair_verification") or {}).get("status") != "VERIFIED":
                    raise SampleTestError("GUI_ORIGINAL_REPAIR_NOT_VERIFIED")
                self.page.locator('[aria-label="权限验证工作区"]:visible').get_by_text("原题复验通过", exact=True).wait_for()
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
            self.page.locator('[aria-label="权限验证工作区"]:visible').get_by_text("原题复验通过", exact=True).wait_for()
            self.page.get_by_role("button", name="查看原检查结果", exact=True).click()
            self.page.get_by_role("heading", name=runs[0]["story"]["judgement"], level=1, exact=True).wait_for()
            self._breakpoint_evidence(runs[0])
            self.history_search(payload["project_id"], runs[0]["run_id"])
            self.history_open(runs[0])
            self.history_return(runs[0]["run_id"])
            repair = self.client.call("GET", f"/api/projects/{payload['project_id']}/repair")
            original = [item for item in repair["tasks"] if item["contract"]["source_run_id"] == runs[0]["run_id"]]
            if len(original) != 1:
                raise SampleTestError("GUI_ORIGINAL_REPAIR_AMBIGUOUS")
            if original[0]["status"] != "VERIFIED":
                raise SampleTestError("GUI_ORIGINAL_REPAIR_NOT_VERIFIED")
            self._goto("/changes?" + urlencode({"repair_reference": original[0]["contract"]["repair_fingerprint"]}))
            self.page.get_by_role("heading", name="修复与复验", exact=True).wait_for()
            # 只核对可见工作面中的结论标签；装饰符号不是业务文案的一部分。
            self.page.locator('[aria-label="修复依据"]:visible .product-status[data-kind="verdict"][data-tone="success"]').filter(has_text="原题复验通过").wait_for()
            self.capture("repair")
        else:
            raise SampleTestError("GUI_CHECKPOINT_UNKNOWN")
        self._mark(event)

    def _select_result_case(self, action):
        """通过总览的精确 case 引用选中检查项，深链详情先返回总览。"""
        selected = self.page.locator(f'button[data-result-case="{action["case_id"]}"]')
        if not selected.count():
            self.page.get_by_role("button", name=re.compile(r"^← 返回 \d+ 项结果$")).click()
        selected.click()

    def _decisive_evidence(self, payload):
        from tests.acceptance.sample_test.harness.state import SampleTestError
        candidates = [(action, source) for action in payload["story"]["actions"]
            if action["permission"]["expectation"] == "DENY"
            for source in action.get("proof_coverage", [])
            if source.get("required_level") == "VERDICT_REQUIRED" and source.get("evidence_refs")]
        if not candidates:
            raise SampleTestError("GUI_DECISIVE_EVIDENCE_MISSING")
        action, source = candidates[0]
        self._select_result_case(action)
        operations = 1
        refs = list(dict.fromkeys(source["evidence_refs"]))
        # 证明要求的引用是权威范围；先注册全部 GET，再由真实页面一次打开。
        with ExitStack() as stack:
            responses = []
            for reference in refs:
                url = self.client.origin + f"/api/runs/{quote(payload['run_id'], safe='')}/evidence/{quote(reference, safe='')}"
                responses.append(stack.enter_context(self.page.expect_response(
                    lambda response, expected=url: response.request.method == "GET" and response.url == expected)))
            self.page.get_by_role("article", name=source["business_label"] + "的证据对应", exact=True).get_by_role("button",
                name="查看必要证明记录", exact=True).click()
            operations += 1
        drawer = self._evidence_container()
        drawer.get_by_text("来自所选证明要求", exact=True).wait_for()
        drawer.get_by_role("heading", name=source["business_label"], exact=True).wait_for()
        drawer.get_by_role("heading", name="观察记录", exact=True).first.wait_for()
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
        panel = self.page.get_by_role("region", name="已发布证据", exact=True)
        panel.wait_for()
        return panel

    def _breakpoint_evidence(self, payload):
        from tests.acceptance.sample_test.harness.state import SampleTestError
        actions = [item for item in payload["story"]["actions"] if item["permission"]["expectation"] == "DENY" and (item.get("breakpoint") or {}).get("evidence_refs")]
        if not actions:
            raise SampleTestError("GUI_ORIGINAL_BREAKPOINT_EVIDENCE_MISSING")
        action = actions[0]
        refs = list(dict.fromkeys(action["breakpoint"]["evidence_refs"]))
        self._select_result_case(action)
        self.page.get_by_role("navigation", name="检查项详情", exact=True).get_by_role("button", name="执行过程", exact=True).click()
        with ExitStack() as stack:
            responses = [stack.enter_context(self.page.expect_response(lambda response, ref=ref:
                response.request.method == "GET" and response.url == self.client.origin + f"/api/runs/{payload['run_id']}/evidence/{ref}")) for ref in refs]
            label = "查看区间的定位证据" if action["breakpoint"].get("precision") == "RANGE" else "查看定位证据"
            self.page.get_by_role("region", name="定位依据与边界", exact=True).get_by_role("button", name=label, exact=True).click()
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
        panel.get_by_role("button", name=re.compile(r"^← 返回(执行过程|事实与证明|证据目录)$")).click()
        panel.wait_for(state="hidden")

    def _execution_path(self, payload):
        from tests.acceptance.sample_test.harness.state import SampleTestError
        actions = [item for item in payload["story"]["actions"] if item["permission"]["expectation"] == "DENY"
            and (item.get("execution_path") or {}).get("events")]
        if not actions:
            raise SampleTestError("GUI_EXECUTION_PATH_MISSING")
        action = actions[0]
        self._select_result_case(action)
        self.page.get_by_role("navigation", name="检查项详情", exact=True).get_by_role("button", name="执行过程", exact=True).click()
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
