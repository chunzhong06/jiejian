"""检查方案在冻结运行中的准确引用；不复制方案或环境材料正文。"""
from pydantic import BaseModel, ConfigDict, Field


class RoutineReference(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True, hide_input_in_errors=True)
    routine_id: str = Field(pattern=r'^csp_[0-9a-f]{32}$')
    revision: int = Field(ge=1)
    binding_id: str = Field(pattern=r'^crb_[0-9a-f]{32}$')


class FrozenRoutineReference(RoutineReference):
    routine_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    binding_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')

