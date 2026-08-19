# 阶段 7.2 v2 API 请求边界；策略和操作者输入严格版本化。

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from .common import ApiModel


class BaselineAcceptRequest(ApiModel):
    schema_version: Literal["2"] = "2"
    accepted_run_id: str = Field(pattern=r"^run_[0-9a-f]{32}$")
    actor: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=1024)

    @field_validator("actor", "reason")
    @classmethod
    def require_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("actor and reason must be non-empty")
        return value.strip()


class GateEvaluateRequest(ApiModel):
    schema_version: Literal["2"] = "2"
    minimum_severity: Literal["low", "medium", "high", "critical"] = "low"
