# 验证本地维护只清理三类可删除内容，并保护当前会话与产品事实。

from __future__ import annotations

import os
import time
from pathlib import Path

from product.backend.infra.runtime.maintenance import LocalMaintenanceService
from product.backend.infra.runtime.worker.lifetime import WorkerLifetimeLock


def test_local_maintenance_status_and_clear_all_preserve_product_facts(
    tmp_path: Path,
) -> None:
    var_dir = tmp_path / "var"
    service = LocalMaintenanceService(
        var_dir,
        session_started_at=time.time() + 60,
    )
    assistant = service.paths.assistant_cache / "response.bin"
    log = service.paths.app_logs / "history.log"
    temporary = service.paths.temp / "orphan.bin"
    data = service.paths.data / "proof.txt"
    runtime = service.paths.runtime / "frontend" / "index.html"
    development = var_dir / "development" / "tools" / "uv.exe"
    for path in (assistant, log, temporary, data, runtime, development):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"proof")

    status = service.status()
    preview = service.operate("clear-all", dry_run=True)
    result = service.operate("clear-all", confirmed=True, dry_run=False)

    assert set(status["entries"]) == {"assistant", "logs", "temporary"}
    assert status["entries"]["assistant"]["files"] == 1
    assert status["entries"]["logs"]["categories"]["app"]["files"] == 1
    assert status["entries"]["temporary"]["files"] == 1
    assert preview["estimated_bytes"] == 15
    assert not assistant.exists() and not log.exists() and not temporary.exists()
    assert data.read_bytes() == b"proof"
    assert runtime.read_bytes() == b"proof"
    assert development.read_bytes() == b"proof"
    assert result["protected"]["database"] is True
    assert result["protected"]["development_root_included"] is False


def test_runtime_repair_protects_active_sample_and_worker_paths(tmp_path: Path) -> None:
    var_dir = tmp_path / "var"
    active = var_dir / "runtime" / "official-samples" / "active"
    service = LocalMaintenanceService(
        var_dir,
        active_runtime_paths=lambda: (active,),
    )
    partial = service.paths.runtime / "browser.partial"
    invalid = service.paths.runtime / "frontend-invalid"
    active_partial = active / "state.tmp"
    worker_partial = service.paths.worker_runtime / "worker.tmp"
    partial.write_bytes(b"partial")
    invalid.mkdir()
    (invalid / ".invalid").write_text("1", encoding="utf-8")
    active_partial.parent.mkdir(parents=True)
    active_partial.write_bytes(b"active")
    worker_partial.write_bytes(b"worker")
    worker_lock = WorkerLifetimeLock.acquire(
        var_dir,
        "job_" + "a" * 32,
        "worker-test",
    )
    try:
        preview = service.operate("repair-runtime", dry_run=True)
        result = service.operate("repair-runtime", confirmed=True, dry_run=False)
    finally:
        worker_lock.release()

    assert {item["path"] for item in preview["targets"]} == {str(partial), str(invalid)}
    assert not partial.exists() and not invalid.exists()
    assert active_partial.is_file() and worker_partial.is_file()
    assert result["requires_restart"] is True


def test_startup_maintenance_applies_each_log_category_retention_and_orphan_age(
    tmp_path: Path,
) -> None:
    service = LocalMaintenanceService(
        tmp_path / "var",
        session_started_at=time.time() + 60,
    )
    now = time.time()
    app_logs: list[Path] = []
    for index in range(22):
        path = service.paths.app_logs / f"app-{index:02d}.log"
        path.write_text(str(index), encoding="utf-8")
        os.utime(path, (now - index, now - index))
        app_logs.append(path)
    old_worker = service.paths.worker_logs / "old.log"
    old_worker.write_text("old", encoding="utf-8")
    old = now - 15 * 24 * 60 * 60
    os.utime(old_worker, (old, old))
    expired = service.paths.temp / "expired"
    active = service.paths.temp / "active"
    expired.mkdir()
    active.mkdir()
    orphaned = now - 25 * 60 * 60
    os.utime(expired, (orphaned, orphaned))
    partial = service.paths.assistant_cache / ".tmp-response"
    partial.write_bytes(b"partial")

    result = service.startup_maintenance()

    assert len(list(service.paths.app_logs.glob("*.log"))) == 20
    assert not old_worker.exists()
    assert not expired.exists() and active.is_dir()
    assert not partial.exists()
    assert str(expired) in result["removed"]


def test_manual_temporary_cleanup_removes_orphaned_runtime_and_keeps_active(
    tmp_path: Path,
) -> None:
    active = tmp_path / "var" / "runtime" / "official-samples" / "active"
    service = LocalMaintenanceService(
        tmp_path / "var",
        active_runtime_paths=lambda: (active,),
    )
    orphaned_sample = service.paths.official_sample_runtime / "orphaned"
    orphaned_identity = service.paths.identity_preparations / "orphaned"
    for path in (active, orphaned_sample, orphaned_identity):
        path.mkdir(parents=True)
        (path / "state.json").write_text("{}", encoding="utf-8")

    result = service.operate("clear-temporary", confirmed=True, dry_run=False)

    assert active.is_dir()
    assert not orphaned_sample.exists() and not orphaned_identity.exists()
    assert set(result["removed"]) == {str(orphaned_sample), str(orphaned_identity)}


def test_manual_log_cleanup_keeps_current_session_logs(tmp_path: Path) -> None:
    service = LocalMaintenanceService(tmp_path / "var")
    current = service.paths.app_logs / "current.log"
    current.write_text("active", encoding="utf-8")

    status = service.status()
    result = service.operate("clear-logs", confirmed=True, dry_run=False)

    assert status["entries"]["logs"]["files"] == 0
    assert result["removed"] == []
    assert current.read_text(encoding="utf-8") == "active"
