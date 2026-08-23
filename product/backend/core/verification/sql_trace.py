# SQL Trace 只形成灰盒建议；该类型在结构上没有 Verdict 字段或判定权限。

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from product.backend.core.verification.permissions import (
    SecurityEffectKind,
    permission_model_sha256,
)


class SqlTraceModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

def sql_trace_advisory_sha256(value: Any) -> str:
    """复用 Verification canonical 规则，但显式限定为 SQL Trace Advisory 身份。"""

    return permission_model_sha256(value)


class SqlStatementKind(StrEnum):
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    OTHER = "OTHER"


class SqlTraceEvent(SqlTraceModel):
    sequence: int = Field(ge=1, le=4096)
    statement_kind: SqlStatementKind
    relation_name: str | None = Field(default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")
    normalized_statement_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class SqlTraceAdvisory(SqlTraceModel):
    trace_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    events: tuple[SqlTraceEvent, ...] = Field(default=(), max_length=4096)
    effect_suggestions: tuple[SecurityEffectKind, ...] = Field(default=(), max_length=6)
    contract_drift_subjects: tuple[str, ...] = Field(default=(), max_length=256)
    observer_suggestions: tuple[str, ...] = Field(default=(), max_length=16)
    verdict_authority: Literal[False] = False

    @model_validator(mode="after")
    def validate_advisory(self) -> SqlTraceAdvisory:
        if tuple(sorted(set(self.contract_drift_subjects))) != self.contract_drift_subjects:
            raise ValueError("SQL trace drift subjects must be unique and sorted")
        if tuple(sorted(set(self.observer_suggestions))) != self.observer_suggestions:
            raise ValueError("SQL trace observer suggestions must be unique and sorted")
        if len(set(self.effect_suggestions)) != len(self.effect_suggestions):
            raise ValueError("SQL trace effect suggestions must be unique")
        payload = self.model_dump(mode="json", exclude={"trace_fingerprint"})
        if self.trace_fingerprint != sql_trace_advisory_sha256(payload):
            raise ValueError("SQL trace advisory fingerprint does not match its facts")
        return self
