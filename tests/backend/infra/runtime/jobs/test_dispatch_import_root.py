# 验证作业运行时中的调度子进程导入根。

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from product.backend.infra.runtime.jobs.dispatch import WORKER_LOG_MAX_BYTES, WorkerDispatcher
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.runtime.process.environment import ProcessEnvironmentRole, run_python_module
from tests.fixtures.runtime_environment import runtime_identity_environment


class _FakeProcess:
    def poll(self) -> None:
        return None


def test_worker_dispatch_uses_import_root_for_child_cwd(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_popen(command: list[str], **kwargs: object) -> object:
        captured["command"] = command
        captured.update(kwargs)
        return _FakeProcess()

    var_dir = tmp_path / "var"
    dispatcher = WorkerDispatcher(
        var_dir=var_dir,
        uow_factory=lambda: None,
        environ=runtime_identity_environment(var_dir),
        popen=fake_popen,
    )

    dispatcher.start(
        job_id="job_12345678901234567890123456789012",
        lease_owner="worker-test",
        secret_names=(),
    )

    command = captured["command"]
    assert isinstance(command, list)
    assert command[0] == sys.executable
    assert command[1:4] == [
        "-B",
        "-m",
        "product.backend.infra.runtime.process.bootstrap",
    ]
    module_index = command.index("--module")
    assert command[module_index + 1] == "product.backend.infra.runtime.worker.process"
    assert captured["cwd"] == str(RuntimePaths(var_dir).temp)
    assert captured["cwd"] != str(var_dir.resolve())
    assert command[command.index("--var-dir") + 1] == str(var_dir.resolve())


def test_worker_dispatch_captures_bootstrap_stderr_and_rotates_by_job_id(
    tmp_path: Path,
) -> None:
    job_id = "job_" + "2" * 32
    commands: list[list[str]] = []

    def fake_popen(command: list[str], **kwargs: object) -> object:
        commands.append(command)
        stderr = kwargs["stderr"]
        assert stderr is kwargs["stdout"]
        stderr.write(b"bootstrap traceback\r\n")
        return _FakeProcess()

    var_dir = tmp_path / "var"
    dispatcher = WorkerDispatcher(
        var_dir=var_dir,
        uow_factory=lambda: None,
        environ=runtime_identity_environment(
            var_dir,
            extra={"NEEDED_SECRET": "sentinel"},
        ),
        popen=fake_popen,
    )

    dispatcher.start(
        job_id=job_id,
        lease_owner="worker-test",
        secret_names=("NEEDED_SECRET",),
    )
    log_path = var_dir / "logs" / "workers" / f"{job_id}.log"
    assert log_path.read_bytes() == b"bootstrap traceback\r\n"
    assert commands[0][-2:] == ["--secret-name", "NEEDED_SECRET"]

    log_path.write_bytes(b"x" * WORKER_LOG_MAX_BYTES)
    dispatcher.start(
        job_id=job_id,
        lease_owner="worker-test",
        secret_names=("NEEDED_SECRET",),
    )

    assert log_path.read_bytes() == b"bootstrap traceback\r\n"
    assert log_path.with_name(f"{job_id}.log.1").stat().st_size == WORKER_LOG_MAX_BYTES


@pytest.mark.process
def test_real_recording_module_imports_away_from_repository_root(tmp_path: Path) -> None:
    if os.environ.get("JIEJIAN_RUNTIME_MODE") != "development":
        pytest.skip("需要通过界鉴源码启动环境执行真实导入证明")
    outside = tmp_path / "outside-repository"
    outside.mkdir()

    completed = run_python_module(
        os.environ,
        "product.backend.infra.recording.process",
        role=ProcessEnvironmentRole.RECORDING,
        cwd=outside,
        timeout_seconds=10,
    )

    assert completed.returncode == 64
    assert "RECORD_PROTOCOL_INVALID" in completed.stderr
    assert outside.resolve() != Path(__file__).parents[5].resolve()
