"""Permission Execution Profile V2 控制面请求 DTO。"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field

from .common import ApiModel


class PermissionExecutionProfileCreateRequest(ApiModel):
    schema_version: Literal["2"] = "2"
    path: str = Field(min_length=1, max_length=2048)
    revalidate: bool = False


class PermissionExecutionRunRequest(ApiModel):
    schema_version: Literal["2"] = "2"
    profile_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    idempotency_key: str = Field(min_length=1, max_length=128)
    max_attempts: int = Field(default=3, ge=1, le=1000)
