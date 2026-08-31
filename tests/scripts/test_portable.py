# 验证 Windows x64 Portable 的单一 Base Tree、离线相对启动、双包组成与仓库外真实烟测。

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import os
import shutil
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path
from types import ModuleType

import pytest
from playwright.sync_api import sync_playwright
from scripts.dev.sample_test import official


ROOT = Path(__file__).parents[2]
BUILDER_PATH = ROOT / "scripts" / "build" / "portable.py"
ARTIFACT_ROOT = ROOT / "var" / "development" / "release" / "artifacts"
RELEASE_NAME = "JieJian-WebV1-1.0.13-Windows-x64"


def _load_module(path: Path, name: str) -> ModuleType:
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _builder() -> ModuleType:
    return _load_module(BUILDER_PATH, f"portable_builder_{uuid.uuid4().hex}")


def _driver() -> ModuleType:
    return official


def test_portable_launcher_is_relative_offline_and_uses_installed_product() -> None:
    builder = _builder()

    assert builder.RELEASE_VERSION == "1.0.13"
    assert builder.RELEASE_NAME == RELEASE_NAME
    assert "%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" in builder._START_CMD
    assert "%~dp0" in builder._START_CMD
    launcher = builder._START_PS1
    assert 'Join-Path $PSScriptRoot ".."' in launcher
    assert '"JIEJIAN_RUNTIME_MODE"' not in launcher
    assert '$env:JIEJIAN_RUNTIME_MODE = "portable"' in launcher
    assert "$env:JIEJIAN_RELEASE_ROOT = $releaseRoot" in launcher
    assert "$env:JIEJIAN_PLAYWRIGHT_EXECUTABLE" in launcher
    assert "$env:PLAYWRIGHT_BROWSERS_PATH" in launcher
    assert 'Lib\\site-packages\\product\\frontend\\dist' in launcher
    assert '"-m", "product.backend.cli"' in launcher
    assert '"--official-sample-root"' in launcher
    assert "Remove-Item Env:JIEJIAN_PROJECT_ROOT" in launcher
    for forbidden in (
        "scripts\\start.ps1",
        "prepare-sourceruntime",
        "invoke-webrequest",
        "start-bitstransfer",
        "conda ",
        "uv ",
        "pip ",
        "pnpm",
        "npm ",
    ):
        assert forbidden not in launcher.lower()


def test_portable_runtime_files_freeze_layout_metadata_and_windows_encoding(tmp_path: Path) -> None:
    builder = _builder()
    base = tmp_path / RELEASE_NAME
    (base / "runtime").mkdir(parents=True)

    builder._write_runtime_files(
        base,
        {
            "python_version": "3.13.13",
            "wheel_version": "1.0.13",
            "playwright_version": "1.58.0",
            "chromium_revision": "1228",
        },
    )

    assert {path.name for path in base.iterdir()} == {"README.txt", "runtime", "start.cmd"}
    assert (base / "start.cmd").read_bytes().startswith(b"@echo off\r\n")
    assert (base / "README.txt").read_bytes().startswith(b"\xef\xbb\xbf")
    start_ps1 = (base / "runtime" / "start.ps1").read_bytes()
    assert start_ps1.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in start_ps1
    release = json.loads((base / "runtime" / "release.json").read_text(encoding="utf-8"))
    assert release == {
        "schema_version": "1",
        "product": "JieJian Web V1",
        "version": "1.0.13",
        "package_version": "1.0.13",
        "platform": "windows",
        "architecture": "x64",
        "runtime_layout_version": "1",
        "python_version": "3.13.13",
        "playwright_version": "1.58.0",
        "chromium_revision": "1228",
    }


