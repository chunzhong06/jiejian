# 验证产品缓存只管理当前实例的 AI 辅助缓存和明确损坏运行时。

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from product.backend.infra.runtime.cache import CacheMaintenanceService


def test_cache_status_and_clean_only_cover_assistant_cache(tmp_path: Path) -> None:
    var_dir = tmp_path / "var"
    service = CacheMaintenanceService(var_dir)
    assistant = service.paths.assistant_cache / "response.bin"
    data = service.paths.data / "proof.txt"
    runtime = service.paths.runtime / "python" / "current" / "python.exe"
    development = var_dir / "development" / "tools" / "uv.exe"
    for path in (assistant, data, runtime, development):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"proof")

    status = service.status()
    preview = service.clean(dry_run=True)
    result = service.clean(confirmed=True, dry_run=False)

    assert set(status["entries"]) == {"assistant"}
    assert preview["targets"] == [
        {"path": str(service.paths.assistant_cache), "estimated_bytes": 5}
    ]
    assert not assistant.exists()
    assert data.read_bytes() == b"proof"
    assert runtime.read_bytes() == b"proof"
    assert development.read_bytes() == b"proof"
    assert result["protected"]["development_root_included"] is False


def test_runtime_repair_only_removes_unreferenced_damaged_paths(tmp_path: Path) -> None:
    service = CacheMaintenanceService(tmp_path / "var")
    partial = service.paths.runtime / "browser.partial"
    invalid = service.paths.runtime / "frontend-invalid"
    current = service.paths.runtime / "current.partial"
    healthy = service.paths.runtime / "frontend"
    partial.write_bytes(b"partial")
    invalid.mkdir()
    (invalid / ".invalid").write_text("1", encoding="utf-8")
    current.write_bytes(b"current")
    healthy.mkdir()
    (healthy / "index.html").write_text("ok", encoding="utf-8")
    (service.paths.runtime / "runtime-state.json").write_text(
        json.dumps({"schema_version": "1", "current_paths": [str(current)]}),
        encoding="utf-8",
    )

    preview = service.repair_runtime(dry_run=True)
    result = service.repair_runtime(confirmed=True, dry_run=False)

    targets = {item["path"] for item in preview["targets"]}
    assert targets == {str(partial), str(invalid)}
    assert not partial.exists() and not invalid.exists()
    assert current.is_file() and healthy.is_dir()
    assert result["requires_restart"] is True


def test_startup_maintenance_removes_only_expired_orphans_and_assistant_partials(
    tmp_path: Path,
) -> None:
    var_dir = tmp_path / "var"
    service = CacheMaintenanceService(var_dir)
    expired = service.paths.temp / "expired"
    active = service.paths.temp / "active"
    partial = service.paths.assistant_cache / ".tmp-response"
    development = var_dir / "development" / "cache" / "keep.bin"
    expired.mkdir()
    active.mkdir()
    partial.parent.mkdir(parents=True, exist_ok=True)
    partial.write_bytes(b"partial")
    development.parent.mkdir(parents=True, exist_ok=True)
    development.write_bytes(b"keep")
    old = time.time() - 25 * 60 * 60
    os.utime(expired, (old, old))

    result = service.startup_maintenance()

    assert not expired.exists()
    assert active.is_dir()
    assert not partial.exists()
    assert development.read_bytes() == b"keep"
    assert str(expired) in result["removed"]
