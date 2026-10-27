# 共享本机 Human Approval 事实；审批入口身份由服务端固定，模型不承载传输来源。

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class HumanApprovalChannel(StrEnum):
    LOCAL_GUI = "LOCAL_GUI"


class HumanApproval(BaseModel):
    """记录一次已完成的人类批准；当前版本只接受本机 GUI 用户。"""

    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, hide_input_in_errors=True
    )

    channel: HumanApprovalChannel
    approved_by: str = Field(min_length=1, max_length=128)
    approved_at_us: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=512)

    @field_validator("approved_by", "reason")
    @classmethod
    def validate_text(cls, value: str, info) -> str:
        if value != value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError(f"{info.field_name} must be trimmed printable text")
        return value

    @model_validator(mode="after")
    def validate_local_user(self) -> HumanApproval:
        if self.channel is not HumanApprovalChannel.LOCAL_GUI:
            raise ValueError("human approval must originate from LOCAL_GUI")
        if self.approved_by != "本机界鉴用户":
            raise ValueError("human approval identity is server controlled")
        return self


__all__ = ["HumanApproval", "HumanApprovalChannel"]
