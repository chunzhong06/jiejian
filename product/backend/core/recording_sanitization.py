# =============================================================================
# Recording 事件脱敏
#
# 定位
#   浏览器原始 payload 进入任何事件、日志或工件前的信任边界
#
# 职责
#   限制递归深度与大小｜替换已知 secret 和敏感字段｜输出可序列化安全值
#
# 边界
#   原始 secret 和超预算正文不得穿过本边界；脱敏结果本身不构成安全结论。
#
# 调用链
#   RecordingEventCollector → RecordingSanitizer → RecordingEvent
# =============================================================================

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from product.protocols.recording import RecordingBudget, RecordingEvent, RecordingHeader
from product.backend.core.redaction import REDACTED, redact_known_secrets

_MAX_STRUCTURED_DEPTH = 16
_MAX_CAPTURED_HEADERS = 64
_MAX_CAPTURED_HEADER_VALUE_CHARS = 1_024
_SENSITIVE_FIELD = re.compile(
    r"(?:authorization|cookie|credential|password|passwd|secret|token|"
    r"api[_-]?key|id[_-]?card|ssn|email|phone|address|full[_-]?name)",
    re.IGNORECASE,
)


class RecordingSanitizer:
    """按 RecordingBudget 截断并脱敏 URL、头和结构化正文。"""

    def __init__(
        self,
        budget: RecordingBudget,
        known_secrets: Sequence[str],
    ) -> None:
        self.budget = budget
        self.known_secrets = tuple(secret for secret in known_secrets if secret)

    def sanitize_headers(
        self,
        headers: Mapping[str, str],
    ) -> tuple[tuple[RecordingHeader, ...], bool]:
        """仅保留预算内 header，并统一替换敏感名称和已知秘密。"""

        truncated = len(headers) > _MAX_CAPTURED_HEADERS
        records = []
        for name, value in sorted(
            headers.items(), key=lambda item: item[0].casefold()
        )[:_MAX_CAPTURED_HEADERS]:
            if _SENSITIVE_FIELD.search(name):
                safe_value = REDACTED
                value_truncated = False
            else:
                safe_value, value_truncated = self.sanitize_text(value)
                if len(safe_value) > _MAX_CAPTURED_HEADER_VALUE_CHARS:
                    safe_value = safe_value[:_MAX_CAPTURED_HEADER_VALUE_CHARS]
                    value_truncated = True
            records.append(
                RecordingHeader(
                    name=name,
                    value=safe_value,
                )
            )
            truncated = truncated or value_truncated
        return tuple(records), truncated

    def sanitize_url(self, value: str) -> tuple[str, bool]:
        """移除 URL 用户信息和 fragment，并脱敏 query/path 中的敏感值。"""

        parsed = urlsplit(value)
        if parsed.username is not None or parsed.password is not None:
            return "[REDACTED_URL]", True
        query = []
        truncated = bool(parsed.fragment)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True):
            safe_key, key_truncated = self.sanitize_text(key)
            if _SENSITIVE_FIELD.search(key):
                safe_item, item_truncated = REDACTED, False
            else:
                safe_item, item_truncated = self.sanitize_text(item)
            query.append((safe_key, safe_item))
            truncated = truncated or key_truncated or item_truncated
        path, path_truncated = self.sanitize_text(parsed.path)
        safe_url = urlunsplit(
            (parsed.scheme, parsed.netloc, path, urlencode(query), "")
        )
        limited, url_truncated = self.sanitize_text(safe_url)
        return limited, truncated or path_truncated or url_truncated

    def sanitize_body(
        self,
        value: str | None,
        content_type: str,
    ) -> tuple[str | None, bool]:
        if value is None:
            return None, False
        try:
            encoded = value.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            return None, True
        if len(encoded) > self.budget.max_body_bytes:
            return None, True
        return self.sanitize_body_bytes(encoded, content_type)

    def sanitize_body_bytes(
        self,
        value: bytes,
        content_type: str,
        *,
        already_limited: bool = False,
    ) -> tuple[str | None, bool]:
        """按 content-type 解析有界正文；无法证明安全时丢弃原文并标记截断。"""

        if already_limited or len(value) > self.budget.max_body_bytes:
            return None, True
        try:
            limited = value.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return None, True
        normalized_type = content_type.casefold()
        if "json" in normalized_type:
            try:
                parsed: Any = json.loads(limited)
            except json.JSONDecodeError:
                return None, True
            safe = self._sanitize_value(parsed, depth=0)
            serialized = json.dumps(
                safe,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            return self._limit_body_text(serialized, already_limited=False)
        if "application/x-www-form-urlencoded" in normalized_type:
            pairs = []
            for key, item in parse_qsl(limited, keep_blank_values=True):
                safe_key, _ = self.sanitize_text(key)
                safe_item = (
                    REDACTED
                    if _SENSITIVE_FIELD.search(key)
                    else self.sanitize_text(item)[0]
                )
                pairs.append((safe_key, safe_item))
            return self._limit_body_text(
                urlencode(pairs), already_limited=False
            )
        if normalized_type.startswith("text/") or any(
            marker in normalized_type for marker in ("javascript", "xml")
        ):
            return self._limit_body_text(limited, already_limited=False)
        return None, True

    def sanitize_text(self, value: str) -> tuple[str, bool]:
        safe = str(redact_known_secrets(value, self.known_secrets))
        truncated = len(safe) > self.budget.max_field_chars
        return safe[: self.budget.max_field_chars], truncated

    def _sanitize_value(self, value: Any, *, depth: int) -> Any:
        if depth >= _MAX_STRUCTURED_DEPTH:
            return "[TRUNCATED]"
        if isinstance(value, Mapping):
            return {
                self.sanitize_text(str(key))[0]: (
                    REDACTED
                    if _SENSITIVE_FIELD.search(str(key))
                    else self._sanitize_value(item, depth=depth + 1)
                )
                for key, item in tuple(value.items())[:256]
            }
        if isinstance(value, list):
            return [
                self._sanitize_value(item, depth=depth + 1) for item in value[:256]
            ]
        if isinstance(value, str):
            return self.sanitize_text(value)[0]
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return self.sanitize_text(str(value))[0]

    def _limit_body_text(
        self,
        value: str,
        *,
        already_limited: bool,
    ) -> tuple[str | None, bool]:
        safe = str(redact_known_secrets(value, self.known_secrets))
        # 页面脚本和自由文本可能含未登记的内联秘密；复用协议规则，丢弃正文而非让采集回调抛错。
        try:
            RecordingEvent.reject_inline_secret_text(safe)
        except ValueError:
            return None, True
        encoded = safe.encode("utf-8")
        truncated = already_limited or len(encoded) > self.budget.max_body_bytes
        limited = encoded[: self.budget.max_body_bytes].decode("utf-8", errors="ignore")
        return limited, truncated
