# 验证进程运行时中的Worker 秘密信息提供器。

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import product.backend.infra.runtime.worker.supervisor as worker_supervisor_module
from product.backend.infra.runtime.process.environment import ProcessEnvironmentRole, minimal_process_environment
from product.backend.infra.runtime.worker.supervisor import LocalWorkerSupervisor
from tests.fixtures.runtime_environment import runtime_identity_environment


def test_worker_supervisor_receives_only_requested_secret_names(tmp_path: Path) -> None:
    requested: list[tuple[str, ...]] = []
    manager = LocalWorkerSupervisor(
        tmp_path / "var",
        lambda **kwargs: None,
        environment_provider=lambda names: requested.append(tuple(names)) or {"ONE": "1"},
    )

    assert manager._environment_provider(("ONE",)) == {"ONE": "1"}
    assert requested == [("ONE",)]


def test_worker_loop_resolves_identity_and_observer_secrets_and_keeps_dispatch_filter(
    tmp_path: Path, monkeypatch, runtime_request_factory, caplog
) -> None:
    requested: list[tuple[str, ...]] = []
    dispatched: dict[str, object] = {}
    job = SimpleNamespace(job_id="job-1", run_id="run-1", request_hash="hash-1")
    request = runtime_request_factory()

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
            return self.calls > 2

        def wait(self, timeout: float) -> None:
            assert timeout == 0.1

    monkeypatch.setattr(worker_supervisor_module, "ExecutionRequestStore", FakeRequestStore)
    monkeypatch.setattr(worker_supervisor_module, "WorkerDispatcher", FakeDispatcher)
    manager = LocalWorkerSupervisor(
        tmp_path / "var",
        lambda **kwargs: None,
        environment_provider=lambda names: requested.append(tuple(names))
        or {
            "JIEJIAN_TEST_TOKEN": "identity-secret-value",
            "OWNER_READ_ONLY": "observer-secret-value",
            "EXTRA": "must-not-inject",
        },
        recovery_service=SimpleNamespace(
            list_recovery_candidates=lambda _request: ()
        ),
    )
    manager._next_job = lambda: job
    manager._stop = StopAfterOneStep()

    manager._loop()

    assert requested == [("JIEJIAN_TEST_TOKEN", "OWNER_READ_ONLY")]
    assert dispatched["environ"] == {
        "JIEJIAN_TEST_TOKEN": "identity-secret-value",
        "OWNER_READ_ONLY": "observer-secret-value",
        "EXTRA": "must-not-inject",
    }
    assert dispatched["secret_names"] == ("JIEJIAN_TEST_TOKEN", "OWNER_READ_ONLY")
    filtered = minimal_process_environment(
        runtime_identity_environment(
            tmp_path / "var",
            extra=dispatched["environ"],
        ),
        role=ProcessEnvironmentRole.WORKER,
        secret_names=dispatched["secret_names"],
    )
    assert filtered["JIEJIAN_TEST_TOKEN"] == "identity-secret-value"
    assert filtered["OWNER_READ_ONLY"] == "observer-secret-value"
    assert "EXTRA" not in filtered
    request_json = request.model_dump_json()
    assert "identity-secret-value" not in request_json
    assert "observer-secret-value" not in request_json
    assert "identity-secret-value" not in caplog.text
    assert "observer-secret-value" not in caplog.text
