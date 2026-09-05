# 验证进程运行时中的进程控制与退出回收。

from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace

import pytest

import product.backend.infra.runtime.process.control as process_control
import product.backend.infra.runtime.process.tree as tree
from product.backend.core.errors import JiejianError
from product.backend.infra.runtime.process.tree import (
    controller_for,
    release_process_tree,
    spawn_managed_process,
    terminate_process_tree,
)


class _Process:
    pid = 4321

    def __init__(self) -> None:
        self.killed = False
        self.wait_timeout: float | None = None

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float) -> int:
        self.wait_timeout = timeout
        return 0


def test_windows_force_termination_targets_only_owned_process_tree(monkeypatch) -> None:
    calls: list[tuple[object, float]] = []
    monkeypatch.setattr(
        process_control,
        "terminate_process_tree",
        lambda process, timeout: calls.append((process, timeout)),
    )
    process = _Process()

    process_control.force_terminate_process_tree(process, 1.5)

    assert calls == [(process, 1.5)]
    assert process.killed is False
    assert process.wait_timeout is None


@pytest.mark.process
def test_managed_tree_reclaims_descendant_after_root_exits() -> None:
    command = [
        sys.executable,
        "-B",
        "-c",
        (
            "import subprocess,sys; "
            "child=subprocess.Popen([sys.executable,'-B','-c','import time; time.sleep(60)']); "
            "print(child.pid, flush=True)"
        ),
    ]
    process = spawn_managed_process(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        assert process.stdout is not None
        descendant_pid = int(process.stdout.readline().strip())
        process.stdout.close()
        process.wait(timeout=5)
        controller = controller_for(process)
        assert controller is not None
        assert descendant_pid > 0
        assert controller.has_exited() is False

        release_process_tree(process, timeout=5)
    finally:
        if controller_for(process) is not None:
            terminate_process_tree(process, timeout=5)


@pytest.mark.parametrize("operation", ["release_process_tree", "terminate_process_tree"])
def test_failed_tree_cleanup_preserves_controller_and_live_tree(monkeypatch, operation):
    process = _Process()
    process.poll = lambda: 0
    controller = tree.ProcessTreeController.attach(process, native=False)
    controller._kernel_identity = {"kind": "test-tree", "name": "owned"}
    alive = [True]
    monkeypatch.setattr(controller, "has_exited", lambda: not alive[0])
    method = "release" if operation == "release_process_tree" else "terminate"

    def cleanup(timeout):
        if alive[0]:
            raise TimeoutError("injected cleanup timeout")
        controller.close()

    monkeypatch.setattr(controller, method, cleanup)
    with pytest.raises(JiejianError, match="子进程树未能"):
        getattr(tree, operation)(process, 0.01)
    assert controller_for(process) is controller
    assert controller.kernel_identity == {"kind": "test-tree", "name": "owned"}
    assert not controller._closed
    assert not tree.process_tree_has_exited(process)
    alive[0] = False
    getattr(tree, operation)(process, 0.01)
    assert controller_for(process) is None
    assert controller._closed
    release_process_tree(process)


def test_close_handle_failure_preserves_handle_until_success(monkeypatch):
    process = _Process()
    process.poll = lambda: 0
    controller = tree.ProcessTreeController.attach(process, native=False)
    controller._job_handle = 123
    controller._kernel_identity = {"kind": "windows-job", "name": "test-owned"}
    monkeypatch.setattr(tree, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(tree, "_active_job_processes", lambda handle: 0)
    calls = []

    def close_handle(handle):
        calls.append(handle)
        if len(calls) == 1:
            raise OSError("injected CloseHandle failure")

    monkeypatch.setattr(tree, "_close_handle", close_handle)
    with pytest.raises(JiejianError):
        release_process_tree(process)
    assert controller_for(process) is controller
    assert controller._job_handle == 123
    assert controller._closed is False
    assert controller.has_exited() is True
    release_process_tree(process)
    assert calls == [123, 123]
    assert controller._job_handle is None
    assert controller._closed is True
    controller.close()
    assert calls == [123, 123]


def test_unregistered_terminate_retains_fallback_for_retry(monkeypatch):
    process = _Process()
    process.poll = lambda: None
    process.terminate = lambda: None
    original_wait = process.wait
    process.wait = lambda **_: (_ for _ in ()).throw(OSError("injected wait failure"))
    with pytest.raises(JiejianError):
        terminate_process_tree(process, 0.01)
    controller = controller_for(process)
    assert controller is not None and not controller._closed
    assert controller.kernel_identity == {}
    process.wait = original_wait
    terminate_process_tree(process, 0.01)
    assert controller_for(process) is None
    assert controller._closed
