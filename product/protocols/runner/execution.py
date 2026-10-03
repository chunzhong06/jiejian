# =============================================================================
# 跨 Target 执行协议
#
# 定位
#   Web V1 与未来 Target 均可复用的预算、绑定和严格协议基类。
#
# 职责
#   约束执行预算｜绑定主体、效果与观察要求｜提供统一严格模型配置
#
# 边界
#   不包含 Web Target、HTTP Workflow、Cookie/OAuth 身份或未来 Target 占位。
#
# 调用链
#   WebExecutionProfile / RunnerInput → Target Runtime / Observer / Verification
# =============================================================================

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from product.backend.core.identifiers import PROJECT_ID_PATTERN
from product.protocols.observer import ObservationPhase, ObserverType


class ProtocolModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )
class ExecutionBudget(ProtocolModel):
    max_requests: int = Field(ge=1, le=500)
    request_timeout_us: int = Field(ge=1, le=30_000_000)
    max_duration_us: int = Field(ge=1, le=3_600_000_000)
    max_response_bytes: int = Field(ge=1, le=4_194_304)
    max_cases: int = Field(ge=1, le=8192)
    max_parallel_cases: Literal[1]


class SubjectExecutionBinding(ProtocolModel):
    subject_id: str = Field(pattern=PROJECT_ID_PATTERN)
    identity_id: str = Field(pattern=PROJECT_ID_PATTERN)


class ObserverRequirementKind(StrEnum):
    OBSERVER_SPEC = "OBSERVER_SPEC"


class EffectClosurePolicy(StrEnum):
    IMMEDIATE = "IMMEDIATE"
    TERMINAL_STATE = "TERMINAL_STATE"
    BOUNDED_QUIESCENCE = "BOUNDED_QUIESCENCE"
    EXCLUSIVE_CHANNEL_WINDOW = "EXCLUSIVE_CHANNEL_WINDOW"


class EffectBinding(ProtocolModel):
    """把安全效果绑定到权威通道与可选佐证通道。"""

    effect_id: str = Field(pattern=PROJECT_ID_PATTERN)
    required_channels: tuple[str, ...] = Field(min_length=1, max_length=32)
    corroborating_channels: tuple[str, ...] = Field(default=(), max_length=32)
    closure_policy: EffectClosurePolicy
    projection_version: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")

    @model_validator(mode="after")
    def validate_effect_binding(self) -> EffectBinding:
        if len(set(self.required_channels)) != len(self.required_channels):
            raise ValueError("required effect channels must be unique")
        if len(set(self.corroborating_channels)) != len(
            self.corroborating_channels
        ):
            raise ValueError("corroborating effect channels must be unique")
        if set(self.required_channels) & set(self.corroborating_channels):
            raise ValueError(
                "required and corroborating effect channels must be disjoint"
            )
        return self


class ObserverRequirementBinding(ProtocolModel):
    requirement_id: str = Field(pattern=PROJECT_ID_PATTERN)
    kind: ObserverRequirementKind
    observer_id: str | None = Field(default=None, pattern=PROJECT_ID_PATTERN)
    observer_type: ObserverType | None = None
    credential_ref: str | None = Field(
        default=None, pattern=r"^env:[A-Z][A-Z0-9_]{0,127}$"
    )
    identity_id: str | None = Field(default=None, pattern=PROJECT_ID_PATTERN)
    phases: tuple[ObservationPhase, ...] = Field(default=(), max_length=5)

    @model_validator(mode="after")
    def validate_binding(self) -> ObserverRequirementBinding:
        if len(set(self.phases)) != len(self.phases):
            raise ValueError("observer binding phases must be unique")
        allowed = {
            ObservationPhase.BASELINE,
            ObservationPhase.BEFORE,
            ObservationPhase.AFTER,
            ObservationPhase.EVENTUAL,
        }
        if any(phase not in allowed for phase in self.phases):
            raise ValueError(
                "Runner observer binding phases must be BASELINE, BEFORE, AFTER, or EVENTUAL"
            )
        if self.observer_id is None or self.observer_type is None or not self.phases:
            raise ValueError(
                "OBSERVER_SPEC binding requires an observer and phase window"
            )
        if self.credential_ref is not None and self.identity_id is not None:
            raise ValueError(
                "observer binding must use either a credential ref or a prepared identity"
            )
        return self
