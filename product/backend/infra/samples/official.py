# =============================================================================
# 官方 Sample 安装与本地运行时
#
# 定位
#   显式官方 Sample 根、ApplicationCore 运行目录与受控 Python 进程树之间的边界
#
# 职责
#   校验固定 manifest｜复制源码快照｜生成仅驻留内存的秘密｜动态端口启动与健康等待｜切换机械行为并回收进程树
#
# 边界
#   不创建产品 Project、Identity 或 Recording；不把秘密写入 manifest、descriptor、日志和公共状态。
#
# 调用链
#   Experience workflow → OfficialSampleManager → process environment / Sample Target
# =============================================================================

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.runtime.process.environment import (
    ProcessEnvironmentRole,
    process_environment_failure_summary,
    spawn_python_module,
)
from product.backend.infra.runtime.process.tree import (
    process_tree_has_exited,
    release_process_tree,
    terminate_process_tree,
)


AuthorizationOrder = Literal[
    "ENQUEUE_BEFORE_AUTHORIZE",
    "AUTHORIZE_BEFORE_ENQUEUE",
]
BlobObservation = Literal["AVAILABLE", "UNAVAILABLE"]
OwnerObservation = Literal["AVAILABLE", "UNAVAILABLE"]

_MANIFEST_FIELDS = {
    "schema_version",
    "sample_id",
    "display_name",
    "source_root",
    "entry_module",
    "health_path",
}
_EXPECTED_MANIFEST = {
    "schema_version": "1",
    "sample_id": "collaboration-space",
    "display_name": "协作空间",
    "source_root": "source",
    "entry_module": "server",
    "health_path": "/health",
}
_EXPERIENCE_ID = re.compile(r"exp_[0-9a-f]{32}\Z")
_MAX_MANIFEST_BYTES = 16_384
_SECRET_NAMES = (
    "JIEJIAN_SAMPLE_ALICE_PASSWORD",
    "JIEJIAN_SAMPLE_BOB_PASSWORD",
    "JIEJIAN_SAMPLE_ALICE_SESSION",
    "JIEJIAN_SAMPLE_BOB_SESSION",
    "JIEJIAN_SAMPLE_QUEUE_SAS",
    "JIEJIAN_SAMPLE_BLOB_SAS",
    "JIEJIAN_SAMPLE_TASK_BEARER",
    "JIEJIAN_SAMPLE_OWNER_OBSERVER",
)
_PATH_SECRET_NAMES = (
    "JIEJIAN_SAMPLE_SQLITE_DATABASE",
    "JIEJIAN_SAMPLE_AUDIT_ROOT",
)
_AUTHORIZATION_POLICY_FILE = "authorization_policy.py"


@dataclass(frozen=True, slots=True)
class OfficialSampleInstallation:
    """显式 Sample 根的非秘密可用性事实。"""

    available: bool
    sample_id: str = "collaboration-space"
    display_name: str = "协作空间"
    reason: str | None = None
    root: Path | None = field(default=None, repr=False)
    source: Path | None = field(default=None, repr=False)
    entry_module: str | None = None
    health_path: str | None = None


@dataclass(frozen=True, slots=True)
class OfficialSampleRuntime:
    """一个活跃 Sample 的内部运行事实；秘密和进程不得进入公共 DTO。"""

    experience_id: str
    sample_id: str
    display_name: str
    origin: str
    experience_root: Path
    source_root: Path
    runtime_root: Path
    descriptor_path: Path
    control_path: Path
    log_path: Path
    process: subprocess.Popen[Any] = field(repr=False, compare=False)
    secrets: dict[str, str] = field(repr=False, compare=False)


ProcessLauncher = Callable[..., subprocess.Popen[Any]]


