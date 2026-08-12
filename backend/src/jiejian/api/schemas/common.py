# 控制面通用请求和响应模型。

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    schema_version: Literal["1"] = "1"


class ApiResponse(ApiModel):
    data: Any


class HealthResponse(ApiModel):
    status: Literal["ok"]


class ReadyResponse(ApiModel):
    status: Literal["ready"]
    worker: Literal["running", "stopped"]
