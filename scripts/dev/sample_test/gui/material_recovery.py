# 通过真实产品页面核对材料回执、刷新恢复与停止后重开；不写入模拟准备状态或检查结论。
from urllib.parse import urlparse
from playwright.sync_api import expect
from scripts.dev.sample_test.harness.state import SampleTestError


def _capture_sizes(gui, name, ready):
    page = gui.page
    for theme in ("light", "dark"):
        page.evaluate("theme => localStorage.setItem('jiejian.theme', theme)", theme)
        page.reload(wait_until="networkidle")
        ready().wait_for()
        for width in (2560, 1280, 600, 390):
            page.set_viewport_size({"width": width, "height": 1440 if width == 2560 else 1000})
            page.wait_for_timeout(180)
            if page.evaluate("document.documentElement.scrollWidth > innerWidth + 2"):
                raise SampleTestError(f"MATERIAL_LAYOUT_OVERFLOW:{name}:{theme}:{width}")
            gui.capture(f"{name}-{theme}-{width}")
    page.evaluate("localStorage.setItem('jiejian.theme', 'light')")
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.reload(wait_until="networkidle")
    ready().wait_for()


def verify_material_reuse(gui, project_id):
    client, page = gui.client, gui.page
    before = client.call("GET", f"/api/projects/{project_id}/preparation")
    if not before["preparation_complete"]:
        raise SampleTestError("MATERIAL_REUSE_REQUIRES_CURRENT_PREPARATION")
    gui._goto("/tests?materials=1")
    table = lambda: page.get_by_role("table", name="检查材料清单")
    table().wait_for()
    _capture_sizes(gui, "materials-overview", table)
    group = page.locator(".material-group").filter(has=page.get_by_text("结果证明", exact=True))
    group.get_by_role("button", name="查看", exact=True).click()
    group.get_by_role("button", name="查看与更新", exact=True).first.click()
    heading = lambda: page.get_by_role("heading", name="更新结果证明", exact=True)
    heading().wait_for()
    _capture_sizes(gui, "material-detail", heading)
    page.get_by_role("button", name="查看证明要求与来源能力", exact=True).click()
    page.get_by_role("button", name="返回准备材料", exact=True).wait_for()
    page.get_by_role("heading", name="来源声明了什么能力", exact=True).wait_for()
    gui.capture("material-source-capabilities")
    page.get_by_role("button", name="返回准备材料", exact=True).click()
    heading().wait_for()
    expect(page.get_by_role("button", name="查看证明要求与来源能力", exact=True)).to_be_focused()
    page.get_by_text("录制新的材料", exact=True).click()
    page.get_by_role("button", name="准备新的录制", exact=True).click()
    page.get_by_role("heading", name="录制新的替换材料", exact=True).wait_for()
    expect(page.get_by_role("button", name="打开浏览器并开始准备", exact=True)).to_be_enabled()
    gui.capture("material-recording-entry")
    page.get_by_role("button", name="返回检查准备", exact=True).click()
    heading().wait_for()
    preview_button = page.get_by_role("button", name="核对本次影响", exact=True)
    preview_button.focus()
    gui._response(f"/api/projects/{project_id}/preparation/changes/preview",
        lambda: page.keyboard.press("Enter"))
    page.get_by_role("button", name="确认沿用材料", exact=True).wait_for()
    gui.capture("material-impact-preview")
    receipt, command = gui._response(f"/api/projects/{project_id}/preparation/changes",
        lambda: page.get_by_role("button", name="确认沿用材料", exact=True).click())
    if receipt["result"] != "RECHECKED" or receipt["updates"]:
        raise SampleTestError("MATERIAL_RECHECK_CHANGED_BINDINGS")
    stored = client.call("GET", f"/api/projects/{project_id}/preparation/changes/{command['operation_id']}")
    if stored != receipt or client.call("GET", f"/api/projects/{project_id}/preparation") != before:
        raise SampleTestError("MATERIAL_RECEIPT_OR_BINDING_DRIFT")
    page.get_by_text("材料已保存并重新核对。已有检查与证据保持原样。", exact=True).wait_for()
    page.get_by_role("button", name="返回材料", exact=True).click()
    table().wait_for()
    page.wait_for_function("document.activeElement?.hasAttribute('data-material-key')")
    gui._mark("material-reuse-recovery")


def verify_environment_restart(gui, project_id):
    from scripts.dev.sample_test.current_api import project_run_ids, prepare_current
    client, page = gui.client, gui.page
    before = client.call("GET", "/api/experience/official-sample")
    historical_runs = project_run_ids(client, project_id)
    gui._goto("/environment")
    page.get_by_role("button", name="停止官方示例", exact=True).click()
    stopped, _ = gui._response("/api/experience/official-sample/stop",
        lambda: page.get_by_role("button", name="确认停止", exact=True).click())
    if stopped["project_id"] != project_id or stopped["recovery_state"] != "EXITED" or not stopped["workspace_retained"]:
        raise SampleTestError("SAMPLE_STOP_LOST_WORKSPACE")
    heading = lambda: page.get_by_role("heading", name="从全新示例开始", exact=True)
    heading().wait_for()
    _capture_sizes(gui, "environment-recovery", heading)
    page.get_by_role("button", name="启动示例", exact=True).click()
    restarted, _ = gui._response("/api/experience/official-sample/start",
        lambda: page.get_by_role("dialog", name="启动官方示例？").get_by_role("button", name="启动示例", exact=True).click())
    new_project = restarted["project_id"]
    if (new_project == project_id or restarted["experience_id"] == before["experience_id"]
            or restarted["scenario_version"] != "BASELINE" or restarted["scenario_prepared"]):
        raise SampleTestError("SAMPLE_RESTART_SCOPE_INVALID")
    if (client.call("GET", f"/api/projects/{project_id}")["status"] != "ARCHIVED"
            or client.call("GET", f"/api/projects/{new_project}/business-boundaries")["permission_intents"]
            or client.call("GET", f"/api/projects/{new_project}/test-identities")
            or project_run_ids(client, new_project)):
        raise SampleTestError("SAMPLE_RESTART_INHERITED_OLD_STATE")
    gui._goto("/permissions")
    page.get_by_role("button", name="使用已提供的权限提案", exact=True).wait_for()
    gui.capture("fresh-sample-permissions")
    prepare_current(client, new_project, initial=True, gui=gui)
    gui._goto("/tests?materials=1")
    page.get_by_role("table", name="检查材料清单").wait_for()
    gui.capture("materials-after-restart")
    if not client.call("GET", f"/api/projects/{new_project}/preparation")["preparation_complete"]:
        raise SampleTestError("SAMPLE_RESTART_COULD_NOT_PREPARE")
    if project_run_ids(client, project_id) != historical_runs:
        raise SampleTestError("SAMPLE_RESTART_CHANGED_CHECK_HISTORY")
    gui._mark("environment-restart-recovery")
    return urlparse(restarted["origin"]).port, new_project
