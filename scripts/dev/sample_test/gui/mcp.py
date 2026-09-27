# 连接授权、变化回执和配对清理的真实页面操作。
import re
from urllib.parse import urlsplit
from .session import GuiSession


class McpActions(GuiSession):
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
            .get_by_role("button", name=re.compile(r"^确\s*认$")).click())
        self.page.get_by_role("dialog", name="管理连接", exact=True).wait_for(state="hidden")

    def mcp_level(self, project, level):
        from scripts.dev.sample_test.harness.state import SampleTestError
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
        from scripts.dev.sample_test.harness.state import SampleTestError
        self._goto("/tools")
        with self.page.expect_response(lambda response: response.request.method == "GET" and response.url == self.client.origin + "/api/mcp/access") as response:
            # 已连接态展示权限面，首次态展示配置面；刷新正式页面统一回读真实连接。
            self.page.reload(wait_until="networkidle")
        view = response.value.json().get("data", {})
        if response.value.status != 200 or not view.get("client_connected") or view.get("client_name") != name:
            raise SampleTestError("GUI_MCP_CLIENT_NOT_CONNECTED")
        self.page.get_by_text(name + " 已连接到界鉴", exact=True).wait_for()
        self._mark("mcp-connected")

    def mcp_change(self, change):
        from scripts.dev.sample_test.harness.state import SampleTestError
        self._goto("/changes")
        # 页面会保留原题上下文；先明确选中本次登记记录，不能把默认所选批次当作新回执。
        self.page.get_by_role("navigation", name="修改记录", exact=True).get_by_role(
            "button", name=re.compile(re.escape(change["reason"]))).click()
        entry = self.page.get_by_role("article", name="所选代码变化", exact=True)
        entry.get_by_role("heading", name=change["reason"], exact=True).wait_for()
        entry.get_by_text(re.compile(r"^登记来源：" + re.escape(change["submitted_by"]) + r" · ")).wait_for()
        manual = self.page.locator("details").filter(has=self.page.get_by_text("手动登记代码变化", exact=True))
        if manual.count() != 1 or manual.get_attribute("open") is not None:
            raise SampleTestError("GUI_MCP_MANUAL_FORM_NOT_CLOSED")
        self.capture("mcp-change")
        self.records.append(dict(event="mcp-change", status="PASSED", project_id=change["project_id"], change_id=change["change_id"]))

    def dismiss_completion(self):
        close = self.page.get_by_role("button", name="关闭检查完成提示", exact=True)
        if close.count():
            close.click()

    def mcp_completion(self, result, original_query):
        from scripts.dev.sample_test.harness.state import SampleTestError
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
