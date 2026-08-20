from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

import pytest
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT / "product" / "frontend" / "dist"


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_ready(base_url: str, process: subprocess.Popen[bytes], timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError("serve process exited before /ready")
        try:
            with urllib.request.urlopen(f"{base_url}/ready", timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.1)
    raise AssertionError("serve process did not become ready")


def _stop_process_tree(process: subprocess.Popen[bytes]) -> None:
    """Stop the serve process and the demo/worker descendants it starts."""
    subprocess.run(
        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


@pytest.mark.e2e
@pytest.mark.process
@pytest.mark.slow
def test_browser_product_demo_vulnerable_reaches_published_block() -> None:
    var_dir = ROOT / "var" / f"9_6e_browser_{uuid4().hex}"
    var_dir.mkdir(parents=True, exist_ok=False)
    port = _free_loopback_port()
    base_url = f"http://127.0.0.1:{port}"
    log_path = var_dir / "serve.log"
    process: subprocess.Popen[bytes] | None = None
    try:
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONUTF8"] = "1"
        with log_path.open("wb") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "product.backend.cli",
                    "--var-dir",
                    str(var_dir),
                    "serve",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--no-open",
                    "--frontend-dir",
                    str(FRONTEND_DIR),
                ],
                cwd=ROOT,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                shell=False,
            )
            _wait_ready(base_url, process)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    page = browser.new_page()
                    page.set_default_timeout(120_000)
                    page.goto(f"{base_url}/", wait_until="domcontentloaded")
                    page.get_by_role("menuitem", name="应用接入").click()
                    demo_card = page.locator(".onboarding-demo-card").filter(has_text="权限漏洞示例")
                    demo_card.get_by_role("button", name="开始体验").click()

                    page.wait_for_url("**/#/checks/start")
                    page.get_by_role("button", name="查看检查结果").click()
                    page.get_by_text("检查结果", exact=True).wait_for()
                    page.get_by_role(
                        "heading",
                        name=re.compile(r"^发现 [1-9]\d* 个权限问题$"),
                    ).wait_for()
                    page.locator(".result-summary").get_by_text("发现权限问题", exact=True).wait_for()
                    page.get_by_text("页面或接口显示已拒绝", exact=True).first.wait_for()
                    page.get_by_text("真实资源已经发生变化", exact=True).first.wait_for()
                    page.get_by_text(
                        "表面拒绝没有阻止真实副作用",
                        exact=False,
                    ).first.wait_for()
                    page.get_by_text("执行事实", exact=True).wait_for()
                    page.get_by_text("执行已拒绝", exact=True).wait_for()
                    page.get_by_text("真实观察", exact=True).wait_for()
                    page.get_by_text("资源状态发生变化", exact=True).wait_for()
                    page.get_by_text("确定性结论", exact=True).wait_for()
                    page.locator(".evidence-timeline").get_by_text(
                        "发现可能的权限越界，需要处理",
                        exact=True,
                    ).wait_for()

                    page.get_by_role("menuitem", name="权限规则").click()
                    page.get_by_text("权限矩阵", exact=True).wait_for()
                    role_filter = page.get_by_role("combobox", name="筛选角色")
                    role_filter.click()
                    role_filter.press("Enter")
                    page.get_by_role("button", name="peer modify owner-resource 未声明").wait_for()
                    page.get_by_role("tab", name="关系图").click()
                    graph = page.get_by_role("region", name="权限关系图")
                    graph.wait_for()
                    assert graph.get_by_role("button").count() >= 3
                    identity_focus = page.get_by_role("combobox", name="聚焦身份")
                    identity_focus.click()
                    identity_focus.press("Enter")
                    page.get_by_text("正在聚焦：攻击者", exact=True).wait_for()
                finally:
                    browser.close()
    finally:
        if process is not None:
            try:
                if process.poll() is None:
                    request = urllib.request.Request(
                        f"{base_url}/api/onboarding/demo/stop",
                        method="POST",
                    )
                    with urllib.request.urlopen(request, timeout=10) as response:
                        assert response.status == 200
            finally:
                _stop_process_tree(process)
        if var_dir.exists():
            rmtree(var_dir)
        assert not var_dir.exists()
