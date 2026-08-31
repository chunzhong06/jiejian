# 本地观察来源组合
#
# 职责：读取已授权的本地环境描述，并把它组合为严格的 Observer/Profile 绑定。
# 边界：只消费非秘密描述和 env: 引用；不读取目标数据、不写入状态，也不参与安全结论。

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.security_setup.models import _observation_requirement
from product.protocols import (
    AsyncTaskApiLocator,
    AsyncTaskPollBudget,
    AzureBlobObjectLocator,
    AzureQueuePeekLocator,
    BlobObjectScanBudget,
    ObservationPhase,
    ObserverBudget,
    ObserverRequirementBinding,
    ObserverRequirementKind,
    ObserverSpec,
    ObserverTarget,
    ObserverType,
    OwnerApiLocator,
    QueuePeekBudget,
    SqliteQueryLocator,
    StructuredAuditLogLocator,
    AuditLogScanBudget,
)


_MAX_DESCRIPTOR_BYTES = 262_144
_SECRET_REF = re.compile(r"^env:[A-Z][A-Z0-9_]{0,127}$")
_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_AZURE_ACCOUNT = re.compile(r"^[a-z0-9]{3,24}$")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("环境描述包含重复字段")
        result[key] = value
    return result


def _fail(message: str) -> JiejianError:
    return JiejianError(ErrorCode.STATE_PRECONDITION, message)