def test_full_and_nosamples_archives_share_exact_product_tree(tmp_path: Path) -> None:
    builder = _builder()
    base = tmp_path / "base"
    samples = tmp_path / "samples"
    (base / "runtime").mkdir(parents=True)
    (base / "start.cmd").write_text("start", encoding="ascii")
    (base / "runtime" / "release.json").write_text("{}", encoding="ascii")
    (samples / "web" / "collaboration_space").mkdir(parents=True)
    (samples / "web" / "collaboration_space" / "sample.json").write_text("{}", encoding="ascii")
    full = tmp_path / "full.zip"
    nosamples = tmp_path / "nosamples.zip"

    builder._write_zip(full, base, samples)
    builder._write_zip(nosamples, base, None)

    assert builder._archive_content(full, without_samples=False) == builder._archive_content(
        nosamples, without_samples=True
    )
    with zipfile.ZipFile(full) as archive:
        assert f"{RELEASE_NAME}/samples/web/collaboration_space/sample.json" in archive.namelist()
    with zipfile.ZipFile(nosamples) as archive:
        assert all("/samples/" not in name for name in archive.namelist())


def test_portable_tree_rejects_repository_paths_and_local_wheel_metadata(tmp_path: Path) -> None:
    builder = _builder()
    base = tmp_path / "base"
    site_packages = base / "runtime" / "python" / "Lib" / "site-packages"
    site_packages.mkdir(parents=True)
    leaked = base / "runtime" / "leak.txt"
    leaked.write_text(str(ROOT.resolve()), encoding="utf-8")

    with pytest.raises(RuntimeError, match="泄漏构建仓库绝对路径"):
        builder._validate_tree_content(base, ROOT)

    leaked.unlink()
    direct_url = site_packages / "jiejian-1.0.13.dist-info" / "direct_url.json"
    direct_url.parent.mkdir()
    direct_url.write_text("{}", encoding="ascii")
    with pytest.raises(RuntimeError, match="direct_url"):
        builder._validate_tree_content(base, ROOT)


def test_portable_runtime_prunes_dependency_tests_and_generated_python_artifacts(
    tmp_path: Path,
) -> None:
    builder = _builder()
    python = tmp_path / "runtime" / "python" / "python.exe"
    site_packages = python.parent / "Lib" / "site-packages"
    dependency_tests = site_packages / "dependency" / "tests"
    dependency_tests.mkdir(parents=True)
    (dependency_tests / "test_runtime.py").write_text("raise AssertionError", encoding="utf-8")
    metadata = site_packages / "jiejian-1.0.13.dist-info"
    metadata.mkdir()
    (metadata / "direct_url.json").write_text("{}", encoding="ascii")
    cache = site_packages / "dependency" / "__pycache__"
    cache.mkdir()
    (cache / "runtime.pyc").write_bytes(b"cache")
    runtime_module = site_packages / "dependency" / "runtime.py"
    runtime_module.write_text("VALUE = 1", encoding="ascii")

    builder._prune_installed_runtime(python)

    assert not dependency_tests.exists()
    assert not (metadata / "direct_url.json").exists()
    assert not cache.exists()
    assert runtime_module.is_file()


def test_portable_build_owns_temp_and_publishes_six_stable_progress_stages(
    tmp_path: Path,
) -> None:
    builder = _builder()
    temporary = tmp_path / "release" / "build" / "temp"

    environment = builder._runtime_environment(tmp_path / "uv-cache", temporary)

    assert environment["TEMP"] == str(temporary.resolve())
    assert environment["TMP"] == str(temporary.resolve())
    assert temporary.is_dir()
    build_source = inspect.getsource(builder.build)
    positions = [build_source.index(f"_progress({step},") for step in range(1, 7)]
    assert positions == sorted(positions)
    assert "flush=True" in inspect.getsource(builder._progress)


def _verify_checksum(path: Path, expected: str) -> None:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == expected


def _portable_environment() -> dict[str, str]:
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.upper().startswith("JIEJIAN_")
        and name.upper() not in {"PYTHONHOME", "PYTHONPATH", "PLAYWRIGHT_BROWSERS_PATH"}
    }
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def _portable_chromium(release: Path) -> Path:
    """只接受发行包内唯一 headed Chromium，供 Recording UIA 校验进程身份。"""

    candidates = tuple(
        path
        for path in (release / "runtime" / "playwright").rglob("chrome.exe")
        if "chromium-" in path.as_posix() and "chrome-win" in path.as_posix()
    )
    assert len(candidates) == 1, candidates
    return candidates[0]


