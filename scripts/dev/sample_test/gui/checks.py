# 准备、执行和证据的真实页面操作。
from contextlib import ExitStack
import re
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from .session import GuiSession


class ChecksActions(GuiSession):
    def prepare(self):
        from scripts.dev.sample_test.harness.state import SampleTestError
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
            # 等页面完成写后回读再显式返回；收到POST回执不代表React已同步准备模式。
            self.page.get_by_role("button", name="返回检查总览", exact=True).click()
            self.page.get_by_role("button", name="开始检查", exact=True).wait_for()
            self._mark("prepare")
        return result

    def submit(self, project, expected_body, change_id, *, require_repair=False):
        from scripts.dev.sample_test.harness.state import SampleTestError
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
        from scripts.dev.sample_test.harness.state import SampleTestError
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
            repair = self.client.call("GET", f"/api/projects/{payload['project_id']}/repair")
            original = [item for item in repair["tasks"] if item["contract"]["source_run_id"] == runs[0]["run_id"]]
            if len(original) != 1:
                raise SampleTestError("GUI_ORIGINAL_REPAIR_AMBIGUOUS")
            self._goto("/changes?" + urlencode({"repair_reference": original[0]["contract"]["repair_fingerprint"]}))
            self.page.get_by_role("heading", name="原题复验通过", exact=True).first.wait_for()
            self.capture("repair")
        else:
            raise SampleTestError("GUI_CHECKPOINT_UNKNOWN")
        self._mark(event)

    def _decisive_evidence(self, payload):
        from scripts.dev.sample_test.harness.state import SampleTestError
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
        from scripts.dev.sample_test.harness.state import SampleTestError
        actions = [item for item in payload["story"]["actions"] if item["permission"]["expectation"] == "DENY" and (item.get("breakpoint") or {}).get("evidence_refs")]
        if not actions:
            raise SampleTestError("GUI_ORIGINAL_BREAKPOINT_EVIDENCE_MISSING")
        action = actions[0]
        refs = list(dict.fromkeys(action["breakpoint"]["evidence_refs"]))
        disclosure = self.page.locator("details").filter(has=self.page.get_by_text("核对观察与定位依据", exact=True))
        if disclosure.get_attribute("open") is None:
            disclosure.locator("summary").click()
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
        panel.get_by_role("button", name=re.compile(r"^(关闭证据并返回事实|返回检查事实)$")).click()
        panel.wait_for(state="hidden")

    def _execution_path(self, payload):
        from scripts.dev.sample_test.harness.state import SampleTestError
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
