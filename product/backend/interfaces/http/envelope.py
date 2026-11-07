# 控制面统一的模型与成功响应边界。

from __future__ import annotations

from typing import Any, Literal, Generic, TypeVar

from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


ResponseData = TypeVar("ResponseData")


class ApiResponse(ApiModel, Generic[ResponseData]):
    schema_version: Literal["1"] = "1"
    data: ResponseData


def data_response(value: Any, *, status_code: int = 200, projection: type[BaseModel] | None = None) -> JSONResponse:
    response = JSONResponse(
        status_code=status_code,
        content={"schema_version": "1", "data": jsonable_encoder(value)},
    )

    if projection is not None and not isinstance(value, projection):
        # 所属边界已返回准确投影模型时直接编码；动态映射才接受同一份字节，避免重新解析合法模型。
        # 直接返回Response会绕过FastAPI的response_model校验，不能只声明类型而放过动态输出。
        ApiResponse[projection].model_validate_json(response.body)
    return response
