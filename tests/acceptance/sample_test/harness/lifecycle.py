# 拥有本轮进程、端口与身份清理，失败清理不覆盖首错。
from __future__ import annotations

import os
import socket
import subprocess
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.runtime.process.lock import lock_is_available
from product.backend.infra.runtime.process.tree import process_tree_has_exited, release_process_tree, spawn_managed_process
import tests.acceptance.sample_test.clients.http as sample_clients_http
import tests.acceptance.sample_test.harness.state as sample_harness_state


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _wait_for(
    read: Callable[[], Any],
    accept: Callable[[Any], bool],
    *,
    timeout: float,
    label: str,
) -> Any:
    deadline = time.monotonic() + timeout
    latest: Any = None
    while time.monotonic() < deadline:
        try:
            latest = read()
            if accept(latest):
                return latest
        except sample_harness_state.SampleTestError:
            pass
        time.sleep(0.2)
    summary = latest if isinstance(latest, (str, int, float, bool, type(None))) else type(latest).__name__
    raise sample_harness_state.SampleTestError(f"等待{label}超时，最后状态: {summary}")


def _start_product(
    root: Path,
    var_dir: Path,
    *, port: int = sample_harness_state.CONTROL_PORT,
) -> tuple[subprocess.Popen[bytes], object]:
    """通过真实 start.cmd 启动本轮拥有的产品进程树。"""

    log_path = var_dir / "logs" / "sample-test-start.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("wb")
    command_shell = os.environ.get("COMSPEC")
    if not command_shell or not Path(command_shell).is_file():
        log.close()
        raise sample_harness_state.SampleTestError("L5_COMMAND_SHELL_UNAVAILABLE")
    command = [
        command_shell,
        "/d",
        "/s",
        "/c",
        "call",
        str(root / "start.cmd"),
        "-Mode",
        "Gui",
        "-VarDir",
        str(var_dir),
        "-Port", str(port),
    ]
    try:
        process = spawn_managed_process(
            command,
            cwd=root,
            env=os.environ.copy(),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            tree_name=f"jiejian-sample-test-{uuid4().hex}",
        )
    except Exception:
        log.close()
        raise
    return process, log


def _wait_source_prepare(
    receipt_path: Path,
    process: subprocess.Popen[bytes],
    *,
    timeout: float,
) -> None:
    """先等待本轮 source receipt，区分准备超时与控制面未就绪。"""

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        return_code = process.poll()
        if return_code is not None:
            raise sample_harness_state.SampleTestError(f"START_CMD_EXITED_DURING_PREPARE:{return_code}")
        if receipt_path.is_file():
            return
        time.sleep(0.2)
    raise sample_harness_state.SampleTestError("L5_SOURCE_PREPARE_TIMEOUT")


