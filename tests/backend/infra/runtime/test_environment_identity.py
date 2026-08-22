from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from product.backend.infra.runtime.environment_identity import python_environment_report
from product.backend.infra.runtime.serve_lock import ServeLock
from product.backend.infra.runtime.service_lifetime import serve_owner_is_alive
from product.backend.infra.runtime.worker_lifetime import (
    WorkerLifetimeLock,
    worker_tree_identity_path,
    worker_tree_name,
)


def test_python_environment_accepts_matching_editable_development_environment(
    tmp_path: Path, monkeypatch
) -> None:
    project_root = tmp_path / "project"
    product_origin = project_root / "product" / "__init__.py"
    monkeypatch.setenv("JIEJIAN_PYTHON_EXECUTABLE", sys.executable)
    monkeypatch.setenv("JIEJIAN_PYTHON_ENVIRONMENT_PATH", sys.prefix)
    monkeypatch.setenv("JIEJIAN_PYTHON_ENVIRONMENT_TYPE", "conda")
    monkeypatch.setenv("JIEJIAN_RUNTIME_MODE", "development")
    monkeypatch.setenv("JIEJIAN_PROJECT_ROOT", str(project_root))
    monkeypatch.setenv("PYTHONNOUSERSITE", "1")
    monkeypatch.delenv("JIEJIAN_RUNTIME_FINGERPRINT", raising=False)
    monkeypatch.setattr(
        "product.backend.infra.runtime.environment_identity._project_distribution",
        lambda: {
            "installed": True,
            "version": "0.1.0",
            "root": str(Path(sys.prefix)),
            "editable": True,
            "source_root": str(project_root),
        },
    )
    monkeypatch.setattr(
        "product.backend.infra.runtime.environment_identity._module_origin",
        lambda name: str(product_origin)
        if name == "product"
        else str(Path(sys.prefix) / "Lib" / "site-packages" / f"{name}.py"),
    )

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


def test_process_lifetime_recovery_requires_lock_tree_and_owner_proof(
    tmp_path: Path, monkeypatch
) -> None:
    var_dir = tmp_path / "var"
    job_id = "job_" + "a" * 32
    worker = WorkerLifetimeLock.acquire(var_dir, job_id, "worker-test")
    serve = ServeLock.acquire(var_dir)
    try:
        assert WorkerLifetimeLock.execution_has_exited(var_dir, job_id, "worker-test") is False
        assert serve_owner_is_alive(serve.path, serve.owner_token) is True
        assert serve_owner_is_alive(serve.path, "wrong-token") is False
    finally:
        worker.release()
        serve.release()

    assert WorkerLifetimeLock.execution_has_exited(var_dir, job_id) is False
    identity = (
        {"kind": "windows-job", "name": worker_tree_name(job_id, "worker-test")}
        if os.name == "nt"
        else {"kind": "posix-process-group", "process_group_id": 12345}
    )
    receipt = worker_tree_identity_path(var_dir, job_id)
    receipt.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "job_id": job_id,
                "lease_owner": "worker-test",
                "kernel_identity": identity,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "product.backend.infra.runtime.worker_lifetime.kernel_tree_has_exited",
        lambda value: value == identity,
    )

    assert WorkerLifetimeLock.execution_has_exited(var_dir, job_id, "wrong-owner") is False
    assert WorkerLifetimeLock.execution_has_exited(var_dir, job_id, "worker-test") is True
    assert serve_owner_is_alive(serve.path, serve.owner_token) is False
