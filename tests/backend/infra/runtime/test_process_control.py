from __future__ import annotations

from types import SimpleNamespace

from product.backend.infra.runtime import process_control


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
    calls: list[tuple[list[str], float]] = []
    monkeypatch.setattr(process_control.os, "name", "nt")
    monkeypatch.setattr(
        process_control.subprocess,
        "run",
        lambda command, **options: calls.append((command, options["timeout"])) or SimpleNamespace(returncode=0),
    )
    process = _Process()

    process_control.force_terminate_process_tree(process, 1.5)

    assert calls == [(["taskkill.exe", "/PID", "4321", "/T", "/F"], 1.5)]
    assert process.killed is False
    assert process.wait_timeout == 1.5
