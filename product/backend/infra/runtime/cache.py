# =============================================================================
# 产品实例缓存与运行时维护
#
# 定位
#   ApplicationCore、CLI、API 与运行环境页共用的当前 VarDir 维护边界。
#
# 职责
#   Assistant cache 状态与清空｜当前实例损坏运行时修复｜有界孤儿与日志清理
#
# 边界
#   不管理 var/development，不触碰 data、凭据或健康运行时，也不提供开发工具 prune。
# =============================================================================

from __future__ import annotations

import json
import os
import shutil
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.runtime.process.lock import (
    lock_is_available,
    try_lock_stream,
    unlock_stream,
)

_ORPHAN_MIN_AGE_SECONDS = 24 * 60 * 60
_STARTUP_LOG_MAX_AGE_SECONDS = 14 * 24 * 60 * 60
_WORKER_LOG_MAX_AGE_SECONDS = 30 * 24 * 60 * 60


class CacheMaintenanceService:
    """只维护当前产品实例可重建内容，并输出统一确认摘要。"""

    def __init__(self, var_dir: Path) -> None:
        self.paths = RuntimePaths(var_dir).ensure_layout()
        self._lock_path = self.paths.locks / "cache-maintenance.lock"
        self._state_path = self.paths.runtime / "cache-maintenance-state.json"
        self._runtime_state_path = self.paths.runtime / "runtime-state.json"

    def status(self) -> dict[str, object]:
        """只报告当前实例的 Assistant cache，不扫描共享开发资产。"""

        state = self._read_json(self._state_path) or {}
        size, files = self._measure(self.paths.assistant_cache)
        return {
            "schema_version": "1",
            "var_dir": str(self.paths.root),
            "entries": {
                "assistant": {
                    "path": str(self.paths.assistant_cache),
                    "bytes": size,
                    "files": files,
                    "budget": None,
                    "over_budget": False,
                    "last_successful_usage": state.get("last_successful_operation"),
                    "referenced": False,
                }
            },
            "last_successful_operation": state.get("last_successful_operation"),
            "protected": self._protected_summary(),
        }

    def clean(
        self,
        *,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> dict[str, object]:
        """预览或清空 Assistant cache；开发缓存和产品事实始终不在范围内。"""

        with self._locked():
            target = self.paths.assistant_cache
            preview = self._preview("clean", [target])
            if not confirmed and not dry_run:
                raise JiejianError(ErrorCode.INPUT_INVALID, "清空缓存需要显式确认")
            removed: list[str] = []
            if confirmed and not dry_run:
                for child in tuple(target.iterdir()) if target.is_dir() else ():
                    self._remove_under(child, self.paths.assistant_cache)
                target.mkdir(parents=True, exist_ok=True)
                removed.append(str(target))
                self._record("clean", {"removed": removed})
            return {
                **preview,
                "dry_run": not (confirmed and not dry_run),
                "confirmed": confirmed,
                "removed": removed,
                "status": self.status(),
            }

    def repair_runtime(
        self,
        *,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> dict[str, object]:
        """只移除当前 VarDir 内有损坏标记且未被当前状态引用的运行时。"""

        with self._locked():
            candidates = self._damaged_runtime_candidates()
            preview = self._preview("runtime_repair", candidates)
            if not confirmed and not dry_run:
                raise JiejianError(ErrorCode.INPUT_INVALID, "修复运行时需要显式确认")
            removed: list[str] = []
            if confirmed and not dry_run:
                for path in candidates:
                    self._remove_damaged_runtime(path)
                    removed.append(str(path))
                self._record("runtime_repair", {"removed": removed})
            return {
                **preview,
                "dry_run": not (confirmed and not dry_run),
                "confirmed": confirmed,
                "removed": removed,
                "requires_restart": bool(removed),
                "status": self.status(),
            }

    def startup_maintenance(self) -> dict[str, object]:
        """启动时只清理过期孤儿、日志和 Assistant cache 的明确 partial。"""

        with self._locked():
            candidates = [
                *self._expired_orphan_candidates(),
                *self._expired_log_candidates(),
                *self._assistant_partial_candidates(),
            ]
            removed: list[str] = []
            for path in candidates:
                if path.resolve().is_relative_to(self.paths.assistant_cache.resolve()):
                    self._remove_under(path, self.paths.assistant_cache)
                else:
                    self._remove_startup_path(path)
                removed.append(str(path))
            self._record("startup_maintenance", {"removed": removed})
            return {
                "schema_version": "1",
                "operation": "startup_maintenance",
                "removed": removed,
                "protected": self._protected_summary(),
            }

    def _protected_summary(self) -> dict[str, object]:
        return {
            "data": str(self.paths.data),
            "data_unchanged": True,
            "current_runtime_unchanged_by_cache": True,
            "includes_database": False,
            "includes_evidence_or_reports": False,
            "includes_credentials": False,
            "development_root_included": False,
        }

    def _damaged_runtime_candidates(self) -> list[Path]:
        state = self._read_json(self._runtime_state_path) or {}
        current_values = state.get("current_paths", ())
        referenced = (
            {
                str(Path(value).resolve())
                for value in current_values
                if isinstance(value, str)
            }
            if isinstance(current_values, (list, tuple))
            else set()
        )
        candidates = [
            path
            for path in self.paths.runtime.rglob("*")
            if self._runtime_path_is_damaged(path)
            and str(path.resolve()) not in referenced
        ]
        return sorted(candidates, key=str, reverse=True)

    @staticmethod
    def _runtime_path_is_damaged(path: Path) -> bool:
        return path.name.endswith(".partial") or (
            path.is_dir() and (path / ".invalid").is_file()
        )

    def _expired_orphan_candidates(self) -> list[Path]:
        cutoff = time.time() - _ORPHAN_MIN_AGE_SECONDS
        candidates: list[Path] = []
        for root in (self.paths.temp, self.paths.test):
            for path in tuple(root.iterdir()) if root.is_dir() else ():
                try:
                    if path.stat().st_mtime >= cutoff:
                        continue
                except OSError:
                    continue
                active_lock = path / ".active.lock" if path.is_dir() else None
                if (
                    active_lock is not None
                    and active_lock.exists()
                    and not lock_is_available(active_lock)
                ):
                    continue
                candidates.append(path)
        return sorted(candidates, key=str)

    def _expired_log_candidates(self) -> list[Path]:
        now = time.time()
        return [
            *self._retained_logs(
                self.paths.startup_logs,
                keep=20,
                cutoff=now - _STARTUP_LOG_MAX_AGE_SECONDS,
            ),
            *self._retained_logs(
                self.paths.worker_logs,
                keep=None,
                cutoff=now - _WORKER_LOG_MAX_AGE_SECONDS,
            ),
        ]

    def _assistant_partial_candidates(self) -> list[Path]:
        root = self.paths.assistant_cache
        if not root.is_dir():
            return []
        return sorted(
            (
                path
                for path in root.rglob("*")
                if path.name.endswith(".partial") or path.name.startswith(".tmp-")
            ),
            key=str,
            reverse=True,
        )

    @staticmethod
    def _retained_logs(root: Path, *, keep: int | None, cutoff: float) -> list[Path]:
        files = sorted(
            (path for path in root.glob("*") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        return [
            path
            for index, path in enumerate(files)
            if path.stat().st_mtime < cutoff or (keep is not None and index >= keep)
        ]

    def _preview(self, operation: str, targets: list[Path]) -> dict[str, object]:
        measured = [(path, self._measure_path(path)) for path in targets]
        return {
            "schema_version": "1",
            "operation": operation,
            "targets": [
                {"path": str(path), "estimated_bytes": size}
                for path, size in measured
            ],
            "estimated_bytes": sum(size for _, size in measured),
            "protected": self._protected_summary(),
        }

    @staticmethod
    def _measure(root: Path) -> tuple[int, int]:
        size = 0
        files = 0
        if root.is_dir():
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                try:
                    size += path.stat().st_size
                    files += 1
                except OSError:
                    continue
        return size, files

    @classmethod
    def _measure_path(cls, path: Path) -> int:
        if path.is_file():
            try:
                return path.stat().st_size
            except OSError:
                return 0
        return cls._measure(path)[0] if path.is_dir() else 0

    def _remove_damaged_runtime(self, path: Path) -> None:
        if not self._runtime_path_is_damaged(path):
            raise JiejianError(ErrorCode.RUNTIME_REPAIR_FAILED, "运行时没有损坏标记")
        self._remove_under(path, self.paths.runtime)

    def _remove_startup_path(self, path: Path) -> None:
        resolved = path.resolve()
        allowed = (self.paths.temp, self.paths.test, self.paths.logs)
        if not any(resolved.is_relative_to(root.resolve()) for root in allowed):
            raise JiejianError(ErrorCode.CACHE_MAINTENANCE_FAILED, "启动清理路径越界")
        self._unlink(resolved)

    def _remove_under(self, path: Path, root: Path) -> None:
        resolved = path.resolve()
        root = root.resolve()
        if resolved == root or not resolved.is_relative_to(root):
            raise JiejianError(ErrorCode.CACHE_MAINTENANCE_FAILED, "维护路径越界")
        self._unlink(resolved)

    @staticmethod
    def _unlink(path: Path) -> None:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()

    @staticmethod
    def _read_json(path: Path) -> dict[str, object] | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    def _record(self, operation: str, details: Mapping[str, object]) -> None:
        payload = {
            "schema_version": "1",
            "last_successful_operation": {
                "operation": operation,
                "completed_at": int(time.time()),
                **details,
            },
        }
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._state_path.with_name(f".{self._state_path.name}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, self._state_path)

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path.touch(exist_ok=True)
        stream = self._lock_path.open("r+b")
        locked = False
        try:
            locked = try_lock_stream(stream)
            if not locked:
                raise JiejianError(
                    ErrorCode.CACHE_MAINTENANCE_FAILED,
                    "已有缓存或运行时维护操作正在进行",
                )
            yield
        finally:
            try:
                if locked:
                    unlock_stream(stream)
            finally:
                stream.close()
