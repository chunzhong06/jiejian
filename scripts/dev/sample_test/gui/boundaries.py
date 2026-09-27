# 业务提案与人类确认的真实页面操作。
from .session import GuiSession


class BoundariesActions(GuiSession):
    def propose(self):
        self._goto("/permissions")
        result, _ = self._response("/api/experience/official-sample/boundary-proposal",
            lambda: self.page.get_by_role("button", name="使用已提供的权限提案", exact=True).click())
        self.page.get_by_role("heading", name="核对本次业务变更", exact=True).wait_for()
        return result

    def approve(self, project, proposal):
        from scripts.dev.sample_test.harness.state import SampleTestError
        self._goto("/permissions")
        self.page.get_by_role("heading", name="核对本次业务变更", exact=True).wait_for()
        self.page.get_by_role("textbox", name="确认或放弃原因").fill("确认本次受控示例的权限或纯实现重绑，保留原题要求")
        self.page.get_by_role("checkbox", name="我已核对本次变更和沿用的业务要求", exact=True).check()
        result, body = self._response(f"/api/projects/{project}/business-boundaries/proposals/{proposal.proposal_id}/approve",
            lambda: self.page.get_by_role("button", name="确认这组业务边界", exact=True).click())
        if body.get("expected_fingerprint") != proposal.proposal_fingerprint:
            raise SampleTestError("GUI_APPROVAL_REFERENCE_MISMATCH")
        self._mark("human-approve")
        return result

    def maintenance(self, project):
        self._goto("/permissions")
        self.page.get_by_role("button", name="管理业务对象", exact=True).click()
        result, _ = self._response(f"/api/projects/{project}/business-boundaries/maintenance-proposals",
            lambda: self.page.get_by_role("button", name="审阅全部变更", exact=True).click())
        self.page.get_by_role("heading", name="核对本次业务变更", exact=True).wait_for()
        self._mark("maintenance-proposal")
        return result