class OfficialSampleManager:
    """管理当前 ApplicationCore 中至多一个官方 Sample 进程。"""

    def __init__(
        self,
        var_dir: Path,
        official_sample_root: Path | None,
        environment: Mapping[str, str],
        *,
        process_launcher: ProcessLauncher = spawn_python_module,
        health_timeout_seconds: float = 10.0,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._paths = RuntimePaths(var_dir).ensure_layout()
        self._environment = dict(environment)
        self._process_launcher = process_launcher
        self._health_timeout_seconds = health_timeout_seconds
        self._monotonic = monotonic
        self._sleeper = sleeper
        self._lock = RLock()
        self._active: OfficialSampleRuntime | None = None
        self.installation = _load_installation(official_sample_root)

    @property
    def active(self) -> OfficialSampleRuntime | None:
        with self._lock:
            runtime = self._active
            if runtime is not None and process_tree_has_exited(runtime.process):
                release_process_tree(runtime.process)
                self._active = None
                runtime = None
            return runtime

    def start(
        self,
        *,
        experience_id: str | None = None,
        authorization_order: AuthorizationOrder = "ENQUEUE_BEFORE_AUTHORIZE",
        owner_observation: OwnerObservation = "AVAILABLE",
        blob_observation: BlobObservation = "AVAILABLE",
    ) -> OfficialSampleRuntime:
        """复制官方源码并以动态端口启动；任一步失败都回收已创建进程。"""

        _validate_behavior(
            authorization_order,
            owner_observation,
            blob_observation,
        )
        with self._lock:
            if self.active is not None:
                raise JiejianError(
                    ErrorCode.OFFICIAL_SAMPLE_CONFLICT,
                    "已有官方示例正在运行",
                )
            installation = self.installation
            if not installation.available or installation.source is None:
                raise JiejianError(
                    ErrorCode.OFFICIAL_SAMPLE_UNAVAILABLE,
                    "官方示例当前不可用",
                )
            clean_id = experience_id or f"exp_{uuid4().hex}"
            if _EXPERIENCE_ID.fullmatch(clean_id) is None:
                raise JiejianError(
                    ErrorCode.STATE_PRECONDITION,
                    "官方示例体验标识无效",
                )
            experience_root = self._paths.official_sample_runtime / clean_id
            source_root = experience_root / "source"
            runtime_root = experience_root / "state"
            log_path = self._paths.logs / "official-samples" / f"{clean_id}.log"
            if experience_root.exists() or log_path.exists():
                raise JiejianError(
                    ErrorCode.OFFICIAL_SAMPLE_CONFLICT,
                    "官方示例体验目录已经存在",
                )
            _copy_source(installation.source, source_root)
            _write_authorization_policy(
                source_root / _AUTHORIZATION_POLICY_FILE,
                authorization_order,
            )
            runtime_root.mkdir(parents=True, exist_ok=False)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            control_path = runtime_root / "control.json"
            _write_control(
                control_path,
                authorization_order,
                owner_observation,
                blob_observation,
            )
            secret_values = _new_secret_values(runtime_root)
            child_environment = dict(self._environment)
            child_environment.update(
                {name: secret_values[name] for name in _SECRET_NAMES}
            )
            process: subprocess.Popen[Any] | None = None
            try:
                with log_path.open("ab", buffering=0) as log_stream:
                    process = self._process_launcher(
                        child_environment,
                        installation.entry_module or "",
                        "--runtime-root",
                        str(runtime_root),
                        "--port",
                        "0",
                        role=ProcessEnvironmentRole.SAMPLE,
                        secret_names=_SECRET_NAMES,
                        cwd=source_root,
                        stdout=log_stream,
                        stderr=subprocess.STDOUT,
                        stdin=subprocess.DEVNULL,
                        tree_name=f"jiejian-sample-{clean_id}",
                    )
                descriptor_path, origin = self._wait_until_healthy(
                    process,
                    runtime_root,
                    installation.health_path or "/health",
                )
                active = OfficialSampleRuntime(
                    experience_id=clean_id,
                    sample_id=installation.sample_id,
                    display_name=installation.display_name,
                    origin=origin,
                    experience_root=experience_root,
                    source_root=source_root,
                    runtime_root=runtime_root,
                    descriptor_path=descriptor_path,
                    control_path=control_path,
                    log_path=log_path,
                    process=process,
                    secrets=secret_values,
                )
                self._active = active
                _append_event(log_path, "OFFICIAL_SAMPLE_STARTED", origin=origin)
                return active
            except Exception as exc:
                process_state = _process_state(process)
                diagnostic = (
                    process_environment_failure_summary(exc)
                    if isinstance(exc, JiejianError)
                    else {}
                )
                if process is not None:
                    try:
                        terminate_process_tree(process, 3.0)
                    except Exception:
                        pass
                secret_values.clear()
                shutil.rmtree(experience_root, ignore_errors=True)
                _append_event(
                    log_path,
                    "OFFICIAL_SAMPLE_START_FAILED",
                    error_code=(
                        exc.code
                        if isinstance(exc, JiejianError)
                        else ErrorCode.OFFICIAL_SAMPLE_START_FAILED.value
                    ),
                    failure_type=type(exc).__name__,
                    process_state=process_state,
                    reason=(
                        str(diagnostic["reason"])
                        if diagnostic.get("reason") is not None
                        else None
                    ),
                    missing_names=(
                        tuple(str(name) for name in diagnostic["missing_names"])
                        if isinstance(diagnostic.get("missing_names"), list)
                        else None
                    ),
                )
                if isinstance(exc, JiejianError):
                    raise
                raise JiejianError(
                    ErrorCode.OFFICIAL_SAMPLE_START_FAILED,
                    "官方示例未能在有界时间内启动",
                ) from exc

    def switch_behavior(
        self,
        experience_id: str,
        *,
        authorization_order: AuthorizationOrder,
        owner_observation: OwnerObservation,
        blob_observation: BlobObservation,
    ) -> OfficialSampleRuntime:
        """先重置当前副作用，再原子切换机械行为；origin 与源码快照保持不变。"""

        _validate_behavior(
            authorization_order,
            owner_observation,
            blob_observation,
        )
        with self._lock:
            runtime = self._require_active(experience_id)
            policy_path = runtime.source_root / _AUTHORIZATION_POLICY_FILE
            previous_policy = policy_path.read_text(encoding="utf-8")
            try:
                with httpx.Client(trust_env=False, follow_redirects=False) as client:
                    response = client.post(
                        f"{runtime.origin}/reset",
                        headers={"X-Jiejian-Test-Mode": "1"},
                        timeout=2.0,
                    )
                    response.raise_for_status()
                _write_authorization_policy(policy_path, authorization_order)
                _write_control(
                    runtime.control_path,
                    authorization_order,
                    owner_observation,
                    blob_observation,
                )
            except (httpx.HTTPError, OSError) as exc:
                try:
                    _write_text_atomic(policy_path, previous_policy)
                except OSError:
                    pass
                raise JiejianError(
                    ErrorCode.OFFICIAL_SAMPLE_START_FAILED,
                    "官方示例行为切换失败",
                ) from exc
            _append_event(runtime.log_path, "OFFICIAL_SAMPLE_BEHAVIOR_CHANGED")
            return runtime

    def resolve_secret_names(self, names: tuple[str, ...] | list[str]) -> dict[str, str]:
        """只返回当前活跃体验明确请求的观察秘密。"""

        runtime = self.active
        if runtime is None:
            return {}
        requested = set(names)
        return {
            name: value
            for name, value in runtime.secrets.items()
            if name in requested
        }

    def stop(self, experience_id: str | None = None) -> None:
        """回收当前 Sample 进程树和会话目录；只保留独立历史日志。"""

        with self._lock:
            runtime = self._active
            if runtime is None:
                return
            if experience_id is not None and runtime.experience_id != experience_id:
                raise JiejianError(
                    ErrorCode.OFFICIAL_SAMPLE_CONFLICT,
                    "指定的官方示例体验不是当前活跃体验",
                )
            self._active = None
            termination_error: Exception | None = None
            try:
                terminate_process_tree(runtime.process, 3.0)
            except Exception as exc:  # pragma: no cover - 由平台进程树测试覆盖
                termination_error = exc
            runtime.secrets.clear()
            _append_event(runtime.log_path, "OFFICIAL_SAMPLE_STOPPED")
            try:
                shutil.rmtree(runtime.experience_root)
            except OSError as exc:
                raise JiejianError(
                    ErrorCode.OFFICIAL_SAMPLE_START_FAILED,
                    "官方示例运行目录清理失败",
                ) from exc
            if termination_error is not None:
                raise termination_error

    def _require_active(self, experience_id: str) -> OfficialSampleRuntime:
        runtime = self.active
        if runtime is None or runtime.experience_id != experience_id:
            raise JiejianError(
                ErrorCode.OFFICIAL_SAMPLE_CONFLICT,
                "官方示例体验当前未运行",
            )
        return runtime

    def _wait_until_healthy(
        self,
        process: subprocess.Popen[Any],
        runtime_root: Path,
        health_path: str,
    ) -> tuple[Path, str]:
        descriptor_path = runtime_root / "environment.json"
        deadline = self._monotonic() + self._health_timeout_seconds
        while self._monotonic() < deadline:
            if process_tree_has_exited(process):
                break
            try:
                descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
                origin = _descriptor_origin(descriptor)
                with httpx.Client(trust_env=False, follow_redirects=False) as client:
                    response = client.get(
                        f"{origin}{health_path}",
                        timeout=0.75,
                    )
                    if response.status_code == 200:
                        return descriptor_path, origin
            except (OSError, UnicodeError, json.JSONDecodeError, httpx.HTTPError, JiejianError):
                pass
            self._sleeper(0.05)
        raise JiejianError(
            ErrorCode.OFFICIAL_SAMPLE_START_FAILED,
            "官方示例未能在有界时间内启动",
        )


def _load_installation(root: Path | None) -> OfficialSampleInstallation:
    if root is None:
        return OfficialSampleInstallation(
            available=False,
            reason="未配置官方示例目录",
        )
    try:
        resolved = root.expanduser().resolve(strict=True)
        if not resolved.is_dir() or resolved.is_symlink():
            raise ValueError("sample root")
        manifest_path = resolved / "sample.json"
        raw = manifest_path.read_bytes()
        if not raw or len(raw) > _MAX_MANIFEST_BYTES:
            raise ValueError("manifest size")
        manifest = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_FIELDS:
            raise ValueError("manifest fields")
        if manifest != _EXPECTED_MANIFEST:
            raise ValueError("manifest values")
        source = (resolved / manifest["source_root"]).resolve(strict=True)
        source.relative_to(resolved)
        if not source.is_dir() or source.is_symlink():
            raise ValueError("source root")
        module_path = source.joinpath(*manifest["entry_module"].split(".")).with_suffix(".py")
        if not module_path.is_file() or module_path.is_symlink():
            raise ValueError("entry module")
        _reject_symlinks(source)
        return OfficialSampleInstallation(
            available=True,
            root=resolved,
            source=source,
            entry_module=manifest["entry_module"],
            health_path=manifest["health_path"],
        )
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return OfficialSampleInstallation(
            available=False,
            reason="官方示例安装不完整或无效",
        )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate manifest key")
        result[key] = value
    return result


def _reject_symlinks(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("sample symlink")


def _copy_source(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(source, destination, copy_function=shutil.copy2)
    except OSError as exc:
        raise JiejianError(
            ErrorCode.OFFICIAL_SAMPLE_START_FAILED,
            "官方示例源码复制失败",
        ) from exc


def _new_secret_values(runtime_root: Path) -> dict[str, str]:
    values = {name: secrets.token_urlsafe(32) for name in _SECRET_NAMES}
    # Azure 兼容观察器要求 SAS 是受限查询串；签名仍为每次体验独立的内存随机值。
    values["JIEJIAN_SAMPLE_QUEUE_SAS"] = (
        "sv=2023-11-03&se=2099-01-01T00%3A00%3A00Z&sp=r&sr=q"
        f"&sig={secrets.token_urlsafe(32)}"
    )
    values["JIEJIAN_SAMPLE_BLOB_SAS"] = (
        "sv=2023-11-03&se=2099-01-01T00%3A00%3A00Z&sp=rl&sr=c"
        f"&sig={secrets.token_urlsafe(32)}"
    )
    values["JIEJIAN_SAMPLE_SQLITE_DATABASE"] = str(runtime_root / "collaboration.db")
    values["JIEJIAN_SAMPLE_AUDIT_ROOT"] = str(runtime_root / "audit")
    return values


def _validate_behavior(
    authorization_order: str,
    owner_observation: str,
    blob_observation: str,
) -> None:
    if authorization_order not in {
        "ENQUEUE_BEFORE_AUTHORIZE",
        "AUTHORIZE_BEFORE_ENQUEUE",
    } or owner_observation not in {"AVAILABLE", "UNAVAILABLE"} or blob_observation not in {
        "AVAILABLE",
        "UNAVAILABLE",
    }:
        raise JiejianError(
            ErrorCode.STATE_PRECONDITION,
            "官方示例行为参数无效",
        )


def _write_control(
    path: Path,
    authorization_order: AuthorizationOrder,
    owner_observation: OwnerObservation,
    blob_observation: BlobObservation,
) -> None:
    payload = {
        "schema_version": "1",
        "authorization_order": authorization_order,
        "owner_observation": owner_observation,
        "blob_observation": blob_observation,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid4().hex}")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _write_authorization_policy(
    path: Path,
    authorization_order: AuthorizationOrder,
) -> None:
    """只改官方源码中唯一的机械顺序，让运行行为与源码 diff 保持一致。"""

    source = f'''# 协作空间导出动作的授权顺序；官方样例会修改本文件来形成可核验的真实源码变化。

from typing import Literal


AuthorizationOrder = Literal[
    "ENQUEUE_BEFORE_AUTHORIZE",
    "AUTHORIZE_BEFORE_ENQUEUE",
]


def export_authorization_order() -> AuthorizationOrder:
    """返回当前导出实现采用的授权与后台任务顺序。"""

    return "{authorization_order}"
'''
    _write_text_atomic(path, source)


def _write_text_atomic(path: Path, content: str) -> None:
    """原子替换单个受控文本文件，避免 Sample 读取到半写入源码。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid4().hex}")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def _descriptor_origin(descriptor: Any) -> str:
    if not isinstance(descriptor, dict):
        raise JiejianError(ErrorCode.OFFICIAL_SAMPLE_START_FAILED, "官方示例描述无效")
    application = descriptor.get("application")
    origin = application.get("origin") if isinstance(application, dict) else None
    if not isinstance(origin, str):
        raise JiejianError(ErrorCode.OFFICIAL_SAMPLE_START_FAILED, "官方示例描述无效")
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.port is None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or origin != f"http://127.0.0.1:{parsed.port}"
    ):
        raise JiejianError(ErrorCode.OFFICIAL_SAMPLE_START_FAILED, "官方示例描述无效")
    return origin


def _process_state(process: subprocess.Popen[Any] | None) -> str:
    """只记录 Sample 根进程是否形成，不暴露命令、环境或异常正文。"""

    if process is None:
        return "NOT_CREATED"
    try:
        return "EXITED" if process_tree_has_exited(process) else "RUNNING"
    except Exception:
        return "UNKNOWN"


def _append_event(
    path: Path,
    code: str,
    *,
    origin: str | None = None,
    error_code: str | None = None,
    failure_type: str | None = None,
    process_state: str | None = None,
    reason: str | None = None,
    missing_names: tuple[str, ...] | None = None,
) -> None:
    """追加无秘密的稳定 Sample 事件；不得写入命令、路径或异常正文。"""

    payload = {"event_code": code}
    for key, value in (
        ("origin", origin),
        ("error_code", error_code),
        ("failure_type", failure_type),
        ("process_state", process_state),
        ("reason", reason),
        ("missing_names", missing_names),
    ):
        if value is not None:
            payload[key] = value
    try:
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
            stream.write("\n")
    except OSError:
        pass


__all__ = [
    "AuthorizationOrder",
    "BlobObservation",
    "OwnerObservation",
    "OfficialSampleInstallation",
    "OfficialSampleManager",
    "OfficialSampleRuntime",
]
