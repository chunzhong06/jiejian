# 控制面统一成功响应。

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse


def data_response(value: Any, *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"schema_version": "1", "data": value},
    )
