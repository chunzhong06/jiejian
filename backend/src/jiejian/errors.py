"""跨 CLI、服务与领域层复用的稳定错误结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping


class ErrorCode(StrEnum):
    CFG_FILE = "CFG_FILE"
    CFG_INVALID = "CFG_INVALID"
    STATE_INVALID_ENTITY = "STATE_INVALID_ENTITY"
    STATE_INVALID_TARGET = "STATE_INVALID_TARGET"
    STATE_INVALID_TRANSITION = "STATE_INVALID_TRANSITION"
    STATE_OPERATOR_REQUIRED = "STATE_OPERATOR_REQUIRED"
    STATE_PRECONDITION = "STATE_PRECONDITION"
    CONTRACT_IMMUTABLE = "CONTRACT_IMMUTABLE"


@dataclass(frozen=True, slots=True)
class ErrorInfo:
    code: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = "1"

    def to_dict(self) -> dict[str, Any]:
        from .redaction import redact

        return redact(
            {
                "schema_version": self.schema_version,
                "code": self.code,
                "message": self.message,
                "details": dict(self.details),
            }
        )


class JiejianError(Exception):
    """具有稳定错误码且可以安全序列化的内部错误。"""

    def __init__(
        self,
        code: ErrorCode | str,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.info = ErrorInfo(
            code=code.value if isinstance(code, ErrorCode) else str(code),
            message=message,
            details=dict(details or {}),
        )
        super().__init__(f"{self.info.code}: {self.info.message}")

    @property
    def code(self) -> str:
        return self.info.code

    def to_dict(self) -> dict[str, Any]:
        return self.info.to_dict()
