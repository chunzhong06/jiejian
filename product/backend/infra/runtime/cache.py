# =============================================================================
# 运行时缓存维护
#
# 定位
#   ApplicationCore、CLI、API 与运行环境页共用的 VarDir 维护边界
#
# 职责
#   状态与 dry-run｜预算 prune｜缓存清空｜损坏运行时修复｜启动期孤儿清理
#
# 边界
#   只触碰 cache、明确过期的 temp/test、损坏运行时和受控日志；绝不触碰 data。
# =============================================================================

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.process.identity import require_python_environment
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.runtime.process.lock import lock_is_available, try_lock_stream, unlock_stream

_BUDGETS = {
    "uv": 2 * 1024**3,
    "pnpm_store": 3 * 1024**3,
    "npm": 512 * 1024**2,
    "vite": 512 * 1024**2,
}
_CACHE_ROOTS = ("uv", "pnpm-store", "npm", "vite", "downloads", "startup")
_ORPHAN_MIN_AGE_SECONDS = 24 * 60 * 60
_STARTUP_LOG_MAX_AGE_SECONDS = 14 * 24 * 60 * 60
_WORKER_LOG_MAX_AGE_SECONDS = 30 * 24 * 60 * 60


class CacheMaintenanceService:
    """在独立系统锁内维护可重建内容，并输出同一份可确认摘要。"""

    def __init__(
        self,
        var_dir: Path,
        *,
        environment: Mapping[str, str] | None = None,
        tool_runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
        environment_verifier: Callable[[Mapping[str, str]], object] = require_python_environment,
    ) -> None:
        self.paths = RuntimePaths(var_dir).ensure_layout()
        self._environment = dict(environment if environment is not None else os.environ)
        self._tool_runner = tool_runner
        self._environment_verifier = environment_verifier
        self._lock_path = self.paths.locks / "cache-maintenance.lock"
        self._state_path = self.paths.startup_cache / "cache-state.json"
        self._runtime_state_path = self.paths.runtime / "runtime-state.json"

    def status(self) -> dict[str, object]:
        """返回实际体积、预算和最近成功事实，不执行删除。"""

        return self._status_snapshot(include_partials=False)[0]

    def _status_snapshot(
        self,
        *,
        include_partials: bool,
    ) -> tuple[dict[str, object], list[Path]]:
        """一次遍历形成预算状态与可选 partial 候选，避免维护链重复扫描。"""

        state = self._read_json(self._state_path) or {}
        entries: dict[str, dict[str, object]] = {}
        partials: list[Path] = []
        roots = (
            ("uv", self.paths.uv_cache, _BUDGETS["uv"]),
            ("pnpm_store", self.paths.pnpm_store, _BUDGETS["pnpm_store"]),
            ("npm", self.paths.npm_cache, _BUDGETS["npm"]),
            ("vite", self.paths.vite_cache, _BUDGETS["vite"]),
            ("downloads", self.paths.downloads, None),
            ("startup", self.paths.startup_cache, None),
        )
        for name, root, budget in roots:
            size, files, found = self._measure(
                root,
                collect_partials=include_partials,
            )
            partials.extend(found)
            entries[name] = self._entry(root, budget, state, size=size, files=files)
        entries["retired_runtime"] = self._entry_paths(
            self._retired_runtime_candidates(),
            state,
        )
        status = {
            "schema_version": "1",
            "var_dir": str(self.paths.root),
            "entries": entries,
            "last_successful_operation": state.get("last_successful_operation"),
            "protected": self._protected_summary(),
        }
        selected: list[Path] = []
        for path in sorted(set(partials), key=lambda item: len(item.parts)):
            resolved = path.resolve()
            if any(resolved.is_relative_to(parent.resolve()) for parent in selected):
                continue
            selected.append(path)
        return status, sorted(selected, key=str, reverse=True)

    def prune(self, *, dry_run: bool = True) -> dict[str, object]:
        """仅在超预算时调用对应工具官方 prune，并清理确定孤立的 partial。"""

        with self._locked():
            return self._prune_locked(dry_run=dry_run)

    def clean(
        self,
        *,
        confirmed: bool = False,
        dry_run: bool = True,
    ) -> dict[str, object]:
        """清空全部可重建缓存；执行前必须显式确认，运行时与 data 始终保留。"""

        with self._locked():
            targets = [self.paths.cache / name for name in _CACHE_ROOTS]
            preview = self._preview("clean", targets)
            if not confirmed and not dry_run:
                raise JiejianError(ErrorCode.INPUT_INVALID, "清空缓存需要显式确认")
            removed: list[str] = []
            if confirmed and not dry_run:
                for target in targets:
                    for child in tuple(target.iterdir()) if target.is_dir() else ():
                        self._remove_cache_path(child)
                    removed.append(str(target))
                self.paths.ensure_layout()
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
        """只移除可证明损坏且未被当前版本引用的运行时，随后要求启动器重建。"""

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
        """只做有界孤儿与日志清理；大型缓存预算留给显式状态和 prune。"""

        with self._locked():
            orphaned = self._expired_orphan_candidates()
            logs = self._expired_log_candidates()
            partials = self._startup_partial_candidates()
            removed: list[str] = []
            for path in (*orphaned, *logs, *partials):
                if path in partials:
                    self._remove_cache_path(path)
                else:
                    self._remove_startup_path(path)
                removed.append(str(path))
            self._record(
                "startup_maintenance",
                {"removed": removed, "prune_tools": []},
            )
            return {
                "schema_version": "1",
                "operation": "startup_maintenance",
                "removed": removed,
                "cache_budget_maintenance": "on_demand",
                "protected": self._protected_summary(),
            }

    def _prune_locked(self, *, dry_run: bool) -> dict[str, object]:
        before, partials = self._status_snapshot(include_partials=True)
        entries = before["entries"]
        assert isinstance(entries, dict)
        over_budget = tuple(
            name
            for name in ("uv", "pnpm_store", "npm", "vite")
            if bool(entries[name]["over_budget"])
        )
        retired_runtime = self._retired_runtime_candidates()
        targets = [
            *partials,
            *retired_runtime,
            *(self._cache_path(name) for name in over_budget),
        ]
        known_sizes = {
            str(self._cache_path(name).resolve()): int(entries[name]["bytes"])
            for name in over_budget
        }
        preview = self._preview("prune", targets, known_sizes=known_sizes)
        removal_measurements = {
            path: self._measure_path_details(path)
            for path in (*partials, *retired_runtime)
        }
        removed: list[str] = []
        tool_results: list[dict[str, object]] = []
        if not dry_run:
            for path in partials:
                self._remove_cache_path(path)
                removed.append(str(path))
            for path in retired_runtime:
                self._remove_retired_runtime(path)
                removed.append(str(path))
            for name in over_budget:
                if name == "vite":
                    self._remove_cache_path(self.paths.vite_cache)
                    self.paths.vite_cache.mkdir(parents=True, exist_ok=True)
                    removed.append(str(self.paths.vite_cache))
                else:
                    tool_results.append(self._official_prune(name))
            self._revalidate_after_prune(over_budget)
            self._record(
                "prune",
                {"removed": removed, "tool_results": tool_results},
            )
        status = (
            self.status()
            if over_budget and not dry_run
            else self._status_after_known_removals(before, removed, removal_measurements)
        )
        return {
            **preview,
            "dry_run": dry_run,
            "over_budget": over_budget,
            "removed": removed,
            "tool_results": tool_results,
            "status": status,
        }

    def _official_prune(self, name: str) -> dict[str, object]:
        executable_name, arguments = {
            "uv": (
                "JIEJIAN_UV_EXECUTABLE",
                ("cache", "prune", "--cache-dir", str(self.paths.uv_cache)),
            ),
            "pnpm_store": (
                "JIEJIAN_PNPM_EXECUTABLE",
                ("--store-dir", str(self.paths.pnpm_store), "store", "prune"),
            ),
            "npm": (
                "JIEJIAN_NPM_EXECUTABLE",
                ("cache", "clean", "--force", "--cache", str(self.paths.npm_cache)),
            ),
        }[name]
        executable = self._environment.get(executable_name)
        if not executable or not Path(executable).is_file():
            return {
                "cache": name,
                "status": "tool_unavailable",
                "tool": executable_name,
            }
        command = [str(Path(executable).resolve()), *arguments]
        try:
            completed = self._tool_runner(
                command,
                cwd=str(self.paths.temp),
                env=self._tool_environment(Path(executable)),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120,
                check=False,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise JiejianError(
                ErrorCode.CACHE_MAINTENANCE_FAILED,
                "缓存官方维护命令无法完成",
                details={"cache": name, "reason": type(exc).__name__},
            ) from None
        if completed.returncode != 0:
            raise JiejianError(
                ErrorCode.CACHE_MAINTENANCE_FAILED,
                "缓存官方维护命令返回失败",
                details={"cache": name, "return_code": completed.returncode},
            )
        return {"cache": name, "status": "pruned", "return_code": 0}

    def _revalidate_after_prune(self, names: tuple[str, ...]) -> None:
        if not names:
            return
        self._environment_verifier(self._environment)

    def _entry(
        self,
        root: Path,
        budget: int | None,
        state: Mapping[str, object],
        *,
        size: int,
        files: int,
    ) -> dict[str, object]:
        usage = state.get("successful_usage", {})
        usage_value = usage.get(root.name) if isinstance(usage, dict) else None
        return {
            "path": str(root),
            "bytes": size,
            "files": files,
            "budget": budget,
            "over_budget": bool(budget is not None and size > budget),
            "last_successful_usage": usage_value,
            "referenced": root in {self.paths.uv_cache, self.paths.pnpm_store},
        }

    def _entry_paths(
        self,
        paths: list[Path],
        state: Mapping[str, object],
    ) -> dict[str, object]:
        measured = [
            (path, self._measure(path, collect_partials=False))
            for path in paths
        ]
        size = sum(result[0] for _, result in measured)
        files = sum(result[1] for _, result in measured)
        return {
            "path": str(self.paths.runtime),
            "bytes": size,
            "files": files,
            "budget": None,
            "over_budget": False,
            "last_successful_usage": state.get("last_successful_operation"),
            "referenced": False,
        }

    @staticmethod
    def _measure(
        root: Path,
        *,
        collect_partials: bool,
    ) -> tuple[int, int, list[Path]]:
        size = 0
        files = 0
        partials: list[Path] = []
        if root.is_dir():
            for path in root.rglob("*"):
                if collect_partials and (
                    path.name.endswith(".partial")
                    or path.name.startswith(".tmp-")
                ):
                    partials.append(path)
                if not path.is_file():
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                size += stat.st_size
                files += 1
        return size, files, partials

    @classmethod
    def _measure_path_details(cls, path: Path) -> tuple[int, int]:
        if path.is_file():
            try:
                return path.stat().st_size, 1
            except OSError:
                return 0, 0
        if path.is_dir():
            size, files, _ = cls._measure(path, collect_partials=False)
            return size, files
        return 0, 0

    @staticmethod
    def _status_after_known_removals(
        status: dict[str, object],
        removed: list[str],
        measurements: Mapping[Path, tuple[int, int]],
    ) -> dict[str, object]:
        """用删除前已取得的局部计数修正快照，不为 partial 再扫整棵缓存。"""

        entries = status.get("entries")
        if not isinstance(entries, dict):
            return status
        for raw in removed:
            path = Path(raw)
            size, files = measurements.get(path, (0, 0))
            resolved = path.resolve()
            for entry in entries.values():
                if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                    continue
                root = Path(entry["path"]).resolve()
                if resolved != root and not resolved.is_relative_to(root):
                    continue
                entry["bytes"] = max(0, int(entry.get("bytes", 0)) - size)
                entry["files"] = max(0, int(entry.get("files", 0)) - files)
                budget = entry.get("budget")
                entry["over_budget"] = bool(
                    isinstance(budget, int) and int(entry["bytes"]) > budget
                )
                break
        return status

    def _preview(
        self,
        operation: str,
        targets: list[Path],
        *,
        known_sizes: Mapping[str, int] | None = None,
    ) -> dict[str, object]:
        known = known_sizes or {}
        sizes = [
            (
                path,
                known[str(path.resolve())]
                if str(path.resolve()) in known
                else self._measure_path(path),
            )
            for path in targets
        ]
        return {
            "schema_version": "1",
            "operation": operation,
            "targets": [
                {"path": str(path), "estimated_bytes": size} for path, size in sizes
            ],
            "estimated_bytes": sum(size for _, size in sizes),
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
        }

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
                if active_lock is not None and active_lock.exists() and not lock_is_available(active_lock):
                    continue
                candidates.append(path)
        return sorted(candidates, key=str)

    def _expired_log_candidates(self) -> list[Path]:
        now = time.time()
        startup = self._retained_logs(
            self.paths.startup_logs,
            keep=20,
            cutoff=now - _STARTUP_LOG_MAX_AGE_SECONDS,
        )
        workers = self._retained_logs(
            self.paths.worker_logs,
            keep=None,
            cutoff=now - _WORKER_LOG_MAX_AGE_SECONDS,
        )
        return [*startup, *workers]

    def _startup_partial_candidates(self) -> list[Path]:
        """只看缓存根的直接子项，不为启动递归进入大型工具缓存。"""

        candidates: list[Path] = []
        for name in _CACHE_ROOTS:
            root = self.paths.cache / name
            for path in tuple(root.iterdir()) if root.is_dir() else ():
                if path.name.endswith(".partial") or path.name.startswith(".tmp-"):
                    candidates.append(path)
        return sorted(candidates, key=str)

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

    def _damaged_runtime_candidates(self) -> list[Path]:
        current = self._read_json(self._runtime_state_path) or {}
        current_paths = current.get("current_paths", ())
        current_values = current_paths if isinstance(current_paths, (list, tuple)) else ()
        referenced = {
            str(Path(value).resolve())
            for value in current_values
            if isinstance(value, str)
        }
        candidates: list[Path] = []
        for path in self.paths.runtime.rglob("*"):
            damaged = self._runtime_path_is_damaged(path)
            if damaged and str(path.resolve()) not in referenced:
                candidates.append(path)
        return sorted(candidates, key=str, reverse=True)

    def _runtime_path_is_damaged(self, path: Path) -> bool:
        if path.name.endswith(".partial") or (
            path.is_dir() and (path / ".invalid").is_file()
        ):
            return True
        if (
            path.resolve() != self.paths.frontend_workspace.resolve()
            or not path.is_dir()
        ):
            return False
        required = (
            path / "package.json",
            path / ".jiejian-source-digest",
            path / "node_modules" / ".modules.yaml",
        )
        return not all(item.is_file() for item in required)

    def _retired_runtime_candidates(self) -> list[Path]:
        state = self._read_json(self._runtime_state_path) or {}
        protected_values: list[str] = []
        for key in ("current_paths", "previous_paths"):
            values = state.get(key)
            if isinstance(values, (list, tuple)):
                protected_values.extend(value for value in values if isinstance(value, str))
        protected = tuple(Path(value).resolve() for value in protected_values)
        if not protected:
            return []
        candidates: list[Path] = []
        release_root = self.paths.runtime / "python" / "release"
        if release_root.is_dir():
            candidates.extend(path for path in release_root.iterdir() if path.is_dir())
        uv_root = self.paths.runtime / "uv"
        if uv_root.is_dir():
            for version_root in uv_root.iterdir():
                if version_root.is_dir():
                    candidates.extend(path for path in version_root.iterdir() if path.is_dir())
        playwright_root = self.paths.runtime / "playwright"
        if playwright_root.is_dir():
            candidates.extend(path for path in playwright_root.iterdir() if path.is_dir())
        return sorted(
            (
                path
                for path in candidates
                if not any(
                    reference == path.resolve()
                    or reference.is_relative_to(path.resolve())
                    or path.resolve().is_relative_to(reference)
                    for reference in protected
                )
            ),
            key=str,
        )

    def _remove_cache_path(self, path: Path) -> None:
        self._remove_under(path, self.paths.cache)

    def _remove_damaged_runtime(self, path: Path) -> None:
        if not self._runtime_path_is_damaged(path):
            raise JiejianError(ErrorCode.RUNTIME_REPAIR_FAILED, "运行时没有损坏标记")
        self._remove_under(path, self.paths.runtime)

    def _remove_retired_runtime(self, path: Path) -> None:
        if path.resolve() not in {
            candidate.resolve() for candidate in self._retired_runtime_candidates()
        }:
            raise JiejianError(ErrorCode.RUNTIME_REPAIR_FAILED, "运行时仍被当前或上一版本引用")
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
    def _measure_path(path: Path) -> int:
        if path.is_file():
            try:
                return path.stat().st_size
            except OSError:
                return 0
        if path.is_dir():
            total = 0
            for child in path.rglob("*"):
                if not child.is_file():
                    continue
                try:
                    total += child.stat().st_size
                except OSError:
                    continue
            return total
        return 0

    def _cache_path(self, name: str) -> Path:
        return {
            "uv": self.paths.uv_cache,
            "pnpm_store": self.paths.pnpm_store,
            "npm": self.paths.npm_cache,
            "vite": self.paths.vite_cache,
        }[name]

    def _tool_environment(self, executable: Path) -> dict[str, str]:
        by_casefold = {key.casefold(): value for key, value in self._environment.items()}
        result: dict[str, str] = {}
        for name in ("COMSPEC", "PATHEXT", "SYSTEMROOT", "WINDIR"):
            value = by_casefold.get(name.casefold())
            if value:
                result[name] = value
        result["PATH"] = os.pathsep.join(
            filter(
                None,
                (
                    str(executable.resolve().parent),
                    str(Path(result["SYSTEMROOT"]) / "System32")
                    if result.get("SYSTEMROOT")
                    else "",
                ),
            )
        )
        result["TEMP"] = result["TMP"] = str(self.paths.temp)
        result["UV_CACHE_DIR"] = str(self.paths.uv_cache)
        result["npm_config_cache"] = str(self.paths.npm_cache)
        return result

    @staticmethod
    def _read_json(path: Path) -> dict[str, object] | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    def _record(self, operation: str, details: Mapping[str, object]) -> None:
        existing = self._read_json(self._state_path) or {}
        payload = {
            **existing,
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
