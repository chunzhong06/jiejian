# 验证本地维护只清理三类可删除内容，并保护当前会话与产品事实。

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from product.backend.infra.runtime.maintenance import LocalMaintenanceService
from product.backend.infra.runtime.generated_files import register_generated_file, generated_file_owner
from product.backend.infra.runtime.worker.lifetime import WorkerLifetimeLock


def test_gui_profile_is_not_temporary_or_damaged_runtime(tmp_path: Path) -> None:
    service = LocalMaintenanceService(tmp_path / "var", session_started_at=time.time() + 60)
    profile = service.paths.gui_browser
    profile.mkdir(parents=True)
    for name in ("Preferences", "browser.tmp", "state.partial", ".invalid"):
        (profile / name).write_text("browser-owned", encoding="utf-8")
    for scope in ("clear-all", "repair-runtime"):
        plan = service.preview(scope)
        service.execute(str(plan["plan_id"]), expected_scope=scope)
    assert all((profile / name).is_file() for name in ("Preferences", "browser.tmp", "state.partial", ".invalid"))


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
    register_generated_file(var_dir,assistant,'assistant-cache')
    register_generated_file(var_dir,log,'app-log')

    status = service.status()
    preview = service.preview("clear-all")
    result = service.execute(str(preview["plan_id"]), expected_scope="clear-all")

    assert set(status["entries"]) == {"assistant", "logs", "temporary"}
    assert status["entries"]["assistant"]["files"] == 1
    assert status["entries"]["logs"]["categories"]["app"]["files"] == 1
    assert status["entries"]["temporary"]["files"] == 0
    assert preview["estimated_bytes"] == 10
    assert not assistant.exists() and not log.exists() and temporary.exists()
    assert any(item['relative_path'] == 'temp/orphan.bin' and item['state'] == 'UNKNOWN' for item in status['inventory'])
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
    sample_probe = service.paths.official_sample_runtime / "probe" / "state.tmp"
    worker_partial = service.paths.worker_runtime / "worker.tmp"
    partial.write_bytes(b"partial")
    invalid.mkdir()
    (invalid / ".invalid").write_text("1", encoding="utf-8")
    active_partial.parent.mkdir(parents=True)
    active_partial.write_bytes(b"active")
    sample_probe.parent.mkdir(parents=True)
    sample_probe.write_bytes(b"sample-test")
    worker_partial.write_bytes(b"worker")
    worker_lock = WorkerLifetimeLock.acquire(
        var_dir,
        "job_" + "a" * 32,
        "worker-test",
    )
    try:
        preview = service.preview("repair-runtime")
        result = service.execute(
            str(preview["plan_id"]),
            expected_scope="repair-runtime",
        )
    finally:
        worker_lock.release()

    assert preview["targets"] == []
    assert partial.exists() and invalid.exists()
    assert active_partial.is_file() and sample_probe.is_file() and worker_partial.is_file()
    assert result["requires_restart"] is False


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
        register_generated_file(service.paths.root,path,'app-log')
        os.utime(path, (now - index, now - index))
        app_logs.append(path)
    old_worker = service.paths.worker_logs / "old.log"
    old_worker.write_text("old", encoding="utf-8")
    register_generated_file(service.paths.root,old_worker,'worker-log')
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
    os.utime(partial, (orphaned, orphaned))
    register_generated_file(service.paths.root,partial,'assistant-cache')
    # 未登记文件既不删除，也不能挤占产品日志的保留名额。
    manual = [service.paths.app_logs / f"manual-{index}.log" for index in range(21)]
    for path in manual:
        path.write_text("keep", encoding="utf-8")

    result = service.startup_maintenance()

    assert sum(path.exists() for path in app_logs) == 20
    assert all(path.is_file() for path in manual)
    assert not old_worker.exists()
    assert expired.exists() and active.is_dir()
    assert not partial.exists()
    assert generated_file_owner(service.paths.root, partial) is None
    assert generated_file_owner(service.paths.root, old_worker) is None
    assert str(expired) not in result["removed"]


