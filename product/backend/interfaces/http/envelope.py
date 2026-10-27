# 控制面统一的模型与成功响应边界。

from __future__ import annotations

from typing import Any, Literal

from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class ApiResponse(ApiModel):
    schema_version: Literal["1"] = "1"
    data: Any


def data_response(value: Any, *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"schema_version": "1", "data": value},
    )
