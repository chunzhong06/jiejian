# =============================================================================
# 本地运行数据维护
#
# 定位
#   ApplicationCore、CLI、API 与运行环境页共用的当前 VarDir 可删除数据边界。
#
# 职责
#   AI 辅助缓存｜历史运行日志｜临时运行文件｜损坏运行时修复｜启动期有界保留
#
# 边界
#   不管理 var/development，不触碰 data、凭据、当前会话日志或活跃运行目录。
# =============================================================================

from __future__ import annotations

import json
import os
import shutil
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
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
_LOG_MAX_AGE_SECONDS = 14 * 24 * 60 * 60
_LOG_KEEP_PER_CATEGORY = 20
_SESSION_MTIME_TOLERANCE_SECONDS = 2
_OPERATIONS = {
    "clear-assistant-cache",
    "clear-logs",
    "clear-temporary",
    "clear-all",
    "repair-runtime",
}


class LocalMaintenanceService:
    """只处理当前实例可安全删除的本地运行数据，并形成统一确认摘要。"""

    def __init__(
        self,
        var_dir: Path,
        *,
        active_runtime_paths: Callable[[], Iterable[Path]] | None = None,
        session_started_at: float | None = None,
    ) -> None:
        self.paths = RuntimePaths(var_dir).ensure_layout()
        self._active_runtime_paths = active_runtime_paths or (lambda: ())
        self._session_started_at = session_started_at or time.time()
        self._lock_path = self.paths.locks / "local-maintenance.lock"
        self._state_path = self.paths.runtime / "local-maintenance-state.json"

    def status(self) -> dict[str, object]:
        """统计三类可清理数据；日志分类统计不包含当前会话受保护文件。"""

        state = self._read_json(self._state_path) or {}
        assistant_bytes, assistant_files = self._measure(self.paths.assistant_cache)
        log_categories = {
            name: self._entry(root, self._manual_log_candidates(root))
            for name, root in self._log_roots().items()
        }
        log_paths = [
            path
            for root in self._log_roots().values()
            for path in self._manual_log_candidates(root)
        ]
        temporary_paths = self._temporary_candidates(include_recent=True)
        return {
            "schema_version": "1",
            "entries": {
                "assistant": {
                    "path": str(self.paths.assistant_cache),
                    "bytes": assistant_bytes,
                    "files": assistant_files,
                },
                "logs": {
                    **self._entry(self.paths.logs, log_paths),
                    "categories": log_categories,
                },
                "temporary": self._entry(self.paths.root, temporary_paths),
            },
            "last_successful_operation": state.get("last_successful_operation"),
            "protected": self._protected_summary(),
        }

    def operate(
        self,
        operation: str,
        *,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> dict[str, object]:
        """先预览后确认执行固定白名单操作；未知操作在进入文件系统前拒绝。"""

        if operation not in _OPERATIONS:
            raise JiejianError(ErrorCode.INPUT_INVALID, "不支持的本地维护操作")
        if not confirmed and not dry_run:
            raise JiejianError(ErrorCode.INPUT_INVALID, "本地维护写操作需要显式确认")
        with self._locked():
            candidates = self._operation_candidates(operation)
            preview = self._preview(operation, candidates)
            removed: list[str] = []
            if confirmed and not dry_run:
                for path, root in candidates:
                    self._remove_under(path, root)
                    removed.append(str(path))
                if operation in {"clear-assistant-cache", "clear-all"}:
                    self.paths.assistant_cache.mkdir(parents=True, exist_ok=True)
                self._record(operation, {"removed": removed})
            return {
                **preview,
                "dry_run": not (confirmed and not dry_run),
                "confirmed": confirmed,
                "removed": removed,
                "requires_restart": operation == "repair-runtime" and bool(removed),
                "status": self.status(),
            }

    def startup_maintenance(self) -> dict[str, object]:
        """启动后只回收过期孤儿、超出日志保留规则的文件和缓存 partial。"""

        with self._locked():
            candidates: list[tuple[Path, Path]] = []
            candidates.extend(
                (path, root)
                for root in (self.paths.temp, self.paths.test)
                for path in self._expired_top_level(root)
            )
            candidates.extend(
                (path, root)
                for root in self._log_roots().values()
                for path in self._retained_log_candidates(root)
            )
            candidates.extend(
                (path, self.paths.assistant_cache)
                for path in self._assistant_partial_candidates()
            )
            removed: list[str] = []
            for path, root in self._unique_candidates(candidates):
                self._remove_under(path, root)
                removed.append(str(path))
            self._record("startup-maintenance", {"removed": removed})
            return {
                "schema_version": "1",
                "operation": "startup-maintenance",
                "removed": removed,
                "protected": self._protected_summary(),
            }

    def _operation_candidates(self, operation: str) -> list[tuple[Path, Path]]:
        assistant = [
            (path, self.paths.assistant_cache)
            for path in self._children(self.paths.assistant_cache)
        ]
        logs = [
            (path, root)
            for root in self._log_roots().values()
            for path in self._manual_log_candidates(root)
        ]
        temporary = [
            (path, self._maintenance_root(path))
            for path in self._temporary_candidates(include_recent=True)
        ]
        if operation == "clear-assistant-cache":
            return assistant
        if operation == "clear-logs":
            return logs
        if operation == "clear-temporary":
            return temporary
        if operation == "clear-all":
            return self._unique_candidates([*assistant, *logs, *temporary])
        return [
            (path, self.paths.runtime)
            for path in self._damaged_runtime_candidates()
        ]

    def _temporary_candidates(self, *, include_recent: bool) -> list[Path]:
        candidates: list[Path] = []
        for root in (self.paths.temp, self.paths.test):
            for path in self._children(root):
                if self._path_has_active_lock(path):
                    continue
                if include_recent or self._older_than(path, _ORPHAN_MIN_AGE_SECONDS):
                    candidates.append(path)
        protected = self._protected_runtime_paths()
        for path in self.paths.runtime.rglob("*"):
            if not self._temporary_runtime_name(path.name):
                continue
            if any(path.resolve().is_relative_to(item) for item in protected):
                continue
            candidates.append(path)
        for root in (self.paths.official_sample_runtime, self.paths.identity_preparations):
            for path in self._children(root):
                if path.resolve() in protected or self._path_has_active_lock(path):
                    continue
                if include_recent or self._older_than(path, _ORPHAN_MIN_AGE_SECONDS):
                    candidates.append(path)
        return sorted(set(candidates), key=lambda path: (len(path.parts), str(path)), reverse=True)

    @staticmethod
    def _temporary_runtime_name(name: str) -> bool:
        return (
            name.endswith((".partial", ".tmp"))
            or name.startswith((".tmp-", "tmp-"))
        )

    def _protected_runtime_paths(self) -> set[Path]:
        protected = {self.paths.locks.resolve()}
        if self._worker_is_active():
            protected.add(self.paths.worker_runtime.resolve())
        protected.update(path.resolve() for path in self._active_runtime_paths())
        return protected

    def _worker_is_active(self) -> bool:
        """以内核锁判断当前 Worker，而不是相信 PID 或诊断文件。"""

        return any(
            not lock_is_available(path)
            for path in self.paths.worker_runtime.glob("*.lock")
            if path.is_file()
        )

    def _damaged_runtime_candidates(self) -> list[Path]:
        protected = self._protected_runtime_paths()
        return sorted(
            (
                path
                for path in self.paths.runtime.rglob("*")
                if self._runtime_path_is_damaged(path)
                and not any(path.resolve().is_relative_to(item) for item in protected)
            ),
            key=lambda path: (len(path.parts), str(path)),
            reverse=True,
        )

    @staticmethod
    def _runtime_path_is_damaged(path: Path) -> bool:
        return path.name.endswith(".partial") or (
            path.is_dir() and (path / ".invalid").is_file()
        )

    def _log_roots(self) -> dict[str, Path]:
        return {
            "startup": self.paths.startup_logs,
            "app": self.paths.app_logs,
            "workers": self.paths.worker_logs,
            "runner": self.paths.runner_logs,
            "recording": self.paths.recording_logs,
            "identity-preparations": self.paths.identity_preparation_logs,
            "official-samples": self.paths.official_sample_logs,
        }

    def _manual_log_candidates(self, root: Path) -> list[Path]:
        return [
            path
            for path in self._log_files(root)
            if not self._is_current_session_log(path)
        ]

    def _retained_log_candidates(self, root: Path) -> list[Path]:
        cutoff = time.time() - _LOG_MAX_AGE_SECONDS
        return [
            path
            for index, path in enumerate(self._log_files(root))
            if not self._is_current_session_log(path)
            and (self._mtime(path) < cutoff or index >= _LOG_KEEP_PER_CATEGORY)
        ]

    def _is_current_session_log(self, path: Path) -> bool:
        """保护当前进程固定日志，并容忍 Windows 文件时间与 Python 时钟的微小偏差。"""

        if path.resolve() == (self.paths.app_logs / "jiejian.log").resolve():
            return True
        return self._mtime(path) >= (
            self._session_started_at - _SESSION_MTIME_TOLERANCE_SECONDS
        )

    @staticmethod
    def _log_files(root: Path) -> list[Path]:
        return sorted(
            (path for path in root.rglob("*") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        ) if root.is_dir() else []

    def _assistant_partial_candidates(self) -> list[Path]:
        return sorted(
            (
                path
                for path in self.paths.assistant_cache.rglob("*")
                if self._temporary_runtime_name(path.name)
            ),
            key=lambda path: (len(path.parts), str(path)),
            reverse=True,
        ) if self.paths.assistant_cache.is_dir() else []

    def _expired_top_level(self, root: Path) -> list[Path]:
        return [
            path
            for path in self._children(root)
            if self._older_than(path, _ORPHAN_MIN_AGE_SECONDS)
            and not self._path_has_active_lock(path)
        ]

    @staticmethod
    def _path_has_active_lock(path: Path) -> bool:
        lock = path / ".active.lock" if path.is_dir() else None
        return bool(lock and lock.exists() and not lock_is_available(lock))

    @staticmethod
    def _children(root: Path) -> list[Path]:
        return list(root.iterdir()) if root.is_dir() else []

    @staticmethod
    def _mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return float("inf")

    def _older_than(self, path: Path, seconds: float) -> bool:
        return self._mtime(path) < time.time() - seconds

    def _maintenance_root(self, path: Path) -> Path:
        resolved = path.resolve()
        for root in (
            self.paths.temp,
            self.paths.test,
            self.paths.runtime,
        ):
            if resolved.is_relative_to(root.resolve()):
                return root
        raise JiejianError(ErrorCode.LOCAL_MAINTENANCE_FAILED, "临时文件路径越界")

    def _protected_summary(self) -> dict[str, object]:
        return {
            "data": str(self.paths.data),
            "applications": True,
            "permissions": True,
            "database": True,
            "evidence": True,
            "reports": True,
            "credentials": True,
            "active_runtime": True,
            "current_session_logs": True,
            "development_root_included": False,
        }

    def _entry(self, root: Path, paths: list[Path]) -> dict[str, object]:
        return {
            "path": str(root),
            "bytes": sum(self._measure_path(path) for path in paths),
            "files": sum(self._measure_path_files(path) for path in paths),
        }

    def _preview(
        self,
        operation: str,
        candidates: list[tuple[Path, Path]],
    ) -> dict[str, object]:
        unique = self._unique_candidates(candidates)
        measured = [(path, self._measure_path(path)) for path, _ in unique]
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
    def _unique_candidates(
        candidates: list[tuple[Path, Path]],
    ) -> list[tuple[Path, Path]]:
        result: list[tuple[Path, Path]] = []
        seen: set[Path] = set()
        for path, root in sorted(candidates, key=lambda item: len(item[0].parts)):
            resolved = path.resolve()
            if resolved in seen or any(resolved.is_relative_to(item) for item in seen):
                continue
            seen.add(resolved)
            result.append((path, root))
        return result

    @staticmethod
    def _measure(root: Path) -> tuple[int, int]:
        if root.is_file():
            try:
                return root.stat().st_size, 1
            except OSError:
                return 0, 0
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
        return cls._measure(path)[0]

    @classmethod
    def _measure_path_files(cls, path: Path) -> int:
        return cls._measure(path)[1]

    def _remove_under(self, path: Path, root: Path) -> None:
        resolved = path.resolve()
        root = root.resolve()
        if resolved == root or not resolved.is_relative_to(root):
            raise JiejianError(ErrorCode.LOCAL_MAINTENANCE_FAILED, "维护路径越界")
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
        temporary = self._state_path.with_name(f".{self._state_path.name}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, self._state_path)

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self._lock_path.touch(exist_ok=True)
        stream = self._lock_path.open("r+b")
        locked = False
        try:
            locked = try_lock_stream(stream)
            if not locked:
                raise JiejianError(
                    ErrorCode.LOCAL_MAINTENANCE_FAILED,
                    "已有本地运行数据维护操作正在进行",
                )
            yield
        finally:
            try:
                if locked:
                    unlock_stream(stream)
            finally:
                stream.close()


__all__ = ["LocalMaintenanceService"]
