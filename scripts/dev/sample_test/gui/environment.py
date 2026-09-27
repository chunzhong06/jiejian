# 官方环境和安全退出的真实页面操作。
from .session import GuiSession


class EnvironmentActions(GuiSession):
    def start(self):
        self._goto("/workspace")
        self.page.get_by_role("button", name="启动官方示例", exact=True).click()
        self.page.get_by_role("dialog", name="启动官方示例？").wait_for()
        result, _ = self._response("/api/experience/official-sample/start",
            lambda: self.page.get_by_role("button", name="启动问题版", exact=True).click())
        self.page.locator('[aria-label="当前需要处理的任务"]').wait_for()
        self._mark("start")
        return result

    def switch(self, version, reference):
        from scripts.dev.sample_test.harness.state import SampleTestError
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
        self._goto("/environment")
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

    def shutdown(self):
        self.page.get_by_role("button", name="设置与更多", exact=False).click()
        self.page.get_by_role("menuitem", name="退出界鉴", exact=False).click()
        self.page.get_by_role("dialog", name="退出界鉴？", exact=True).wait_for()
        result, _ = self._response("/api/system/shutdown",
            lambda: self.page.get_by_role("button", name="安全退出", exact=True).click())
        self._mark("exit")
        return result