def test_manual_temporary_cleanup_excludes_development_validation_runtime(
    tmp_path: Path,
) -> None:
    active = tmp_path / "var" / "runtime" / "official-samples" / "active"
    service = LocalMaintenanceService(
        tmp_path / "var",
        active_runtime_paths=lambda: (active,),
    )
    orphaned_sample = service.paths.official_sample_runtime / "orphaned"
    orphaned_identity = service.paths.identity_preparations / "orphaned"
    product_temporary = service.paths.temp / "product-temporary"
    test_probe = service.paths.test / "validation-probe"
    process_gate = service.paths.process_gates / "source-receipt.json"
    for path in (active, orphaned_sample, orphaned_identity, product_temporary, test_probe):
        path.mkdir(parents=True)
        (path / "state.json").write_text("{}", encoding="utf-8")
    process_gate.write_text("protected", encoding="utf-8")

    preview = service.preview("clear-temporary")
    result = service.execute(str(preview["plan_id"]))

    assert product_temporary.exists()
    assert active.is_dir() and orphaned_sample.is_dir() and orphaned_identity.is_dir()
    assert test_probe.is_dir() and process_gate.is_file()
    assert result["removed"] == []


def test_manual_log_cleanup_keeps_current_session_logs(tmp_path: Path) -> None:
    service = LocalMaintenanceService(tmp_path / "var")
    current = service.paths.app_logs / "current.log"
    current.write_text("active", encoding="utf-8")
    register_generated_file(service.paths.root,current,'app-log')

    status = service.status()
    result = service.operate("clear-logs", confirmed=True, dry_run=False)

    assert status["entries"]["logs"]["files"] == 0
    assert result["removed"] == []
    assert current.read_text(encoding="utf-8") == "active"


def test_confirm_executes_only_frozen_plan_and_leaves_new_candidate(tmp_path: Path) -> None:
    service = LocalMaintenanceService(tmp_path / "var")
    planned = service.paths.assistant_cache / "planned.bin"
    added_later = service.paths.assistant_cache / "added-later.bin"
    planned.write_bytes(b"planned")
    register_generated_file(service.paths.root,planned,'assistant-cache')

    preview = service.preview("clear-assistant-cache")
    added_later.write_bytes(b"later")
    register_generated_file(service.paths.root,added_later,'assistant-cache')
    result = service.execute(str(preview["plan_id"]))

    assert result["counts"]["DELETED"] == 1
    assert not planned.exists()
    assert added_later.read_bytes() == b"later"


def test_confirm_reports_missing_and_changed_candidates_without_deleting(
    tmp_path: Path,
) -> None:
    service = LocalMaintenanceService(tmp_path / "var")
    missing = service.paths.assistant_cache / "missing.bin"
    changed = service.paths.assistant_cache / "changed.bin"
    missing.write_bytes(b"old")
    changed.write_bytes(b"old")
    register_generated_file(service.paths.root,missing,'assistant-cache')
    register_generated_file(service.paths.root,changed,'assistant-cache')
    preview = service.preview("clear-assistant-cache")
    missing.unlink()
    changed.write_bytes(b"changed")

    result = service.execute(str(preview["plan_id"]))
    statuses = {item["relative_path"]: item["status"] for item in result["results"]}

    assert statuses[missing.relative_to(tmp_path / "var").as_posix()] == "ALREADY_MISSING"
    assert statuses[changed.relative_to(tmp_path / "var").as_posix()] == "SKIPPED_CHANGED"
    assert changed.read_bytes() == b"changed"


def test_confirm_isolates_occupied_and_failed_items(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = LocalMaintenanceService(tmp_path / "var")
    occupied = service.paths.assistant_cache / "occupied.bin"
    failed = service.paths.assistant_cache / "failed.bin"
    deleted = service.paths.assistant_cache / "deleted.bin"
    for path in (occupied, failed, deleted):
        path.write_bytes(path.name.encode("utf-8"))
        register_generated_file(service.paths.root,path,'assistant-cache')
    preview = service.preview("clear-assistant-cache")
    original_remove = service._remove_under

    def controlled_remove(path: Path, root: Path) -> None:
        if path == occupied:
            raise PermissionError("occupied")
        if path == failed:
            raise OSError("isolated failure")
        original_remove(path, root)

    monkeypatch.setattr(service, "_remove_under", controlled_remove)
    result = service.execute(str(preview["plan_id"]))
    statuses = {item["relative_path"]: item["status"] for item in result["results"]}

    assert statuses[occupied.relative_to(tmp_path / "var").as_posix()] == "SKIPPED_IN_USE"
    assert statuses[failed.relative_to(tmp_path / "var").as_posix()] == "FAILED"
    assert statuses[deleted.relative_to(tmp_path / "var").as_posix()] == "DELETED"
    assert occupied.is_file() and failed.is_file() and not deleted.exists()
