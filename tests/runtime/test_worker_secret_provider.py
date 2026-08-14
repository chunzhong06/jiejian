from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import jiejian.runtime.worker_manager as worker_manager_module
from jiejian.execution.process_environment import minimal_process_environment
from jiejian.runtime.worker_manager import LocalWorkerManager


def test_worker_manager_receives_only_requested_secret_names(tmp_path: Path) -> None:
    requested: list[tuple[str, ...]] = []
    manager = LocalWorkerManager(
        tmp_path / "var",
        lambda **kwargs: None,
        environment_provider=lambda names: requested.append(tuple(names)) or {"ONE": "1"},
    )

    assert manager._environment_provider(("ONE",)) == {"ONE": "1"}
    assert requested == [("ONE",)]


def test_worker_loop_resolves_request_secrets_and_keeps_dispatch_filter(
    tmp_path: Path, monkeypatch
) -> None:
    requested: list[tuple[str, ...]] = []
    dispatched: dict[str, object] = {}
    job = SimpleNamespace(job_id="job-1", run_id="run-1", request_hash="hash-1")
    request = SimpleNamespace(
        project_snapshot=SimpleNamespace(
            identities=(
                SimpleNamespace(secret_ref="env:PRIMARY"),
                SimpleNamespace(secret_ref="env:COMPARISON"),
            )
        )
    )

    class FakeRequestStore:
        def __init__(self, var_dir: Path) -> None:
            assert var_dir == (tmp_path / "var").resolve()

        def load(self, job_id: str, *, expected_hash: str):
            assert (job_id, expected_hash) == ("job-1", "hash-1")
            return request

    class FakeProcess:
        def poll(self) -> int:
            return 0

    class FakeDispatcher:
        def __init__(self, *, environ, **kwargs) -> None:
            dispatched["environ"] = dict(environ)

        def start(self, *, secret_names, **kwargs) -> FakeProcess:
            dispatched["secret_names"] = tuple(secret_names)
            return FakeProcess()

    class StopAfterOneStep:
        calls = 0

        def is_set(self) -> bool:
            self.calls += 1
            return self.calls > 1

        def wait(self, timeout: float) -> None:
            assert timeout == 0.1

    monkeypatch.setattr(worker_manager_module, "ExecutionRequestStore", FakeRequestStore)
    monkeypatch.setattr(worker_manager_module, "WorkerDispatcher", FakeDispatcher)
    manager = LocalWorkerManager(
        tmp_path / "var",
        lambda **kwargs: None,
        environment_provider=lambda names: requested.append(tuple(names))
        or {"PRIMARY": "one", "COMPARISON": "two", "EXTRA": "must-not-inject"},
    )
    manager._next_job = lambda: job
    manager._stop = StopAfterOneStep()

    manager._loop()

    assert requested == [("PRIMARY", "COMPARISON")]
    assert dispatched["environ"] == {
        "PRIMARY": "one",
        "COMPARISON": "two",
        "EXTRA": "must-not-inject",
    }
    assert dispatched["secret_names"] == ("PRIMARY", "COMPARISON")
    filtered = minimal_process_environment(
        dispatched["environ"], secret_names=dispatched["secret_names"]
    )
    assert filtered["PRIMARY"] == "one"
    assert filtered["COMPARISON"] == "two"
    assert "EXTRA" not in filtered
