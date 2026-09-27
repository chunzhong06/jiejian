# 验证验收脚本的独立 Windows 环境能力。
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright
from scripts.dev.sample_test import official
from scripts.dev.sample_test import windows as windows_module
from tests.scripts._support_sample_test import ROOT, _fresh_real_probe_dir

def test_recording_window_requires_a_unique_new_controlled_chromium(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    windows = windows_module
    chromium = Path(sys.executable).resolve()
    fact = windows.WindowFact(22, 100, "协作空间 · 校园数字展馆", chromium)

    class Control:
        def exists(self, timeout: float) -> bool:
            return True

    class Window:
        def child_window(self, **_kwargs):
            return Control()

    class Desktop:
        def window(self, *, handle: int):
            assert handle == 22
            return Window()

    monkeypatch.setattr(windows, "visible_top_level_windows", lambda: (fact,))
    monkeypatch.setattr(windows, "Desktop", lambda backend: Desktop())
    driver = windows.RecordingWindowDriver(frozenset({11}), chromium)
    driver.wait_until_ready(timeout=0.1)

    monkeypatch.setattr(
        windows,
        "visible_top_level_windows",
        lambda: (fact, windows.WindowFact(23, 101, fact.title, chromium)),
    )
    with pytest.raises(windows.WindowsL5Error, match="RECORDING_WINDOW_AMBIGUOUS"):
        windows.RecordingWindowDriver(frozenset({11}), chromium).wait_until_ready(timeout=0.1)

@pytest.mark.skipif(
    os.name != "nt" or os.environ.get("JIEJIAN_RUN_WINDOWS_L5") != "1",
    reason="真实 Windows UIA capability 只在明确授权的交互用户环境运行",
)
def test_real_uia_capability_invokes_html_button_and_reads_status(tmp_path: Path) -> None:
    windows = windows_module
    receipt = json.loads((ROOT / "var" / "runtime" / "source" / "receipt.json").read_text(encoding="utf-8"))
    chromium = Path(receipt["playwright"]["executable"]).resolve()
    browser_root = Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"]).resolve()
    assert chromium.is_file()
    assert chromium.is_relative_to(browser_root)
    before = windows.window_snapshot()

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(tmp_path / "uia-profile"),
            headless=False,
            executable_path=str(chromium),
        )
        try:
            page = context.pages[0]
            page.set_content(
                """<!doctype html><html><head><title>JIEJIAN UIA Probe</title></head><body>
                <button type="button" onclick="document.getElementById('status').textContent='探针已完成'">执行探针</button>
                <div id="status" role="status" aria-live="polite">等待探针</div>
                </body></html>"""
            )
            deadline = time.monotonic() + 10
            candidates = []
            while time.monotonic() < deadline:
                candidates = [
                    item
                    for item in windows.visible_top_level_windows()
                    if item.handle not in before
                    and "JIEJIAN UIA Probe" in item.title
                    and str(item.image).casefold() == str(chromium).casefold()
                ]
                if len(candidates) == 1:
                    break
                time.sleep(0.2)
            assert len(candidates) == 1
            window = windows.Desktop(backend="uia").window(handle=candidates[0].handle)
            windows._invoke_button(window, "执行探针", timeout=5)
            windows._wait_control(window, "探针已完成", "Text", timeout=5)
            assert page.locator("#status").inner_text() == "探针已完成"
        finally:
            context.close()

@pytest.mark.skipif(
    os.name != "nt" or os.environ.get("JIEJIAN_RUN_WINDOWS_L5") != "1",
    reason="真实官方样例准备只在明确授权的交互用户环境运行",
)
def test_real_official_scenario_setup_closes_before_full_l5() -> None:
    driver = official
    run_dir = _fresh_real_probe_dir()

    driver.run(ROOT, run_dir, stop_after_setup=True, verify_workspace_ui=True)

    summary = json.loads(
        (run_dir / "audit" / "sample-test" / "sample-test-summary.json").read_text(encoding="utf-8")
    )
    assert summary["scenario_setup_probe"] == "passed"
    assert summary["case_count"] == 3
    assert summary["differential_pair_count"] == 1
    assert summary["workspace_ui_probe"] == "passed"
    assert summary["control_port_closed"] is True
    assert summary["sample_port_closed"] is True
    assert summary["owned_process_tree_closed"] is True