def _wait_product_ready(
    client: sample_clients_http.ApiClient,
    process: subprocess.Popen[bytes],
    *,
    timeout: float,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        return_code = process.poll()
        if return_code is not None:
            raise sample_harness_state.SampleTestError(f"START_CMD_EXITED_AFTER_PREPARE:{return_code}")
        try:
            ready = client.readiness()
        except sample_harness_state.SampleTestError:
            time.sleep(0.2)
            continue
        if ready.get("status") == "ready" and ready.get("worker") == "running":
            return ready
        time.sleep(0.2)
    raise sample_harness_state.SampleTestError("L5_CONTROL_READY_TIMEOUT")


def _cleanup_after_failure(
    client: sample_clients_http.ApiClient,
    state: sample_harness_state.HarnessState,
    identities: Mapping[str, str],
    gui=None,
) -> dict[str, object]:
    """按公开 API 收口身份、Sample 和控制面，不覆盖首个失败。"""

    report: dict[str, object] = {"actions": []}
    actions = report["actions"]
    assert isinstance(actions, list)
    if not state.product_ready:
        report.update(
            {
                "state_closed": True,
                "shutdown_requested": False,
            }
        )
        return report
    report["state_closed"] = True
    if state.active_run_job_id is not None:
        try:
            client.call("POST", f"/api/jobs/{state.active_run_job_id}/cancel")
            actions.append("check.cancel")
            _wait_for(lambda: client.call("GET", f"/api/runs/{state.active_run_id}"),
                lambda item: (item.get("job") or {}).get("state") in {"SUCCEEDED", "FAILED", "CANCELLED"},
                timeout=30, label="取消本次检查")
            state.active_run_id = state.active_run_job_id = None
        except Exception as error:
            report["check_cleanup_error"] = type(error).__name__
            report["state_closed"] = False
    if state.mcp_cleanup_pending:
        try:
            from tests.acceptance.sample_test.current_mcp import cleanup
            cleanup(client, gui, state)
            actions.append("mcp.cleanup")
        except Exception as error:
            report["mcp_cleanup_error"] = type(error).__name__
            report["state_closed"] = False
    for identity_id in identities.values():
        try:
            client.call(
                "POST",
                f"/api/test-identities/{identity_id}/reset",
                {"schema_version": "1"},
            )
            actions.append("identity.reset")
        except Exception as error:
            report.setdefault("identity_cleanup_errors", []).append(type(error).__name__)
    if state.sample_started:
        try:
            client.call("POST", "/api/experience/official-sample/stop")
            actions.append("official-sample.stop")
        except Exception as error:
            report["sample_cleanup_error"] = type(error).__name__
    try:
        client.call("POST", "/api/system/shutdown", {"schema_version": "1"}, accepted=(202,))
        actions.append("system.shutdown")
        report["shutdown_requested"] = True
    except Exception as error:
        report["shutdown_requested"] = False
        report["shutdown_error"] = type(error).__name__
    return report


def _runtime_locks_released(var_dir: Path) -> bool:
    """按系统锁可重新获取证明释放；诊断锁文件允许继续保留。"""

    runtime_paths = RuntimePaths(var_dir)
    lock_paths = (
        runtime_paths.locks / "serve.lock",
        *sorted(runtime_paths.worker_runtime.glob("*.lock")),
    )
    try:
        return all(
            lock_is_available(path)
            for path in lock_paths
            if path.exists()
        )
    except OSError:
        return False


def _shutdown_owned_runtime(
    client: sample_clients_http.ApiClient,
    state: sample_harness_state.HarnessState,
    identities: Mapping[str, str],
    browser: object,
    playwright: object,
    process: subprocess.Popen[bytes],
    var_dir: Path,
    sample_port: int | None,
    shutdown_action=None,
) -> None:
    """通过正式 API 关闭产品资源，并证明本轮端口、进程树和锁均已收口。"""

    for identity_id in identities.values():
        reset = client.call(
            "POST",
            f"/api/test-identities/{identity_id}/reset",
            {"schema_version": "1"},
        )
        if reset.get("status") != "NOT_PREPARED":
            raise sample_harness_state.SampleTestError("测试账号秘密引用没有完成受控清理")
    client.call("POST", "/api/experience/official-sample/stop")
    state.sample_started = False
    if shutdown_action is None:
        client.call("POST", "/api/system/shutdown", {"schema_version": "1"}, accepted=(202,))
    else:
        shutdown_action()
    browser.close()
    playwright.stop()
    process.wait(timeout=30)
    if process.returncode != 0:
        raise sample_harness_state.SampleTestError(f"控制面安全关闭返回 {process.returncode}")
    if not process_tree_has_exited(process):
        raise sample_harness_state.SampleTestError("L5_OWNED_PROCESS_TREE_NOT_CLOSED")
    release_process_tree(process, timeout=5)
    if _port_open(state.control_port) or (sample_port is not None and _port_open(sample_port)):
        raise sample_harness_state.SampleTestError("安全关闭后仍有受控端口占用")
    if not _runtime_locks_released(var_dir):
        raise sample_harness_state.SampleTestError("L5_RUNTIME_LOCK_NOT_RELEASED")
