# 规划、预览和清理当前运行根中可回收的缓存、日志与临时文件。
# 只处理已确认归属的项目，保留业务资料、活跃引用和未知归属文件。

from __future__ import annotations

import json
import hashlib
import os
import secrets
import shutil
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.infrastructure.maintenance.models import MaintenanceCandidate, MaintenancePlan
from product.backend.infrastructure.runtime.paths import RuntimePaths
from product.backend.infrastructure.maintenance.inventory import (
    Asset, StartupAssets, children, read_record, safe_tree, component_in_use,
    exclusive_file, overlaps,
)
from product.backend.infrastructure.runtime.generated_files import generated_file_owner, forget_generated_file
from product.backend.infrastructure.runtime.process.lock import lock_is_available

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






class LocalMaintenanceService:
    """只处理当前实例可安全删除的本地运行数据，并形成统一确认摘要。"""

    def __init__(
        self,
        var_dir: Path,
        *,
        active_runtime_paths: Callable[[], Iterable[Path]] | None = None,
        session_started_at: float | None = None,
        plan_ttl_seconds: int = _PLAN_TTL_SECONDS,
        development_root: Path | None = None,
    ) -> None:
        self.paths = RuntimePaths(var_dir).ensure_layout()
        self._active_runtime_paths = active_runtime_paths or (lambda: ())
        self._session_started_at = session_started_at or time.time()
        self._plan_ttl_us = plan_ttl_seconds * 1_000_000
        self._plans: dict[str, MaintenancePlan] = {}
        self._lock_path = self.paths.locks / "local-maintenance.lock"
        self._state_path = self.paths.runtime / "local-maintenance-state.json"
        self.assets = StartupAssets(self.paths.root, development_root)
        self._completed: dict[str, dict] = {}

    def status(self) -> dict[str, object]:
        """按生成方归属返回候选及保留原因；兼容统计也只包含已登记的闲置文件。"""

        return self._status_payload(self._inventory())

    def _status_payload(self, assets: list[Asset]) -> dict[str, object]:
        # 预览与展示复用同一次扫描；删除前仍逐项重读归属和占用，不能复用旧许可。
        state = read_record(self._state_path) or {}
        inventory = [self._asset_payload(item) for item in assets]

        # CLI 的分类摘要与 GUI 明细使用同一次扫描，避免占用状态和大小出现两套结果。
        def entry(category: str, root: Path) -> dict[str, object]:
            prefix = root.relative_to(self.paths.root).as_posix() + "/"
            items = [item for item in inventory if item["category"] == category
                     and item["state"] == "CLEANABLE"
                     and (root == self.paths.root or item["relative_path"].startswith(prefix))]
            return {"path": str(root), "bytes": sum(item["bytes"] or 0 for item in items),
                    "files": sum(item["files"] or 0 for item in items)}

        return {
            "schema_version": "1",
            "entries": {
                "assistant": entry("assistant", self.paths.assistant_cache),
                "logs": {
                    **entry("logs", self.paths.logs),
                    "categories": {name: entry("logs", root) for name, root in self._log_roots().items()},
                },
                "temporary": entry("temporary", self.paths.root),
            },
            "last_successful_operation": state.get("last_successful_operation"),
            "protected": self._protected_summary(),
            "inventory": inventory,
            "ownership_policy": "仅管理由启动和运行模块登记的闲置生成物",
        }

    def operate(
        self,
        operation: str,
        *,
        confirmed: bool = False,
        dry_run: bool = True,
        plan_id: str | None = None,
        item_ids: list[str] | None = None,
    ) -> dict[str, object]:
        """兼容 CLI 的命令形态；API/GUI 使用 preview 后按 plan_id 确认。"""

        if not confirmed and not dry_run:
            raise JiejianError(ErrorCode.INPUT_INVALID, "本地维护写操作需要显式确认")
        if confirmed and not dry_run:
            if plan_id is None:
                plan_id = str(self.preview(operation)["plan_id"])
            return self.execute(plan_id, expected_scope=operation, item_ids=item_ids)
        return self.preview(operation)

    def preview(self, operation: str) -> dict[str, object]:
        """扫描一次白名单候选并冻结短期计划，不在确认阶段重新计算。"""

        self._validate_operation(operation)
        with self._locked():
            now_us = self._now_us()
            self._prune_plans(now_us)
            inventory = self._inventory()
            candidates = tuple(
                self._snapshot_candidate(operation, asset)
                for asset in self._operation_candidates(operation, inventory)
                if safe_tree(asset.path, asset.root)
            )
            plan = MaintenancePlan(
                plan_id=secrets.token_urlsafe(24),
                scope=operation,
                generated_at_us=now_us,
                expires_at_us=now_us + self._plan_ttl_us,
                candidates=candidates,
            )
            self._plans[plan.plan_id] = plan
            return self._plan_payload(plan, self._status_payload(inventory))

    def execute(
        self,
        plan_id: str,
        *,
        expected_scope: str | None = None,
        item_ids: list[str] | None = None,
    ) -> dict[str, object]:
        """只执行被冻结计划中的项目，并为每项保留可解释的安全结果。"""

        with self._locked():
            now_us = self._now_us()
            if plan_id in self._completed:
                return self._completed[plan_id]
            plan = self._plans.get(plan_id)
            if plan is None or plan.expires_at_us < now_us:
                raise JiejianError(
                    ErrorCode.LOCAL_MAINTENANCE_FAILED,
                    "维护计划不存在或已过期，请重新预览",
                    details={"execution_started":False},
                )
            if expected_scope is not None and plan.scope != expected_scope:
                raise JiejianError(
                    ErrorCode.INPUT_INVALID,
                    "维护计划与请求操作不一致",
                )
            known_ids = {item.item_id for item in plan.candidates}
            selected_ids = known_ids if item_ids is None else set(item_ids)
            if not selected_ids or not selected_ids.issubset(known_ids):
                if known_ids or item_ids is not None:
                    raise JiejianError(ErrorCode.INPUT_INVALID, "清理选择不属于这份预览计划")
            self._plans.pop(plan_id, None)
            results = [self._execute_candidate(item) for item in plan.candidates if item.item_id in selected_ids]
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
            result = {
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
            }
            self._completed[plan_id] = result
            try:
                receipts = self.paths.runtime / "maintenance-results"
                receipts.mkdir(parents=True, exist_ok=True)
                receipt = receipts / (hashlib.sha256(plan_id.encode()).hexdigest() + ".json")
                temporary = receipt.with_suffix(".tmp")
                temporary.write_text(json.dumps({"schema_version":"1", "plan_id":plan_id,
                    "result":{key:value for key,value in result.items() if key != "status"}}, ensure_ascii=False), encoding="utf-8")
                os.replace(temporary, receipt)
            except OSError:
                result["recorded"] = False
            if len(self._completed) > 20:
                self._completed.pop(next(iter(self._completed)))
            return result

    def outcome(self, plan_id: str) -> dict[str, object]:
        if not 1 <= len(plan_id) <= 128:
            raise JiejianError(ErrorCode.INPUT_INVALID, "清理计划标识无效")
        if plan_id in self._completed:
            return {"state":"COMPLETED", "result":self._completed[plan_id]}
        receipt = read_record(self.paths.runtime / "maintenance-results" / (hashlib.sha256(plan_id.encode()).hexdigest() + ".json"))
        if receipt and receipt.get("plan_id") == plan_id and isinstance(receipt.get("result"),dict):
            return {"state":"COMPLETED", "result":{**receipt["result"], "status":self.status()}}
        return {"state":"PENDING" if plan_id in self._plans else "UNKNOWN", "result":None}

    def startup_maintenance(self) -> dict[str, object]:
        """启动后只回收产品临时目录、产品日志和助手缓存 partial。"""

        with self._locked():
            candidates: list[tuple[Path, Path]] = []
            candidates.extend((item.path, item.root) for item in self._inventory()
                              if item.state == "CLEANABLE" and item.category == "temporary"
                              and self._older_than(item.path, _ORPHAN_MIN_AGE_SECONDS))
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
                if safe_tree(path, root) and not self._path_is_in_use(path):
                    self._remove_under(path, root)
                    removed.append(str(path))
            self._record("startup-maintenance", {"removed": removed})
            return {
                "schema_version": "1",
                "operation": "startup-maintenance",
                "removed": removed,
                "protected": self._protected_summary(),
            }

    def _operation_candidates(self, operation: str, inventory: list[Asset] | None = None) -> list[Asset]:
        category = {"clear-assistant-cache":"assistant", "clear-logs":"logs", "clear-temporary":"temporary"}.get(operation)
        items = {item.path: item for item in (self._inventory() if inventory is None else inventory)
                 if item.state == "CLEANABLE" and (category is None or item.category == category)
                 and (operation != "repair-runtime" or self._runtime_path_is_damaged(item.path))}
        return [items[path] for path, _ in self._unique_candidates([(item.path, item.root) for item in items.values()])]

    def _inventory(self) -> list[Asset]:
        items = self.assets.scan()
        def add(path, category, label, known=True, protected=False):
            state, reason = "CLEANABLE", "运行产生且没有活动引用"
            if not safe_tree(path, self.paths.root):
                state, reason = "UNKNOWN", "包含链接或无法完整读取，暂不处理"
            elif protected or self._path_is_in_use(path):
                state, reason = "PROTECTED", "当前运行仍在使用"
            elif not known:
                state, reason = "UNKNOWN", "缺少来源或退出证明，暂不处理"
            items.append(Asset(path,self.paths.root,category,label,state,reason))
        for path in children(self.paths.assistant_cache):
            writing = path.name.startswith('.assistant-') and path.name.endswith('.tmp') and not self._older_than(path,_ORPHAN_MIN_AGE_SECONDS)
            add(path,"assistant","AI 辅助缓存",known=generated_file_owner(self.paths.root,path)=='assistant-cache',protected=writing)
        for root in self._log_roots().values():
            for path in self._log_files(root):
                add(path,"logs","历史运行日志",known=bool(generated_file_owner(self.paths.root,path)),protected=self._is_current_session_log(path))
        for root in (self.paths.temp, self.paths.identity_preparations,
                     self.paths.runtime / 'node-artifacts', self.paths.runtime / 'target-artifacts',
                     self.paths.official_sample_runtime, self.paths.runtime / 'maintenance-results', self.paths.runtime):
            for path in children(root):
                item = self._temporary_asset(path)
                if item is not None:
                    items.append(item)
        return items

    def _temporary_asset(self, path: Path) -> Asset | None:
        """只核对这一项的生成方和退出证明；列表和删除复查使用相同规则。"""

        known, busy = False, False
        if path.parent == self.paths.temp and path != self.paths.process_gates:
            label = "运行临时文件"
            process = read_record(path / '.runtime-process.json') if path.is_dir() else None
            if process and process.get('kind') == 'runtime-process' and process.get('name') == path.name and isinstance(process.get('kernel_identity'),dict):
                from product.backend.infrastructure.runtime.process.tree import kernel_tree_has_exited
                try:
                    known = kernel_tree_has_exited(process['kernel_identity'])
                    busy = not known
                except OSError:
                    known = False
        elif path.parent == self.paths.identity_preparations:
            label = "已结束登录准备"
            marker = read_record(path / '.runtime-idle.json')
            known = bool(marker and marker.get('kind') == 'runtime-idle' and marker.get('producer') == 'identity-preparation' and marker.get('name') == path.name)
        # 保留源副本和 Worker 恢复收据的读取契约；没有完整退出证明时不能猜测孤儿目录。
        elif path.parent in (self.paths.runtime / 'node-artifacts', self.paths.runtime / 'target-artifacts', self.paths.official_sample_runtime):
            label = "应用运行副本"
        elif path.parent == self.paths.runtime / 'maintenance-results':
            label = "清理回执"
            receipt = read_record(path)
            known = bool(receipt and isinstance(receipt.get('result'),dict) and isinstance(receipt.get('plan_id'),str))
            busy = not self._older_than(path, _ORPHAN_MIN_AGE_SECONDS)
        elif path.parent == self.paths.runtime and self._runtime_path_is_damaged(path):
            label = "运行残留"
        else:
            return None
        state, reason = "CLEANABLE", "运行产生且没有活动引用"
        if not safe_tree(path, self.paths.root):
            state, reason = "UNKNOWN", "包含链接或无法完整读取，暂不处理"
        elif busy or self._path_is_in_use(path):
            state, reason = "PROTECTED", "当前运行仍在使用"
        elif not known:
            state, reason = "UNKNOWN", "缺少来源或退出证明，暂不处理"
        return Asset(path, self.paths.root, "temporary", label, state, reason)

    def _relative_path(self, path: Path, root: Path) -> str:
        if path.is_relative_to(self.paths.root):
            return path.relative_to(self.paths.root).as_posix()
        return "共享启动目录/" + path.relative_to(root).as_posix()

    def _asset_payload(self, item: Asset) -> dict[str, object]:
        safe = item.state == "CLEANABLE" and safe_tree(item.path, item.root)
        size, files = self._measure(item.path) if safe else (None,None)
        return {"category":item.category,"label":item.label,"relative_path":self._relative_path(item.path,item.root),
                "state":item.state,"reason":item.reason,"bytes":size,"files":files}

    @staticmethod
    def _temporary_runtime_name(name: str) -> bool:
        return (
            name.endswith((".partial", ".tmp"))
            or name.startswith((".tmp-", "tmp-"))
        )

    def _protected_runtime_paths(self) -> set[Path]:
        protected = {
            self.paths.gui_browser.resolve(),
            self.paths.locks.resolve(),
            self.paths.process_gates.resolve(),
            self.paths.official_sample_runtime.resolve(),
            self.paths.frontend_dist.resolve(),
            self.paths.runtime.joinpath("node-artifacts").resolve(),
            self.paths.runtime.joinpath("target-artifacts").resolve(),
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

    def _retained_log_candidates(self, root: Path) -> list[Path]:
        cutoff = time.time() - _LOG_MAX_AGE_SECONDS
        owned = [path for path in self._log_files(root) if generated_file_owner(self.paths.root, path)]
        return [
            path
            for index, path in enumerate(owned)
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
                and self._older_than(path, _ORPHAN_MIN_AGE_SECONDS)
                and generated_file_owner(self.paths.root,path) == 'assistant-cache'
            ),
            key=lambda path: (len(path.parts), str(path)),
            reverse=True,
        ) if self.paths.assistant_cache.is_dir() else []

    @staticmethod
    def _path_has_active_lock(path: Path) -> bool:
        lock = path / ".active.lock" if path.is_dir() else None
        return bool(lock and lock.exists() and not lock_is_available(lock))

    @staticmethod
    def _mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return float("inf")

    def _older_than(self, path: Path, seconds: float) -> bool:
        return self._mtime(path) < time.time() - seconds

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
            "development_root_included": self.assets.root is not None,
            "test_root_included": False,
            "official_sample_runtime_included": False,
        }

    def _plan_payload(self, plan: MaintenancePlan, status: dict[str, object] | None = None) -> dict[str, object]:
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
                    "category": item.category,
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
            "status": self.status() if status is None else status,
        }

    def _snapshot_candidate(
        self,
        operation: str,
        asset: Asset,
    ) -> MaintenanceCandidate:
        path, root = asset.path, asset.root
        relative_path = self._relative_path(path, root)
        item_id = hashlib.sha256(
            f"{operation}\0{relative_path}".encode("utf-8")
        ).hexdigest()[:24]
        return MaintenanceCandidate(
            item_id=item_id,
            label=asset.label,
            relative_path=relative_path,
            path=path,
            root=root,
            estimated_bytes=self._measure(path)[0],
            fingerprint=self._path_fingerprint(path),
            category=asset.category,
        )

    def _execute_candidate(self, item: MaintenanceCandidate) -> dict[str, object]:
        result: dict[str, object] = {
            "item_id": item.item_id,
            "label": item.label,
            "relative_path": item.relative_path,
        }
        if not item.path.exists():
            return {**result, "status": "ALREADY_MISSING", "reason": "候选已不存在"}
        shared = self.assets.root is not None and item.root == self.assets.root
        references, valid = self.assets.references() if shared else (set(), True)
        if (not safe_tree(item.path, item.root) or not valid
                or item.category in {"assistant", "logs"} and not generated_file_owner(self.paths.root, item.path)):
            return {
                **result,
                "status": "SKIPPED_CHANGED",
                "reason": "候选安全边界已变化，已跳过",
            }
        if not shared and item.category == "temporary":
            current = self._temporary_asset(item.path)
            if current is None or current.state != "CLEANABLE":
                return {**result, "status":"SKIPPED_IN_USE", "reason":"运行引用或退出证明已变化，已跳过"}
        if (self._path_is_in_use(item.path) or shared and overlaps(item.path.resolve(), references)
                or item.category == 'components' and component_in_use(item.path)):
            return {
                **result,
                "status": "SKIPPED_IN_USE",
                "reason": "仍被当前运行环境使用，已跳过",
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

    def _path_is_in_use(self, path: Path) -> bool:
        if self._path_has_active_lock(path):
            return True
        return overlaps(path.resolve(), self._protected_runtime_paths())

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
        from product.backend.infrastructure.maintenance.inventory import linked
        if linked(root):
            return 0, 0
        if root.is_file():
            try:
                return root.stat().st_size, 1
            except OSError:
                return 0, 0
        size = 0
        files = 0
        if root.is_dir():
            for folder, directories, filenames in os.walk(root,followlinks=False):
                directories[:] = [name for name in directories if not linked(Path(folder)/name)]
                for name in filenames:
                    path=Path(folder)/name
                    if linked(path):
                        continue
                    try:
                        size += path.stat().st_size
                        files += 1
                    except OSError:
                        continue
        return size, files

    def _remove_under(self, path: Path, root: Path) -> None:
        if not safe_tree(path, root):
            raise JiejianError(ErrorCode.LOCAL_MAINTENANCE_FAILED, "维护路径越界")
        owner = generated_file_owner(self.paths.root, path)
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
        if owner:
            forget_generated_file(self.paths.root, path, owner)

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
        with self.assets.locked():
            with exclusive_file(self._lock_path):
                yield


__all__ = ["LocalMaintenanceService", "MaintenanceCandidate", "MaintenancePlan"]