def _section(value: Any, expected: set[str]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != expected:
        raise _fail("本地观察环境描述字段不完整或包含未知字段")
    return value


def _text(value: Any, *, maximum: int = 512) -> str:
    if type(value) is not str or not value or len(value) > maximum or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise _fail("本地观察环境描述包含无效文本")
    return value


def _secret_ref(value: Any) -> str:
    value = _text(value, maximum=136)
    if _SECRET_REF.fullmatch(value) is None:
        raise _fail("本地观察环境描述只能使用 env: 秘密引用")
    return value


def _relative_path(value: Any) -> str:
    value = _text(value, maximum=256)
    parts = value.split("/")
    if value.startswith(("/", "\\")) or "\\" in value or any(part in {"", ".", ".."} for part in parts):
        raise _fail("本地观察环境描述路径必须是安全的相对路径")
    return value


def _origin(value: Any, *, expected: str | None = None) -> str:
    value = _text(value, maximum=256)
    parsed = urlsplit(value)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise _fail("本地观察环境描述必须使用精确的 loopback origin")
    try:
        port = parsed.port
    except ValueError as exc:
        raise _fail("本地观察环境描述端口无效") from exc
    if port is None or not 1 <= port <= 65535 or value != f"http://127.0.0.1:{port}":
        raise _fail("本地观察环境描述 origin 未规范化")
    if expected is not None and value != expected:
        raise _fail("本地观察环境描述 origin 与已确认应用地址不一致")
    return value


def _json_load(raw: bytes) -> dict[str, Any]:
    if len(raw) > _MAX_DESCRIPTOR_BYTES:
        raise _fail("本地观察环境描述超过大小预算")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise _fail("本地观察环境描述不是有效 JSON") from exc
    if type(value) is not dict:
        raise _fail("本地观察环境描述根必须是对象")
    return value


def _bounded_id(prefix: str, action_id: str, source: str) -> str:
    value = f"{prefix}_{hashlib.sha256(f'{action_id}:{source}'.encode()).hexdigest()[:20]}"
    if _ID.fullmatch(value) is None:
        raise _fail("本地观察来源标识无法安全生成")
    return value


def _target(action_id: str, source: str, locator: Any) -> ObserverTarget:
    token = hashlib.sha256(f"{action_id}:{source}".encode()).hexdigest()[:20]
    return ObserverTarget(
        target_id=f"local-target-{token}",
        locator=locator,
        normalization_id=f"local-normalizer-{token}",
        normalization_version="1",
    )


def _spec(
    action_id: str,
    source: str,
    observer_type: ObserverType,
    locator: Any,
    phases: tuple[ObservationPhase, ...],
    *,
    required: bool,
    timeout_us: int,
    max_rows: int,
    max_bytes: int,
) -> ObserverSpec:
    return ObserverSpec(
        observer_id=_bounded_id(f"local-{source}", action_id, "observer"),
        observer_type=observer_type,
        target=_target(action_id, source, locator),
        phases=phases,
        required=required,
        budget=ObserverBudget(
            timeout_us=timeout_us,
            max_rows=max_rows,
            max_bytes=max_bytes,
        ),
    )


@dataclass(frozen=True, slots=True)
class LocalObserverWiring:
    """单一受限 Action 的本地六来源组合结果。"""

    action_id: str
    descriptor_fingerprint: str
    observers: tuple[ObserverSpec, ...]
    bindings: tuple[ObserverRequirementBinding, ...]
    required_channels: tuple[str, ...]
    corroborating_channels: tuple[str, ...]


def load_local_observer_wiring(
    descriptor_path: str | None,
    *,
    var_dir: Path,
    action_id: str,
    expected_origin: str | None,
    expected_resource_id: str,
    resource_mismatch_is_disabled: bool = False,
) -> LocalObserverWiring | None:
    """从受控环境路径构造本地观察组合；未启用时保留普通 Owner 配置。"""

    if descriptor_path is None or not descriptor_path.strip():
        return None
    try:
        resolved_descriptor = Path(descriptor_path).expanduser().resolve()
        root = var_dir.resolve()
        resolved_descriptor.relative_to(root)
        raw = resolved_descriptor.read_bytes()
    except (OSError, RuntimeError, ValueError) as exc:
        raise _fail("本地观察环境描述无法在运行目录内读取") from exc
    descriptor = _json_load(raw)
    sections = {"application", "owner_api", "sqlite", "audit", "task", "queue", "blob"}
    if set(descriptor) != sections:
        raise _fail("本地观察环境描述根字段不完整或包含未知字段")
    application = _section(descriptor["application"], {"origin", "project_id", "resource_id"})
    owner = _section(descriptor["owner_api"], {"origin", "relative_path_template", "credential_ref"})
    sqlite = _section(descriptor["sqlite"], {"relative_path", "database_secret_ref", "query_template_id", "table_or_view"})
    audit = _section(descriptor["audit"], {"relative_path", "authorized_root_ref", "relative_file_pattern", "allowed_fields"})
    task = _section(descriptor["task"], {"base_url", "relative_path_template", "read_only_credential_ref"})
    queue = _section(descriptor["queue"], {"service_url", "account", "queue_name", "read_only_sas_ref", "allowed_fields"})
    blob = _section(descriptor["blob"], {"service_url", "account", "container_name", "prefix_template", "read_only_sas_ref", "allowed_metadata_fields"})
    origin = _origin(application["origin"], expected=expected_origin)
    application_project_id = _text(application["project_id"], maximum=64)
    application_resource_id = _text(application["resource_id"], maximum=256)
    if _ID.fullmatch(application_project_id) is None or _ID.fullmatch(application_resource_id) is None:
        raise _fail("本地观察环境描述项目或资源标识无效")
    if application_resource_id != expected_resource_id:
        if resource_mismatch_is_disabled:
            return None
        raise _fail("本地观察环境描述未绑定当前测试资源")
    if _origin(owner["origin"], expected=origin) != origin:
        raise _fail("所有者观察 origin 不一致")
    owner_path = _text(owner["relative_path_template"], maximum=512)
    owner_ref = _secret_ref(owner["credential_ref"])
    _relative_path(sqlite["relative_path"])
    sqlite_ref = _secret_ref(sqlite["database_secret_ref"])
    sqlite_query = _text(sqlite["query_template_id"], maximum=64)
    sqlite_table = _text(sqlite["table_or_view"], maximum=64)
    audit_path = _relative_path(audit["relative_path"])
    audit_ref = _secret_ref(audit["authorized_root_ref"])
    audit_pattern = _text(audit["relative_file_pattern"], maximum=64)
    if audit_path.rsplit("/", 1)[-1] != audit_pattern:
        raise _fail("审计观察文件名与相对路径不一致")
    audit_fields = tuple(_text(item, maximum=64) for item in audit["allowed_fields"])
    if type(audit["allowed_fields"]) is not list or len(set(audit_fields)) != len(audit_fields):
        raise _fail("本地观察环境描述字段白名单无效")
    task_origin = _origin(task["base_url"], expected=origin)
    task_path = _text(task["relative_path_template"], maximum=512)
    task_ref = _secret_ref(task["read_only_credential_ref"])
    queue_account = _text(queue["account"], maximum=24)
    blob_account = _text(blob["account"], maximum=24)
    if _AZURE_ACCOUNT.fullmatch(queue_account) is None or _AZURE_ACCOUNT.fullmatch(blob_account) is None:
        raise _fail("Azure 观察账户标识无效")
    queue_url = _text(queue["service_url"], maximum=256)
    blob_url = _text(blob["service_url"], maximum=256)
    if queue_url != f"{origin}/{queue_account}" or blob_url != f"{origin}/{blob_account}":
        raise _fail("Azure 观察服务地址与账户不一致")
    queue_name = _text(queue["queue_name"], maximum=64)
    queue_ref = _secret_ref(queue["read_only_sas_ref"])
    if type(queue["allowed_fields"]) is not list:
        raise _fail("本地观察环境描述字段白名单无效")
    queue_fields = tuple(_text(item, maximum=64) for item in queue["allowed_fields"])
    if len(set(queue_fields)) != len(queue_fields):
        raise _fail("本地观察环境描述字段白名单无效")
    container_name = _text(blob["container_name"], maximum=64)
    blob_prefix = _text(blob["prefix_template"], maximum=256)
    blob_ref = _secret_ref(blob["read_only_sas_ref"])
    if type(blob["allowed_metadata_fields"]) is not list:
        raise _fail("本地观察环境描述字段白名单无效")
    blob_fields = tuple(_text(item, maximum=64) for item in blob["allowed_metadata_fields"])
    if len(set(blob_fields)) != len(blob_fields):
        raise _fail("本地观察环境描述字段白名单无效")

    owner_req = _observation_requirement(action_id)
    sqlite_req = _bounded_id("sqlite_state", action_id, "requirement")
    audit_req = _bounded_id("audit_log", action_id, "requirement")
    task_req = _bounded_id("async_task", action_id, "requirement")
    queue_req = _bounded_id("queue_peek", action_id, "requirement")
    blob_req = _bounded_id("blob_object", action_id, "requirement")
    common_phases = (ObservationPhase.BEFORE, ObservationPhase.AFTER, ObservationPhase.EVENTUAL)
    observers = (
        _spec(action_id, "owner", ObserverType.OWNER_API, OwnerApiLocator(relative_path_template=owner_path), (ObservationPhase.BASELINE, *common_phases), required=True, timeout_us=5_000_000, max_rows=1, max_bytes=262_144),
        _spec(action_id, "sqlite", ObserverType.READ_ONLY_SQLITE, SqliteQueryLocator(query_template_id=sqlite_query, table_or_view=sqlite_table, database_secret_ref=sqlite_ref), common_phases, required=False, timeout_us=5_000_000, max_rows=1, max_bytes=262_144),
        _spec(action_id, "audit", ObserverType.STRUCTURED_AUDIT_LOG, StructuredAuditLogLocator(authorized_root_ref=audit_ref, relative_file_pattern=audit_pattern, allowed_fields=audit_fields, scan_budget=AuditLogScanBudget(max_files=4, max_lines=256, max_line_bytes=4096)), common_phases, required=False, timeout_us=5_000_000, max_rows=32, max_bytes=262_144),
        _spec(action_id, "task", ObserverType.ASYNC_TASK_STATUS, AsyncTaskApiLocator(base_url=task_origin, relative_path_template=task_path, read_only_credential_ref=task_ref, allow_private_network=False, allow_loopback_http=True, poll_budget=AsyncTaskPollBudget(max_polls=20, poll_interval_us=50_000, per_request_timeout_us=250_000, max_response_bytes=262_144)), (ObservationPhase.EVENTUAL,), required=False, timeout_us=8_000_000, max_rows=1, max_bytes=262_144),
        _spec(action_id, "queue", ObserverType.AZURE_QUEUE_PEEK, AzureQueuePeekLocator(allow_loopback_http=True, service_url=queue_url, queue_name=queue_name, read_only_sas_ref=queue_ref, exclusive_test_queue=True, allowed_fields=queue_fields, peek_budget=QueuePeekBudget(max_messages=8, max_message_bytes=8192, max_total_bytes=65536, max_attempts=3, per_request_timeout_us=1_000_000, retry_interval_us=50_000)), (ObservationPhase.EVENTUAL,), required=False, timeout_us=4_000_000, max_rows=8, max_bytes=262_144),
        _spec(action_id, "blob", ObserverType.AZURE_BLOB_OBJECT, AzureBlobObjectLocator(allow_loopback_http=True, service_url=blob_url, container_name=container_name, prefix_template=blob_prefix, read_only_sas_ref=blob_ref, exclusive_test_container=True, allowed_metadata_fields=blob_fields, scan_budget=BlobObjectScanBudget(page_size=1, max_pages=1, max_objects=1, max_object_bytes=262_144, max_total_bytes=262_144, max_attempts=3, per_request_timeout_us=1_000_000, retry_interval_us=50_000)), common_phases, required=True, timeout_us=10_000_000, max_rows=1, max_bytes=262_144),
    )
    bindings = tuple(
        ObserverRequirementBinding(
            requirement_id=requirement_id,
            kind=ObserverRequirementKind.OBSERVER_SPEC,
            observer_id=spec.observer_id,
            observer_type=spec.observer_type,
            credential_ref=owner_ref if requirement_id == owner_req else None,
            phases=spec.phases,
        )
        for requirement_id, spec in zip((owner_req, sqlite_req, audit_req, task_req, queue_req, blob_req), observers, strict=True)
    )
    descriptor_fingerprint = hashlib.sha256(json.dumps(descriptor, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return LocalObserverWiring(
        action_id=action_id,
        descriptor_fingerprint=descriptor_fingerprint,
        observers=observers,
        bindings=bindings,
        required_channels=(owner_req, blob_req),
        corroborating_channels=(sqlite_req, audit_req, task_req, queue_req),
    )


__all__ = [
    "LocalObserverWiring",
    "load_local_observer_wiring",
]
