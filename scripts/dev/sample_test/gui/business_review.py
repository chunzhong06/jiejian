# 从真实候选编辑进入独立总览，并检查账号管理布局；不替代正式权限审批或创建额外检查。
from playwright.sync_api import expect
from scripts.dev.sample_test.harness.state import SampleTestError


def _capture_layout(gui, name):
    for width in (1280, 600, 390):
        gui.page.set_viewport_size({"width": width, "height": 1000})
        gui.page.evaluate("window.scrollTo(0, 0)")
        gui.page.wait_for_timeout(180)
        if gui.page.evaluate("document.documentElement.scrollWidth > innerWidth + 2"):
            raise SampleTestError(f"BUSINESS_REVIEW_LAYOUT_OVERFLOW:{name}:{width}")
        gui.capture(f"{name}-{width}")
    gui.page.set_viewport_size({"width": 1440, "height": 1000})


def verify_business_selection(gui, project):
    gui._goto("/application")
    gui.page.get_by_role("button", name="审阅业务与权限", exact=True).click()
    area = gui.page.get_by_role("region", name="审阅业务候选", exact=True)
    area.get_by_role("heading", name="整理权限组与业务动作", exact=True).wait_for()
    _capture_layout(gui, "business-selection")
    expect(area.get_by_role("button", name="下一步：核对业务总览", exact=True)).to_have_count(1)
    area.get_by_role("button", name="下一步：核对业务总览", exact=True).click()
    expect(area.get_by_role("heading", name="核对业务总览", exact=True)).to_be_focused()
    expect(area.get_by_role("textbox")).to_have_count(0)
    _capture_layout(gui, "business-selection-review")
    # 下一步只是本地审阅；直到明确确认才请求保存业务候选，仍不批准权限。
    result, _ = gui._response(f"/api/projects/{project}/candidate-decisions",
        lambda: area.get_by_role("button", name="确认这些业务信息", exact=True).click(), method="PUT")
    if result.get("project_id") != project:
        raise SampleTestError("BUSINESS_REVIEW_PROJECT_MISMATCH")
    # 确认候选后自动进入权限页；不能等待已离开的候选页成功提示。
    gui.page.wait_for_url("**/#/permissions")
    gui.page.get_by_role("button", name="使用已提供的权限提案", exact=True).wait_for()
    gui._mark("business-selection-review")


def verify_identity_layout(gui):
    gui._goto("/tests?materials=1")
    group = gui.page.locator(".material-group").filter(has=gui.page.get_by_text("真实账号", exact=True))
    group.get_by_role("button", name="查看", exact=True).click()
    group.get_by_role("button", name="管理测试账号", exact=True).first.click()
    gui.page.get_by_role("heading", name="管理当前测试账号", exact=True).wait_for()
    _capture_layout(gui, "identity-management")
    expect(gui.page.get_by_role("textbox", name="测试账号名称", exact=True)).to_be_visible()
    gui.page.get_by_role("button", name="返回检查准备", exact=True).click()
    gui.page.get_by_role("table", name="检查材料清单", exact=True).wait_for()
    gui._mark("identity-management-layout")


def verify_maintenance_layout(gui):
    gui._goto("/permissions")
    gui.page.get_by_role("button", name="管理业务对象", exact=True).click()
    gui.page.get_by_role("button", name="核对代码关联", exact=True).wait_for()
    expect(gui.page.get_by_role("button", name="下一步：核对修改", exact=True)).to_have_count(0)
    _capture_layout(gui, "boundary-maintenance-entry")
    gui._goto("/tests")
    gui._mark("boundary-maintenance-layout")
