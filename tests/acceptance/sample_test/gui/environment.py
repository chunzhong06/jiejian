# 官方环境和安全退出的真实页面操作。
import re
from .session import GuiSession


class EnvironmentActions(GuiSession):
    def start(self):
        self._goto("/workspace")
        self.page.get_by_role("button", name="启动示例", exact=True).click()
        self.page.get_by_role("dialog", name="启动官方示例？").wait_for()
        result, _ = self._response("/api/experience/official-sample/start",
            lambda: self.page.get_by_role("dialog", name="启动官方示例？").get_by_role("button", name="启动示例", exact=True).click())
        self.page.locator('[aria-label="当前需要处理的任务"]').wait_for()
        self._mark("start")
        return result

    def switch(self, version, reference):
        from tests.acceptance.sample_test.harness.state import SampleTestError
        labels = {"VULNERABLE": "应用预设异步优化", "FIXED": "应用预设修复"}
        versions = {"BASELINE", "VULNERABLE", "EVIDENCE_LIMITED", "FIXED"}
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
        if version == "EVIDENCE_LIMITED":
            self._goto("/environment")
            self.page.get_by_text("可选体验：证据不足时会怎样", exact=True).click()
            result, body = self._response("/api/experience/official-sample/observation",
                lambda: self.page.get_by_role("button", name="使用受限观察条件", exact=True).click())
            if body.get("available") is not False:
                raise SampleTestError("GUI_OBSERVATION_CONDITION_MISMATCH")
            self._mark("switch-evidence_limited")
            return result
        self._goto("/changes")
        journey = self.page.get_by_role("button", name=re.compile(r"^(继续官方示例演练|收起官方演练)$"))
        # 工作面保留展开状态；返回时只在关闭态展开，不能把已打开的演练反向收起。
        if journey.get_attribute("aria-expanded") != "true":
            journey.click()
        if repair is not None and len(repair["tasks"]) > 1:
            eligible = [task for task in repair["tasks"] if task["status"] != "STALE"]
            selected = next(index for index, task in enumerate(eligible) if task is matches[0])
            self.page.get_by_role("combobox", name="选择待修复原题", exact=True).click()
            self.page.get_by_role("option", name=f"原问题 {selected + 1}", exact=True).click()
        self.page.get_by_role("button", name=labels[version], exact=True).click()
        result, body = self._response("/api/experience/official-sample/version",
            lambda: self.page.get_by_role("button", name="应用代码变更", exact=True).click())
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
