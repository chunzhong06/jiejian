# 登录准备的非秘密状态与页面回读合同。
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field


class IdentityPreparationStatus(StrEnum):
    STARTING = 'STARTING'
    WAITING_FOR_LOGIN = 'WAITING_FOR_LOGIN'
    SAVING = 'SAVING'
    CANCELLING = 'CANCELLING'
    PREPARED = 'PREPARED'
    UNSUPPORTED = 'UNSUPPORTED'
    CANCELLED = 'CANCELLED'
    FAILED = 'FAILED'


class IdentityPreparationView(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True, hide_input_in_errors=True)
    preparation_id: str = Field(pattern=r'^prep_[0-9a-f]{32}$')
    identity_id: str = Field(pattern=r'^tid_[0-9a-f]{32}$')
    status: IdentityPreparationStatus
    message: str = Field(min_length=1, max_length=256)
    error_code: str | None = Field(default=None, max_length=64)
    log_path: str = Field(default='', max_length=2048)
    project_id: str | None = None
    job_id: str | None = None
    cleanup_required: bool = False


PREPARATION_TERMINAL = frozenset({'PREPARED', 'UNSUPPORTED', 'CANCELLED', 'FAILED'})
