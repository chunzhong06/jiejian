# Observer canonical/hash 与严格 JSON 解析入口；不放宽秘密拒绝和身份关联。

from __future__ import annotations

import hashlib
from typing import Any, TypeVar

from pydantic import BaseModel
from product.protocols.codec import decode_json

from .config import OBSERVER_JSON_MAX_BYTES
from .invocation import (
    AsyncTaskObserverInvocation,
    AuditLogObserverInvocation,
    ObserverInvocation,
)
from .result import ObservationEnvelope, _json_bytes, _reject_secret_values

T = TypeVar("T", bound=BaseModel)


def canonical_json_bytes(value: Any) -> bytes:
    """将 Observer 协议对象编码为稳定的 canonical JSON 字节。"""

    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    return _json_bytes(value)


def observer_canonical_sha256(value: Any) -> str:
    """返回 Observer canonical JSON 的 SHA-256，不改变输入对象。"""

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def parse_observer_json(
    payload: bytes,
    model_type: type[T],
    *,
    known_secrets: tuple[str, ...] = (),
) -> T:
    parsed = decode_json(payload, limit=OBSERVER_JSON_MAX_BYTES)
    expected_version = {
        ObserverInvocation: "1",
        AsyncTaskObserverInvocation: "1",
        AuditLogObserverInvocation: "1",
        ObservationEnvelope: "1",
    }.get(model_type)
    if expected_version is None or parsed.get("schema_version") != expected_version:
        raise ValueError("observer root schema_version is missing or unsupported")
    _reject_secret_values(parsed, known_secrets)
    # 保留 JSON 模式对 enum、tuple 的严格转换。
    return model_type.model_validate_json(payload)
