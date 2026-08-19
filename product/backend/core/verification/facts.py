# =============================================================================
# 通用执行与观察事实
#
# 定位
# 具体执行/观察适配器与 Verification 判定之间的纯事实语言。
#
# 职责
# 表达执行结果｜表达资源观察效果｜校验事实与 case 的稳定关联
#
# 边界
# HTTP、数据库、队列等适配器字段必须在进入本模块前归约；事实本身不决定 Finding 或 Gate。
#
# 调用链
# Execution/Observer adapters → ExecutionFact / ObservationFact → Verification
# =============================================================================

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


_ID = r"^[a-z][a-z0-9_-]{0,63}$"
_HEX = r"^[0-9a-f]{64}$"
_REASON = r"^[A-Z][A-Z0-9_]{0,127}$"


class FactModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal["2"] = "2"


class TargetType(StrEnum):
    WEB = "WEB"
    CLI_APPLICATION = "CLI_APPLICATION"
    MCP_AGENT = "MCP_AGENT"


class ExecutionOutcome(StrEnum):
    ACCEPTED = "ACCEPTED"
    DENIED = "DENIED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class ObservedEffect(StrEnum):
    CONFIRMED = "CONFIRMED"
    ABSENT = "ABSENT"
    UNKNOWN = "UNKNOWN"


def _reason_codes(values: tuple[str, ...]) -> tuple[str, ...]:
    if len(values) != len(set(values)) or any(re.fullmatch(_REASON, value) is None for value in values):
        raise ValueError("reason_codes must contain unique stable codes")
    return tuple(sorted(values))


class ExecutionFact(FactModel):
    case_id: str = Field(pattern=_ID)
    action_id: str = Field(pattern=_ID)
    target_type: TargetType
    outcome: ExecutionOutcome
    execution_marker: str = Field(pattern=_ID)
    input_hash: str = Field(pattern=_HEX)
    output_hash: str = Field(pattern=_HEX)
    reason_codes: tuple[str, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def validate_reasons(self) -> ExecutionFact:
        reasons = _reason_codes(self.reason_codes)
        if self.outcome in {ExecutionOutcome.ACCEPTED, ExecutionOutcome.DENIED} and reasons:
            raise ValueError("successful execution facts cannot contain failure reasons")
        if self.outcome in {ExecutionOutcome.FAILED, ExecutionOutcome.UNKNOWN} and not reasons:
            raise ValueError("failed or unknown execution facts require a reason")
        object.__setattr__(self, "reason_codes", reasons)
        return self


class ObservationFact(FactModel):
    requirement_id: str = Field(pattern=_ID)
    resource_id: str = Field(pattern=_ID)
    effect: ObservedEffect
    complete: bool
    reliable: bool
    reason_codes: tuple[str, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def validate_observation(self) -> ObservationFact:
        reasons = _reason_codes(self.reason_codes)
        if self.effect is ObservedEffect.UNKNOWN and (self.complete and self.reliable):
            raise ValueError("unknown observation cannot be complete and reliable")
        if not self.complete or not self.reliable:
            if not reasons:
                raise ValueError("incomplete or unreliable observations require a reason")
        elif reasons:
            raise ValueError("complete reliable observations cannot contain failure reasons")
        object.__setattr__(self, "reason_codes", reasons)
        return self
