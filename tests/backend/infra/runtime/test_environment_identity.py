from __future__ import annotations

import sys
from pathlib import Path

from product.backend.infra.runtime.environment_identity import python_environment_report
from product.backend.infra.runtime.serve_lock import ServeLock
from product.backend.infra.runtime.service_lifetime import serve_owner_is_alive
from product.backend.infra.runtime.worker_lifetime import WorkerLifetimeLock


def test_python_environment_accepts_matching_isolated_interpreter(monkeypatch) -> None:
    monkeypatch.setenv("JIEJIAN_PYTHON_EXECUTABLE", sys.executable)
    monkeypatch.setenv("JIEJIAN_PYTHON_ENVIRONMENT_PATH", sys.prefix)
    monkeypatch.setenv("JIEJIAN_PYTHON_ENVIRONMENT_TYPE", "test")
    monkeypatch.setenv("PYTHONNOUSERSITE", "1")

    report = python_environment_report()

    assert report["ok"] is True
    assert report["executable"] == str(Path(sys.executable).resolve())
    assert report["user_site_on_sys_path"] is False


def test_python_environment_rejects_user_site_source(tmp_path: Path, monkeypatch) -> None:
    user_site = tmp_path / "user-site"
    user_site.mkdir()
    monkeypatch.setattr("site.getusersitepackages", lambda: str(user_site))
    monkeypatch.setattr(sys, "path", [str(user_site), *sys.path])

    report = python_environment_report({"PYTHONNOUSERSITE": "1"}, package_names=())

    assert report["ok"] is False
    assert report["user_site_on_sys_path"] is True
    assert "检测到 Windows 用户级 Python 包来源" in report["issues"]


def test_process_lifetime_locks_prove_exit_without_pid(tmp_path: Path) -> None:
    var_dir = tmp_path / "var"
    job_id = "job_" + "a" * 32
    worker = WorkerLifetimeLock.acquire(var_dir, job_id, "worker-test")
    serve = ServeLock.acquire(var_dir)
    try:
        assert WorkerLifetimeLock.execution_has_exited(var_dir, job_id) is False
        assert serve_owner_is_alive(serve.path, serve.owner_token) is True
        assert serve_owner_is_alive(serve.path, "wrong-token") is False
    finally:
        worker.release()
        serve.release()

    assert WorkerLifetimeLock.execution_has_exited(var_dir, job_id) is True
    assert serve_owner_is_alive(serve.path, serve.owner_token) is False
