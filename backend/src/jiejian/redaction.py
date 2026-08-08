"""日志、错误和诊断输出共用的最小脱敏器。"""

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
