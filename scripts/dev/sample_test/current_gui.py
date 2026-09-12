# 默认验收的真实GUI操作；用户动作只触发一次，公开API用于核对而不重复写入。
from urllib.parse import urlencode


class CurrentGui:
    """在本轮控制会话中操作当前页面，并记录实际通过的技术交互。"""

    def __init__(self, page, client, audit_dir):
        self.page, self.client, self.audit_dir = page, client, audit_dir
        self.records = []

    def _mark(self, event):
        self.records.append({"event": event, "status": "PASSED"})

    def _goto(self, path):
        self.page.goto(self.client.origin + "/#" + path, wait_until="domcontentloaded")

    def _response(self, path, action, *, accepted=(200, 201, 202)):
        from .official import SampleTestError
        with self.page.expect_response(lambda response: response.request.method == "POST"
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
        self.page.get_by_role("button", name="审阅示例权限", exact=True).wait_for()
        self._mark("start")
        return result

    def propose(self):
        self._goto("/workspace")
        result, _ = self._response("/api/experience/official-sample/boundary-proposal",
            lambda: self.page.get_by_role("button", name="审阅示例权限", exact=True).click())
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
        self._goto("/workspace")
        result, _ = self._response("/api/experience/official-sample/prepare",
            lambda: self.page.get_by_role("button", name="准备示例材料", exact=True).click())
        if result.get("scenario_prepared"):
            self.page.get_by_role("button", name="进入示例检查", exact=True).wait_for()
            self._mark("prepare")
        return result

    def switch(self, version, reference):
        from .official import SampleTestError
        labels = {"VULNERABLE": "切换到问题版", "EVIDENCE_LIMITED": "切换到观察受限版", "FIXED": "应用示例修复"}
        self._goto("/workspace")
        self.page.get_by_text("观察条件与示例修复", exact=True).click()
        self.page.get_by_role("button", name=labels[version], exact=True).click()
        result, body = self._response("/api/experience/official-sample/version",
            lambda: self.page.get_by_role("button", name="确认切换", exact=True).click())
        if body.get("version") != version or body.get("repair_reference") != reference:
            raise SampleTestError("GUI_VERSION_REFERENCE_MISMATCH")
        self._mark("switch-" + version.lower())
        return result

    def submit(self, project, expected_body, change_id):
        from .official import SampleTestError
        self._goto("/tests" + ("?" + urlencode({"change_id": change_id}) if change_id else ""))
        result, body = self._response(f"/api/projects/{project}/runs",
            lambda: self.page.get_by_role("button", name="开始检查", exact=True).click(), accepted=(202,))
        if (body.get("schema_version") != "2" or body.get("change_id") != change_id
                or body.get("expected_plan_fingerprint") != expected_body["expected_plan_fingerprint"]
                or not body.get("idempotency_key") or set(body) - {"schema_version", "change_id", "expected_plan_fingerprint", "idempotency_key"}):
            raise SampleTestError("GUI_CHECK_SUBMISSION_MISMATCH")
        self._mark("submit-check")
        return result

    def checkpoint(self, event, payload):
        from .official import SampleTestError
        if event.endswith("-result"):
            self._goto("/tests?" + urlencode({"run_id": payload["run_id"]}))
            self.page.locator('section[aria-label="当前检查判断"]').get_by_role("heading", name=payload["story"]["judgement"], exact=True).wait_for()
            if event == "fixed-result":
                self.page.get_by_text("原题复验通过", exact=True).wait_for()
            self.page.screenshot(path=str(self.audit_dir / (event + ".png")), full_page=True)
        elif event in {"limited-ready", "fixed-ready"}:
            self._goto("/workspace")
            if not payload.get("project_id"):
                raise SampleTestError("GUI_SAMPLE_PROJECT_MISSING")
            self.page.get_by_role("button", name="进入示例检查", exact=True).wait_for()
        elif event == "evidence-and-repair":
            runs = payload["runs"]
            if not runs:
                raise SampleTestError("GUI_ORIGINAL_REPAIR_MISSING")
            self._goto("/tests?" + urlencode({"run_id": runs[-1]["run_id"]}))
            self.page.get_by_text("原题复验通过", exact=True).wait_for()
            self.page.get_by_role("button", name="查看原问题", exact=True).click()
            self.page.get_by_role("button", name="查看定位证据", exact=True).click()
            self.page.get_by_role("dialog", name="已发布证据", exact=True).wait_for()
            self.page.get_by_role("heading", name="观察记录", exact=True).first.wait_for()
            self.page.screenshot(path=str(self.audit_dir / "original-evidence.png"), full_page=True)
            self.page.locator(".ant-drawer-close").click()
            self._goto("/changes")
            self.page.get_by_role("heading", name="原题复验通过", exact=True).first.wait_for()
        else:
            raise SampleTestError("GUI_CHECKPOINT_UNKNOWN")
        self._mark(event)

    def shutdown(self):
        self.page.get_by_role("button", name="设置与更多", exact=False).click()
        self.page.get_by_role("menuitem", name="退出界鉴", exact=False).click()
        self.page.get_by_role("dialog", name="退出界鉴？", exact=True).wait_for()
        result, _ = self._response("/api/system/shutdown",
            lambda: self.page.get_by_role("button", name="安全退出", exact=True).click())
        self._mark("exit")
        return result