def _accept_full_delivery(
    driver: ModuleType,
    release: Path,
    page,
    client,
    audit_dir: Path,
    state,
    identities: dict[str, str],
) -> int:
    """在 full Portable 内完成持续验证主流程和一次真实 BLOCK 代表性检查。"""

    experience = driver._start_guided_experience(page, client, audit_dir, state)
    project_id = str(experience["project_id"])
    sample_port = int(str(experience["origin"]).rsplit(":", 1)[1])
    role_ids, action_ids = driver._confirm_understanding(client, project_id)
    page.goto(client.origin + "/#/application", wait_until="networkidle")
    page.get_by_role("heading", name="应用接入").wait_for()

    # 身份一经写入 Credential Manager 就同步给外层，后续任意首错都能走正式 reset 清理。
    identities.update(driver._prepare_identities(client, project_id))
    page.goto(client.origin + "/#/identities", wait_until="networkidle")
    page.get_by_role("heading", name="测试账号").wait_for()

    page.goto(client.origin + "/#/flows", wait_until="networkidle")
    page.get_by_role("heading", name="业务流程").wait_for()
    recording_id = driver._record_flow(
        client,
        project_id,
        action_ids[driver.EXPORT_ACTION_KEY],
        identities["project_owner"],
        _portable_chromium(release),
        state,
    )
    driver._confirm_safety(client, recording_id)
    view_recording_id = driver._record_flow(
        client,
        project_id,
        action_ids[driver.VIEW_ACTION_KEY],
        identities["project_owner"],
        _portable_chromium(release),
        state,
        flow_kind="view",
    )
    driver._confirm_safety(client, view_recording_id, flow_kind="view")

    driver._confirm_permissions(
        page,
        client,
        audit_dir,
        project_id,
        action_ids,
        role_ids,
    )
    page.get_by_role("heading", name="验证运行").wait_for()
    result = driver._run_case(
        client,
        project_id,
        identities,
        state,
        name="portable-vulnerable",
        authorization_order="ENQUEUE_BEFORE_AUTHORIZE",
        blob_observation="AVAILABLE",
        expected_verdict="BLOCK",
        expected_issue="VULNERABLE",
        action_ids=action_ids,
    )

    page.goto(client.origin + "/#/results", wait_until="networkidle")
    expected_headline = str(result["presentation"]["headline"])
    # 路由标题先出现时结果请求仍可能在途，必须等待权威结果标题替换加载占位文本。
    page.get_by_role("heading", name=expected_headline, exact=True).wait_for(timeout=30_000)
    assert page.locator("#result-headline").inner_text().strip() == expected_headline
    page.goto(client.origin + "/#/history", wait_until="networkidle")
    page.get_by_role("heading", name="历史变化").wait_for()
    return sample_port


