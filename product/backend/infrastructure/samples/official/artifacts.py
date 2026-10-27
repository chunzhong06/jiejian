# 写入示例控制文件与脱敏描述，秘密仅由内存注入。
from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import uuid4
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.infrastructure.runtime.process.tree import process_tree_has_exited
from .models import AuthorizationOrder, BlobObservation, OwnerObservation


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
    values["JIEJIAN_SAMPLE_SQLITE_DATABASE"] = str(runtime_root / "database" / "collaboration-space.sqlite3")
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
    if path.is_file():
        previous=json.loads(path.read_text(encoding="utf-8"))
        for name in ("export_effect_id","view_effect_id"):
            value=previous.get(name)
            if value is not None:
                if not isinstance(value,str) or re.fullmatch(r"bef_[0-9a-f]{32}",value) is None:
                    raise ValueError("invalid sample effect mapping")
                payload[name]=value
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
    execution_mode: Literal["SYNCHRONOUS", "QUEUED"] = "QUEUED",
) -> None:
    """只改官方源码中唯一的机械顺序，让运行行为与源码 diff 保持一致。"""

    if execution_mode not in {"SYNCHRONOUS", "QUEUED"} or execution_mode == "SYNCHRONOUS" and authorization_order != "AUTHORIZE_BEFORE_ENQUEUE":
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "示例执行方式与授权顺序不匹配")

    source = f'''# 协作空间导出动作的授权顺序；官方样例会修改本文件来形成可核验的真实源码变化。

from typing import Literal


AuthorizationOrder = Literal[
    "ENQUEUE_BEFORE_AUTHORIZE",
    "AUTHORIZE_BEFORE_ENQUEUE",
]


def export_authorization_order() -> AuthorizationOrder:
    """返回当前导出实现采用的授权与后台任务顺序。"""

    return "{authorization_order}"


def export_execution_mode() -> Literal["SYNCHRONOUS", "QUEUED"]:
    """同步完成项目包或交给后台队列；两种模式都真实执行导出。"""
    return "{execution_mode}"
'''
    _write_text_atomic(path, source)


def _write_text_atomic(path: Path, content: str) -> None:
    """原子替换单个受控文本文件，避免 Sample 读取到半写入源码。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid4().hex}")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def _write_check_descriptor(descriptor_path: Path, runtime_root: Path, origin: str) -> None:
    """只派生本实例受控环境的 Cookie 观察入口，原六来源描述保持不变。"""
    if descriptor_path.resolve() != (runtime_root / "environment.json").resolve() or descriptor_path.is_symlink():
        raise JiejianError(ErrorCode.OFFICIAL_SAMPLE_START_FAILED, "官方示例描述路径无效")
    raw = descriptor_path.read_bytes()
    if len(raw) > 262_144:
        raise JiejianError(ErrorCode.OFFICIAL_SAMPLE_START_FAILED, "官方示例描述超过预算")
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise JiejianError(ErrorCode.OFFICIAL_SAMPLE_START_FAILED, "官方示例描述字段重复")
            value[key] = item
        return value
    descriptor = json.loads(raw, object_pairs_hook=unique)
    if (set(descriptor) != {"application", "owner_api", "sqlite", "audit", "task", "queue", "blob"}
            or _descriptor_origin(descriptor) != origin
            or descriptor["application"] != {"origin": origin, "project_id": "campus-digital-museum", "resource_id": "campus-digital-museum-package"}
            or descriptor["owner_api"] != {"origin": origin, "relative_path_template": "/api/observer/resources/{resource_id}",
                "credential_ref": "env:JIEJIAN_SAMPLE_OWNER_OBSERVER"}):
        raise JiejianError(ErrorCode.OFFICIAL_SAMPLE_START_FAILED, "官方示例描述不匹配")
    descriptor["owner_api"] = {"origin": origin,
        "relative_path_template": "/api/projects/campus-digital-museum/resources/{resource_id}/state",
        "credential_ref": "env:JIEJIAN_SAMPLE_ALICE_SESSION"}
    # 注册前仍由完整严格 loader 校验全部六来源与实际文件 hash。
    path = runtime_root / "check-environment.json"
    if path.exists():
        # 同一业务实例重载代码仍使用原观察描述；只接受完全相同的内容，不覆盖历史引用。
        if path.is_symlink() or path.stat().st_size > 262_144 or json.loads(path.read_bytes(), object_pairs_hook=unique) != descriptor:
            raise JiejianError(ErrorCode.OFFICIAL_SAMPLE_START_FAILED, "既有检查环境描述与重载实例不一致")
        return
    with path.open("x", encoding="utf-8") as stream:
        json.dump(descriptor, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


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
