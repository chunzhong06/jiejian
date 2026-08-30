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
import hashlib
import os
import secrets
import shutil
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
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
_PLAN_TTL_SECONDS = 5 * 60
_OPERATIONS = {
    "clear-assistant-cache",
    "clear-logs",
    "clear-temporary",
    "clear-all",
    "repair-runtime",
}


@dataclass(frozen=True)
class MaintenanceCandidate:
    """冻结一次预览中的候选身份；真实路径只留在服务端当前实例。"""

    item_id: str
    label: str
    relative_path: str
    path: Path
    root: Path
    estimated_bytes: int
    fingerprint: str


@dataclass(frozen=True)
class MaintenancePlan:
    """把普通维护预览冻结为一次短期、单实例、一次性确认计划。"""

    plan_id: str
    scope: str
    generated_at_us: int
    expires_at_us: int
    candidates: tuple[MaintenanceCandidate, ...]


class LocalMaintenanceService:
    """只处理当前实例可安全删除的本地运行数据，并形成统一确认摘要。"""

    def __init__(
        self,
        var_dir: Path,
        *,
        active_runtime_paths: Callable[[], Iterable[Path]] | None = None,
        session_started_at: float | None = None,
        plan_ttl_seconds: int = _PLAN_TTL_SECONDS,
    ) -> None:
        self.paths = RuntimePaths(var_dir).ensure_layout()
        self._active_runtime_paths = active_runtime_paths or (lambda: ())
        self._session_started_at = session_started_at or time.time()
        self._plan_ttl_us = plan_ttl_seconds * 1_000_000
        self._plans: dict[str, MaintenancePlan] = {}
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
        plan_id: str | None = None,
    ) -> dict[str, object]:
        """兼容 CLI 的命令形态；API/GUI 使用 preview 后按 plan_id 确认。"""

        if not confirmed and not dry_run:
            raise JiejianError(ErrorCode.INPUT_INVALID, "本地维护写操作需要显式确认")
        if confirmed and not dry_run:
            if plan_id is None:
                plan_id = str(self.preview(operation)["plan_id"])
            return self.execute(plan_id, expected_scope=operation)
        return self.preview(operation)

    def preview(self, operation: str) -> dict[str, object]:
        """扫描一次白名单候选并冻结短期计划，不在确认阶段重新计算。"""

        self._validate_operation(operation)
        with self._locked():
            now_us = self._now_us()
            self._prune_plans(now_us)
            candidates = tuple(
                self._snapshot_candidate(operation, path, root)
                for path, root in self._operation_candidates(operation)
                if self._path_within_root(path, root)
            )
            plan = MaintenancePlan(
                plan_id=secrets.token_urlsafe(24),
                scope=operation,
                generated_at_us=now_us,
                expires_at_us=now_us + self._plan_ttl_us,
                candidates=candidates,
            )
            self._plans[plan.plan_id] = plan
            return self._plan_payload(plan)

    def execute(
        self,
        plan_id: str,
        *,
        expected_scope: str | None = None,
    ) -> dict[str, object]:
        """只执行被冻结计划中的项目，并为每项保留可解释的安全结果。"""

        with self._locked():
            now_us = self._now_us()
            plan = self._plans.pop(plan_id, None)
            if plan is None or plan.expires_at_us < now_us:
                raise JiejianError(
                    ErrorCode.LOCAL_MAINTENANCE_FAILED,
                    "维护计划不存在或已过期，请重新预览",
                )
            if expected_scope is not None and plan.scope != expected_scope:
                raise JiejianError(
                    ErrorCode.INPUT_INVALID,
                    "维护计划与请求操作不一致",
                )
            results = [self._execute_candidate(item) for item in plan.candidates]
            deleted = [
                str(item["relative_path"])
                for item in results
                if item["status"] == "DELETED"
            ]
            counts = {
                status: sum(item["status"] == status for item in results)
                for status in (
                    "DELETED",
                    "ALREADY_MISSING",
                    "SKIPPED_IN_USE",
                    "SKIPPED_CHANGED",
                    "FAILED",
                )
            }
            if plan.scope in {"clear-assistant-cache", "clear-all"}:
                self.paths.assistant_cache.mkdir(parents=True, exist_ok=True)
            recorded = True
            try:
                self._record(plan.scope, {"plan_id": plan.plan_id, "results": results})
            except OSError:
                recorded = False
            return {
                **self._plan_payload(plan),
                "dry_run": False,
                "confirmed": True,
                "removed": deleted,
                "results": results,
                "counts": counts,
                "recorded": recorded,
                "requires_restart": (
                    plan.scope == "repair-runtime" and counts["DELETED"] > 0
                ),
                "status": self.status(),
            }

    def startup_maintenance(self) -> dict[str, object]:
        """启动后只回收产品临时目录、产品日志和助手缓存 partial。"""

        with self._locked():
            candidates: list[tuple[Path, Path]] = []
            candidates.extend(
                (path, root)
                for root in (self.paths.temp,)
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
        for root in (self.paths.temp,):
            for path in self._children(root):
                if self._path_is_in_use(path):
                    continue
                if include_recent or self._older_than(path, _ORPHAN_MIN_AGE_SECONDS):
                    candidates.append(path)
        protected = self._protected_runtime_paths()
        for path in self.paths.runtime.rglob("*"):
            if not self._temporary_runtime_name(path.name):
                continue
            if self._overlaps_any(path, protected):
                continue
            candidates.append(path)
        return sorted(set(candidates), key=lambda path: (len(path.parts), str(path)), reverse=True)

    @staticmethod
    def _temporary_runtime_name(name: str) -> bool:
        return (
            name.endswith((".partial", ".tmp"))
            or name.startswith((".tmp-", "tmp-"))
        )

    def _protected_runtime_paths(self) -> set[Path]:
        protected = {
            self.paths.locks.resolve(),
            self.paths.process_gates.resolve(),
            self.paths.official_sample_runtime.resolve(),
        }
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
            and not self._path_is_in_use(path)
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
            "process_gates": True,
            "current_session_logs": True,
            "development_root_included": False,
            "test_root_included": False,
            "official_sample_runtime_included": False,
        }

    def _entry(self, root: Path, paths: list[Path]) -> dict[str, object]:
        return {
            "path": str(root),
            "bytes": sum(self._measure_path(path) for path in paths),
            "files": sum(self._measure_path_files(path) for path in paths),
        }

    def _plan_payload(self, plan: MaintenancePlan) -> dict[str, object]:
        return {
            "schema_version": "1",
            "plan_id": plan.plan_id,
            "scope": plan.scope,
            "operation": plan.scope,
            "generated_at_us": plan.generated_at_us,
            "expires_at_us": plan.expires_at_us,
            "targets": [
                {
                    "item_id": item.item_id,
                    "label": item.label,
                    "relative_path": item.relative_path,
                    "estimated_bytes": item.estimated_bytes,
                }
                for item in plan.candidates
            ],
            "estimated_bytes": sum(
                item.estimated_bytes for item in plan.candidates
            ),
            "dry_run": True,
            "confirmed": False,
            "removed": [],
            "results": [],
            "counts": {
                "DELETED": 0,
                "ALREADY_MISSING": 0,
                "SKIPPED_IN_USE": 0,
                "SKIPPED_CHANGED": 0,
                "FAILED": 0,
            },
            "protected": self._protected_summary(),
            "status": self.status(),
        }

    def _snapshot_candidate(
        self,
        operation: str,
        path: Path,
        root: Path,
    ) -> MaintenanceCandidate:
        relative_path = path.resolve().relative_to(self.paths.root.resolve()).as_posix()
        item_id = hashlib.sha256(
            f"{operation}\0{relative_path}".encode("utf-8")
        ).hexdigest()[:24]
        return MaintenanceCandidate(
            item_id=item_id,
            label=self._candidate_label(path, root),
            relative_path=relative_path,
            path=path,
            root=root,
            estimated_bytes=self._measure_path(path),
            fingerprint=self._path_fingerprint(path),
        )

    def _execute_candidate(self, item: MaintenanceCandidate) -> dict[str, object]:
        result: dict[str, object] = {
            "item_id": item.item_id,
            "label": item.label,
            "relative_path": item.relative_path,
        }
        if not item.path.exists():
            return {**result, "status": "ALREADY_MISSING", "reason": "候选已不存在"}
        if self._path_is_in_use(item.path):
            return {
                **result,
                "status": "SKIPPED_IN_USE",
                "reason": "仍被当前运行环境使用，已跳过",
            }
        if not self._candidate_within_root(item):
            return {
                **result,
                "status": "SKIPPED_CHANGED",
                "reason": "候选安全边界已变化，已跳过",
            }
        if self._path_fingerprint(item.path) != item.fingerprint:
            return {
                **result,
                "status": "SKIPPED_CHANGED",
                "reason": "候选内容已变化，已跳过",
            }
        try:
            self._remove_under(item.path, item.root)
        except PermissionError:
            return {
                **result,
                "status": "SKIPPED_IN_USE",
                "reason": "仍被当前运行环境使用，已跳过",
            }
        except OSError as exc:
            if getattr(exc, "winerror", None) in {32, 33}:
                return {
                    **result,
                    "status": "SKIPPED_IN_USE",
                    "reason": "仍被当前运行环境使用，已跳过",
                }
            return {**result, "status": "FAILED", "reason": "清理失败，其他项目已继续处理"}
        return {**result, "status": "DELETED", "reason": "已安全清理"}

    def _candidate_within_root(self, item: MaintenanceCandidate) -> bool:
        return self._path_within_root(item.path, item.root)

    @staticmethod
    def _path_within_root(path: Path, root: Path) -> bool:
        try:
            resolved = path.resolve()
            resolved_root = root.resolve()
        except OSError:
            return False
        return resolved != resolved_root and resolved.is_relative_to(resolved_root)

    def _path_is_in_use(self, path: Path) -> bool:
        if self._path_has_active_lock(path):
            return True
        return self._overlaps_any(path, self._protected_runtime_paths())

    @staticmethod
    def _overlaps_any(path: Path, protected: Iterable[Path]) -> bool:
        resolved = path.resolve()
        return any(
            resolved.is_relative_to(item) or item.is_relative_to(resolved)
            for item in protected
        )

    def _candidate_label(self, path: Path, root: Path) -> str:
        if root.resolve() == self.paths.assistant_cache.resolve():
            category = "AI 辅助缓存"
        elif root.resolve().is_relative_to(self.paths.logs.resolve()):
            category = "历史运行日志"
        elif root.resolve() == self.paths.temp.resolve():
            category = "临时运行文件"
        else:
            category = "运行环境修复项"
        return f"{category}：{path.name}"

    @classmethod
    def _path_fingerprint(cls, path: Path) -> str:
        digest = hashlib.sha256()
        members = [path]
        if path.is_dir():
            members.extend(sorted(path.rglob("*"), key=lambda item: item.as_posix()))
        for member in members:
            relative = "." if member == path else member.relative_to(path).as_posix()
            try:
                stat = member.stat(follow_symlinks=False)
                value = (
                    relative,
                    stat.st_mode,
                    stat.st_size,
                    stat.st_mtime_ns,
                )
            except OSError:
                value = (relative, "unavailable")
            digest.update(repr(value).encode("utf-8"))
            digest.update(b"\0")
        return digest.hexdigest()

    @staticmethod
    def _now_us() -> int:
        return time.time_ns() // 1_000

    def _prune_plans(self, now_us: int) -> None:
        self._plans = {
            plan_id: plan
            for plan_id, plan in self._plans.items()
            if plan.expires_at_us >= now_us
        }

    @staticmethod
    def _validate_operation(operation: str) -> None:
        if operation not in _OPERATIONS:
            raise JiejianError(ErrorCode.INPUT_INVALID, "不支持的本地维护操作")

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


__all__ = ["LocalMaintenanceService", "MaintenanceCandidate", "MaintenancePlan"]
