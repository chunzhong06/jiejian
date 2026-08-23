from __future__ import annotations

import subprocess
import sys

import pytest

from product.backend.infra.runtime import process_control
from product.backend.infra.runtime.process_tree import (
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
