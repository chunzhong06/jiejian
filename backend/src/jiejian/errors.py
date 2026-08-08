"""跨 CLI、服务与领域层复用的稳定错误结构。"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Mapping

from .redaction import redact


class ErrorCode(StrEnum):
    CFG_FILE = "CFG_FILE"
    CFG_INVALID = "CFG_INVALID"
    INPUT_FILE = "INPUT_FILE"
    INPUT_INVALID = "INPUT_INVALID"
    INPUT_PATH = "INPUT_PATH"
    SCOPE_URL = "SCOPE_URL"
    SCOPE_HOST = "SCOPE_HOST"
    SCOPE_PORT = "SCOPE_PORT"
    SCOPE_PRIVATE_NETWORK = "SCOPE_PRIVATE_NETWORK"
    SCOPE_REDIRECT = "SCOPE_REDIRECT"
    SECRET_MISSING = "SECRET_MISSING"
    EXEC_REQUEST = "EXEC_REQUEST"
    EXEC_TIMEOUT = "EXEC_TIMEOUT"
    EXEC_BUDGET = "EXEC_BUDGET"
    EXEC_RESPONSE_TOO_LARGE = "EXEC_RESPONSE_TOO_LARGE"
    ARTIFACT_WRITE = "ARTIFACT_WRITE"
    REPORT_NOT_FOUND = "REPORT_NOT_FOUND"
    STATE_INVALID_ENTITY = "STATE_INVALID_ENTITY"
    STATE_INVALID_TARGET = "STATE_INVALID_TARGET"
    STATE_INVALID_TRANSITION = "STATE_INVALID_TRANSITION"
    STATE_OPERATOR_REQUIRED = "STATE_OPERATOR_REQUIRED"
    STATE_PRECONDITION = "STATE_PRECONDITION"
    CONTRACT_IMMUTABLE = "CONTRACT_IMMUTABLE"


class JiejianError(Exception):
    """具有稳定错误码且可以安全序列化的内部错误。"""

    def __init__(
        self,
        code: ErrorCode | str,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self._code = code.value if isinstance(code, ErrorCode) else str(code)
        self._message = message
        self._details = dict(details or {})
        super().__init__(f"{self._code}: {redact(self._message)}")

    @property
    def code(self) -> str:
        return self._code

    def to_dict(self) -> dict[str, Any]:
        return redact(
            {
                "schema_version": "1",
                "code": self._code,
                "message": self._message,
                "details": self._details,
            }
        )
