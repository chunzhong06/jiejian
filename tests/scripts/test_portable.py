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
from scripts.dev.sample_test import current_api
from scripts.dev.sample_test.current_gui import CurrentGui
from scripts.dev.sample_test.clients.http import ApiClient
from scripts.dev.sample_test.harness.state import HarnessState, CONTROL_PORT
from scripts.dev.sample_test.harness.lifecycle import (_port_open, _wait_product_ready, _shutdown_owned_runtime, _runtime_locks_released, _cleanup_after_failure)
from product.backend.infra.runtime.process.tree import (spawn_managed_process, process_tree_has_exited, release_process_tree, terminate_process_tree)
from product.backend import __version__


ROOT = Path(__file__).parents[2]
BUILDER_PATH = ROOT / "scripts" / "build" / "portable.py"
ARTIFACT_ROOT = ROOT / "var" / "development" / "release" / "artifacts"
RELEASE_NAME = f"JieJian-WebV1-{__version__}-Windows-x64"


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


def test_portable_launcher_is_relative_offline_and_uses_installed_product() -> None:
    builder = _builder()

    assert builder.RELEASE_VERSION == __version__
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
            "wheel_version": __version__,
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
        "version": __version__,
        "package_version": __version__,
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
    direct_url = site_packages / "jiejian-1.0.16.dist-info" / "direct_url.json"
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
    metadata = site_packages / "jiejian-1.0.16.dist-info"
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


def _accept_full_delivery(page, client, audit_dir, state, identities) -> int:
    """便携版使用同一当前 GUI/API 操作，只有安装和启动身份不同。"""
    gui = CurrentGui(page, client, audit_dir)
    experience = gui.start()
    state.sample_started = True
    project_id = experience["project_id"]
    sample_port = int(experience["origin"].rsplit(":", 1)[1])
    current_api.prepare_current(client, project_id, initial=True, gui=gui)
    for identity in client.call("GET", f"/api/projects/{project_id}/test-identities"):
        identities[identity["identity_id"]] = identity["identity_id"]
    result = current_api.run_current(client, project_id, state, name="portable-problem", expected="BLOCK", gui=gui)
    gui.checkpoint("problem-result", result)
    gui.history_search(project_id, result["run_id"])
    gui.history_open(result)
    gui.history_return(result["run_id"])
    return sample_port


def _smoke_archive(archive: Path, root: Path, *, samples: bool) -> None:
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
    state = HarnessState(product_ready=True)
    client = None
    try:
        assert not _port_open(CONTROL_PORT), "默认控制端口已被占用"
        log = log_path.open("wb")
        command_shell = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")
        process = spawn_managed_process(
            [command_shell, "/d", "/s", "/c", "call", str(release / "start.cmd"), "-NoOpen"],
            cwd=invocation,
            env=_portable_environment(),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            tree_name=f"jiejian-portable-{uuid.uuid4().hex}",
        )
        client = ApiClient(f"http://127.0.0.1:{CONTROL_PORT}")
        ready = _wait_product_ready(client, process, timeout=90)
        assert ready["status"] == "ready"
        assert ready["worker"] == "running"

        playwright = sync_playwright().start()
        candidates = [item for item in (release / "runtime/playwright").rglob("chrome.exe")
            if "chromium-" in item.as_posix() and "chrome-win" in item.as_posix()]
        assert len(candidates) == 1
        browser = playwright.chromium.launch(executable_path=str(candidates[0]), headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(client.origin, wait_until="networkidle")
        page.get_by_role("main").wait_for()
        client.bind_page(page)
        sample_status = client.call("GET", "/api/experience/official-sample")
        assert sample_status["available"] is samples
        sample_button = page.get_by_role("button", name="启动官方示例")
        if samples:
            assert sample_button.is_enabled()
        elif sample_button.count():
            assert sample_button.is_disabled()
        if samples:
            sample_port = _accept_full_delivery(
                page,
                client,
                root,
                state,
                identities,
            )
            _shutdown_owned_runtime(
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
            assert sample_status["active"] is False
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
            assert process_tree_has_exited(process)
            release_process_tree(process, timeout=5)
            released = True
            assert not _port_open(CONTROL_PORT)
            assert _runtime_locks_released(release / "var")
    except Exception as exc:
        # 首错保留之前先尽力走正式 API 清理，强制回收仍只针对本用例拥有的进程树。
        if client is not None and process is not None and process.poll() is None:
            _cleanup_after_failure(client, state, identities)
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
                terminate_process_tree(process, timeout=10)
            if not released:
                release_process_tree(process, timeout=5)
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
        _smoke_archive(full, external, samples=True)
        _smoke_archive(nosamples, external, samples=False)
    finally:
        assert external.resolve().parent == ROOT.parent.resolve()
        assert external.name.startswith("界鉴 Portable 正式验收 ")
        shutil.rmtree(external, ignore_errors=True)
