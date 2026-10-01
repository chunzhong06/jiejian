# 业务提案与人类确认的真实页面操作。
import re
from .session import GuiSession


class BoundariesActions(GuiSession):
    def propose(self):
        self._goto("/permissions")
        result, _ = self._response("/api/experience/official-sample/boundary-proposal",
            lambda: self.page.get_by_role("button", name="使用已提供的权限提案", exact=True).click())
        self.page.get_by_role("heading", name="核对本次业务变更", exact=True).wait_for()
        self.capture("boundary-approval")
        return result

    def approve(self, project, proposal):
        from scripts.dev.sample_test.harness.state import SampleTestError
        self._goto("/permissions")
        self.page.get_by_role("heading", name="核对本次业务变更", exact=True).wait_for()
        self.page.get_by_role("checkbox", name="我已核对本次变更和沿用的业务要求", exact=True).check()
        result, body = self._response(f"/api/projects/{project}/business-boundaries/proposals/{proposal.proposal_id}/approve",
            lambda: self.page.get_by_role("button", name="确认这组业务边界", exact=True).click())
        if body.get("expected_fingerprint") != proposal.proposal_fingerprint:
            raise SampleTestError("GUI_APPROVAL_REFERENCE_MISMATCH")
        self._mark("human-approve")
        return result

    def _open_maintenance(self):
        """沿权限详情进入代码关联草稿，不从隐藏表单直接提交。"""
        self._goto("/permissions")
        self.page.get_by_role("button", name=re.compile(r"^详\s*情$")).first.click()
        self.page.locator("summary").filter(has_text="当前代码定位").click()
        self.page.get_by_role("button", name="管理业务对象与代码关联", exact=True).click()
        self.page.get_by_role("button", name="核对代码关联", exact=True).wait_for()

    def maintenance(self, project):
        self._open_maintenance()
        self.capture("boundary-maintenance-entry")
        result, _ = self._response(f"/api/projects/{project}/business-boundaries/maintenance-proposals",
            lambda: self.page.get_by_role("button", name="核对代码关联", exact=True).click())
        self.page.get_by_role("heading", name="核对本次业务变更", exact=True).wait_for()
        self._mark("maintenance-proposal")
        return result