def _smoke_archive(driver: ModuleType, archive: Path, root: Path, *, samples: bool) -> None:
    extraction = root / ("完整版" if samples else "无示例版")
    invocation = root / ("独立调用目录 full" if samples else "独立调用目录 nosamples")
    extraction.mkdir()
    invocation.mkdir()
    shutil.unpack_archive(archive, extraction)
    release = extraction / RELEASE_NAME
    log_path = root / ("full.log" if samples else "nosamples.log")
    process = None
    log = None
    playwright = None
    browser = None
    released = False
    identities: dict[str, str] = {}
    sample_port: int | None = None
    state = driver.HarnessState(product_ready=True)
    client = None
    try:
        assert not driver._port_open(driver.CONTROL_PORT), "默认控制端口已被占用"
        log = log_path.open("wb")
        command_shell = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")
        process = driver.spawn_managed_process(
            [command_shell, "/d", "/s", "/c", "call", str(release / "start.cmd"), "-NoOpen"],
            cwd=invocation,
            env=_portable_environment(),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            tree_name=f"jiejian-portable-{uuid.uuid4().hex}",
        )
        client = driver.ApiClient(f"http://127.0.0.1:{driver.CONTROL_PORT}")
        ready = driver._wait_product_ready(client, process, timeout=90)
        assert ready["status"] == "ready"
        assert ready["worker"] == "running"

        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(client.origin, wait_until="networkidle")
        assert page.get_by_role("heading", name="开始一次安全检查").is_visible()
        client.bind_page(page)
        sample_status = client.call("GET", "/api/experience/official-sample")
        assert sample_status["available"] is samples
        sample_button = page.get_by_role("button", name="启动官方示例")
        assert sample_button.is_disabled() is (not samples)
        if samples:
            sample_port = _accept_full_delivery(
                driver,
                release,
                page,
                client,
                root,
                state,
                identities,
            )
            driver._shutdown_owned_runtime(
                client,
                state,
                identities,
                browser,
                playwright,
                process,
                release / "var",
                sample_port,
            )
            browser = None
            playwright = None
            process = None
            released = True
        else:
            assert page.get_by_text("当前版本未包含官方示例").first.is_visible()
            client.call(
                "POST",
                "/api/system/shutdown",
                {"schema_version": "1"},
                accepted=(202,),
            )
            browser.close()
            browser = None
            playwright.stop()
            playwright = None
            assert process.wait(timeout=30) == 0
            assert driver.process_tree_has_exited(process)
            driver.release_process_tree(process, timeout=5)
            released = True
            assert not driver._port_open(driver.CONTROL_PORT)
            assert driver._runtime_locks_released(release / "var")
    except Exception as exc:
        # 首错保留之前先尽力走正式 API 清理，强制回收仍只针对本用例拥有的进程树。
        if client is not None and process is not None and process.poll() is None:
            for identity_id in identities.values():
                try:
                    client.call(
                        "POST",
                        f"/api/test-identities/{identity_id}/reset",
                        {"schema_version": "1"},
                    )
                except Exception:
                    pass
            if state.sample_started:
                try:
                    client.call(
                        "POST",
                        "/api/experience/official-sample/stop",
                        {"schema_version": "1"},
                    )
                except Exception:
                    pass
            try:
                client.call(
                    "POST",
                    "/api/system/shutdown",
                    {"schema_version": "1"},
                    accepted=(202,),
                )
            except Exception:
                pass
        if log is not None:
            log.flush()
        tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:] if log_path.is_file() else ""
        raise AssertionError(f"Portable {'full' if samples else 'nosamples'} 烟测失败：{exc}\n{tail}") from exc
    finally:
        if browser is not None:
            browser.close()
        if playwright is not None:
            playwright.stop()
        if process is not None:
            if process.poll() is None:
                driver.terminate_process_tree(process, timeout=10)
            if not released:
                driver.release_process_tree(process, timeout=5)
        if log is not None:
            log.close()


@pytest.mark.skipif(
    os.name != "nt" or os.environ.get("JIEJIAN_RUN_PORTABLE_PROBE") != "1",
    reason="真实 Portable 仓库外验收需要显式启用",
)
def test_real_full_and_nosamples_portables_start_outside_repository() -> None:
    full = ARTIFACT_ROOT / f"{RELEASE_NAME}.zip"
    nosamples = ARTIFACT_ROOT / f"{RELEASE_NAME}-nosamples.zip"
    sums = ARTIFACT_ROOT / "SHA256SUMS.txt"
    assert full.is_file() and nosamples.is_file() and sums.is_file(), "请先执行 dev.ps1 package"
    expected = {
        name: digest
        for digest, name in (line.split("  ", 1) for line in sums.read_text(encoding="ascii").splitlines())
    }
    _verify_checksum(full, expected[full.name])
    _verify_checksum(nosamples, expected[nosamples.name])

    external = ROOT.parent / f"界鉴 Portable 正式验收 {uuid.uuid4().hex}"
    external.mkdir()
    try:
        driver = _driver()
        _smoke_archive(driver, full, external, samples=True)
        _smoke_archive(driver, nosamples, external, samples=False)
    finally:
        shutil.rmtree(external, ignore_errors=True)
