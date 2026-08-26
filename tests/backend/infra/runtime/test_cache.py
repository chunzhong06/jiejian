# 验证进程运行时中的缓存管理。

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from product.backend.infra.runtime.cache import CacheMaintenanceService


def _service(var_dir: Path) -> CacheMaintenanceService:
    return CacheMaintenanceService(
        var_dir,
        environment={},
        environment_verifier=lambda environment: {"ok": True},
    )


def test_cache_clean_never_touches_data_or_runtime(tmp_path: Path) -> None:
    service = _service(tmp_path / "var")
    data = service.paths.data / "proof.txt"
    runtime = service.paths.runtime / "python" / "release" / "current" / "python.exe"
    cached = service.paths.uv_cache / "archive.bin"
    vite = service.paths.vite_cache / "deps" / "manifest.json"
    for path in (data, runtime, cached, vite):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"proof")
    cached_size = cached.stat().st_size

    preview = service.clean(dry_run=True)
    result = service.clean(confirmed=True, dry_run=False)

    assert preview["estimated_bytes"] >= cached_size
    assert data.read_bytes() == b"proof"
    assert runtime.read_bytes() == b"proof"
    assert not cached.exists()
    assert not vite.exists()
    assert result["protected"]["data_unchanged"] is True
    assert result["protected"]["current_runtime_unchanged_by_cache"] is True


def test_runtime_repair_removes_incomplete_frontend_workspace(tmp_path: Path) -> None:
    service = _service(tmp_path / "var")
    workspace = service.paths.frontend_workspace
    (workspace / "node_modules").mkdir(parents=True)
    (workspace / "package.json").write_text("{}", encoding="utf-8")

    preview = service.repair_runtime(dry_run=True)
    result = service.repair_runtime(confirmed=True, dry_run=False)

    assert {target["path"] for target in preview["targets"]} == {str(workspace)}
    assert str(workspace) in result["removed"]
    assert not workspace.exists()
    assert result["requires_restart"] is True


def test_runtime_prune_keeps_current_and_previous_versions(tmp_path: Path) -> None:
    service = _service(tmp_path / "var")
    release = service.paths.runtime / "python" / "release"
    current = release / "current"
    previous = release / "previous"
    retired = release / "retired"
    for path in (current, previous, retired):
        path.mkdir(parents=True)
        (path / "python.exe").write_bytes(path.name.encode("ascii"))
    state = {
        "schema_version": "1",
        "current_paths": [str(current)],
        "previous_paths": [str(previous)],
    }
    state_path = service.paths.runtime / "runtime-state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    preview = service.prune(dry_run=True)
    targets = {target["path"] for target in preview["targets"]}
    result = service.prune(dry_run=False)

    assert str(retired) in targets
    assert str(current) not in targets
    assert str(previous) not in targets
    assert current.is_dir() and previous.is_dir()
    assert not retired.exists()
    assert str(retired) in result["removed"]


def test_runtime_prune_refuses_to_guess_without_reference_state(tmp_path: Path) -> None:
    service = _service(tmp_path / "var")
    runtime = service.paths.runtime / "python" / "release" / "unknown"
    runtime.mkdir(parents=True)
    (runtime / "python.exe").write_bytes(b"unknown")

    result = service.prune(dry_run=False)

    assert runtime.is_dir()
    assert str(runtime) not in result["removed"]


def test_startup_maintenance_only_removes_expired_temp_and_partial(tmp_path: Path) -> None:
    service = _service(tmp_path / "var")
    expired = service.paths.temp / "expired"
    active = service.paths.temp / "active"
    partial = service.paths.downloads / ".tmp-download.zip"
    expired.mkdir()
    active.mkdir()
    partial.write_bytes(b"partial")
    old = time.time() - 25 * 60 * 60
    os.utime(expired, (old, old))

    result = service.startup_maintenance()

    assert not expired.exists()
    assert active.is_dir()
    assert not partial.exists()
    assert service.paths.data.is_dir()
    assert str(expired) in result["removed"]


def test_startup_maintenance_never_scans_large_cache_roots(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = _service(tmp_path / "var")
    marker = service.paths.pnpm_store / "v11" / "files" / "package.bin"
    data = service.paths.data / "product.db"
    marker.parent.mkdir(parents=True)
    marker.write_bytes(b"cache")
    data.write_bytes(b"product")
    calls: dict[Path, int] = {}
    original = CacheMaintenanceService._measure

    def counted(root: Path, *, collect_partials: bool):
        resolved = root.resolve()
        calls[resolved] = calls.get(resolved, 0) + 1
        return original(root, collect_partials=collect_partials)

    monkeypatch.setattr(
        CacheMaintenanceService,
        "_measure",
        staticmethod(counted),
    )

    result = service.startup_maintenance()

    assert calls == {}
    assert result["cache_budget_maintenance"] == "on_demand"
    assert marker.read_bytes() == b"cache"
    assert data.read_bytes() == b"product"
