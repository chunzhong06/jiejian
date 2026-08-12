# =============================================================================
# 统一脱敏
#
# 定位
#   日志、异常、事件、诊断与 LLM 输入共享的输出前安全边界
#
# 职责
#   遮蔽常见 secret｜递归处理结构化值｜替换已知敏感明文
#
# 调用链
#   Runtime / Errors / Recording / Contracts → redaction → safe output or storage
# =============================================================================

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_KEY = re.compile(
    r"(?:authorization|cookie|credential|password|passwd|secret|token|api[_-]?key)",
    re.IGNORECASE,
)
_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_ASSIGNMENT = re.compile(
    r"\b(authorization|cookie|credential|password|passwd|secret|token|api[_-]?key)"
    r"(\s*[:=]\s*)([^\s,;]+)",
    re.IGNORECASE,
)


def redact(value: Any) -> Any:
    """递归脱敏常见秘密字段和字符串表示。"""

    if isinstance(value, Mapping):
        return {
            key: REDACTED if _SENSITIVE_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, str):
        value = _BEARER.sub(f"Bearer {REDACTED}", value)
        return _ASSIGNMENT.sub(
            lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}", value
        )
    return value


def redact_known_secrets(value: Any, secrets: tuple[str, ...]) -> Any:
    """递归替换运行时已解析秘密的精确值及其字符串包含形式。"""

    normalized = tuple(
        sorted({secret for secret in secrets if secret}, key=len, reverse=True)
    )

    def replace(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {replace(key): replace(nested) for key, nested in item.items()}
        if isinstance(item, list):
            return [replace(nested) for nested in item]
        if isinstance(item, tuple):
            return tuple(replace(nested) for nested in item)
        if isinstance(item, str):
            for secret in normalized:
                item = item.replace(secret, REDACTED)
        return item

    return replace(redact(value))
