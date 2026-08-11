"""浏览器事件的有界内存脱敏，不允许原始敏感值越过此边界。"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..protocols.recording_v1 import RecordingBudgetV1, RecordingHeaderV1
from ..redaction import REDACTED, redact_known_secrets

_MAX_STRUCTURED_DEPTH = 16
_MAX_CAPTURED_HEADERS = 64
_MAX_CAPTURED_HEADER_VALUE_CHARS = 1_024
_SENSITIVE_FIELD = re.compile(
    r"(?:authorization|cookie|credential|password|passwd|secret|token|"
    r"api[_-]?key|id[_-]?card|ssn|email|phone|address|full[_-]?name)",
    re.IGNORECASE,
)


class RecordingSanitizer:
    """按 RecordingBudgetV1 截断并脱敏 URL、头和结构化正文。"""

    def __init__(
        self,
        budget: RecordingBudgetV1,
        known_secrets: Sequence[str],
    ) -> None:
        self.budget = budget
        self.known_secrets = tuple(secret for secret in known_secrets if secret)

    def sanitize_headers(
        self,
        headers: Mapping[str, str],
    ) -> tuple[tuple[RecordingHeaderV1, ...], bool]:
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
                RecordingHeaderV1(
                    schema_version="1",
                    name=name,
                    value=safe_value,
                )
            )
            truncated = truncated or value_truncated
        return tuple(records), truncated

    def sanitize_url(self, value: str) -> tuple[str, bool]:
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
        prefix = value[: self.budget.max_body_bytes]
        encoded = prefix.encode("utf-8", errors="replace")
        truncated = len(value) > len(prefix) or len(encoded) > self.budget.max_body_bytes
        return self.sanitize_body_bytes(
            encoded[: self.budget.max_body_bytes],
            content_type,
            already_limited=truncated,
        )

    def sanitize_body_bytes(
        self,
        value: bytes,
        content_type: str,
        *,
        already_limited: bool = False,
    ) -> tuple[str | None, bool]:
        truncated = already_limited or len(value) > self.budget.max_body_bytes
        limited = value[: self.budget.max_body_bytes].decode("utf-8", errors="replace")
        if "json" in content_type.casefold():
            try:
                parsed: Any = json.loads(limited)
            except json.JSONDecodeError:
                return self._limit_body_text(limited, already_limited=truncated)
            safe = self._sanitize_value(parsed, depth=0)
            serialized = json.dumps(
                safe,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            return self._limit_body_text(serialized, already_limited=truncated)
        if "application/x-www-form-urlencoded" in content_type.casefold():
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
                urlencode(pairs), already_limited=truncated
            )
        return self._limit_body_text(limited, already_limited=truncated)

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
    ) -> tuple[str, bool]:
        safe = str(redact_known_secrets(value, self.known_secrets))
        encoded = safe.encode("utf-8")
        truncated = already_limited or len(encoded) > self.budget.max_body_bytes
        limited = encoded[: self.budget.max_body_bytes].decode("utf-8", errors="ignore")
        return limited, truncated
