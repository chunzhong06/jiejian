# System API Router
# 提供控制面存活与依赖就绪探针；检查不得触发目标请求或其他业务副作用。

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from product.backend.workflows.context import ApplicationCore
from product.backend.infra.runtime.worker_supervisor import LocalWorkerSupervisor
from product.backend.infra.runtime.diagnostics import browser_availability
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage import default_database_path
from product.backend.api.envelope import ApiResponse, data_response


def build_system_router(
    context: ApplicationCore, workers: LocalWorkerSupervisor
) -> APIRouter:
    router = APIRouter()

    @router.get("/health", operation_id="health", response_model=HealthResponse)
    async def health() -> dict[str, str]:
        return {"schema_version": "1", "status": "ok"}

    @router.get("/ready", operation_id="ready", response_model=ReadyResponse)
    async def ready() -> dict[str, str]:
        database = default_database_path(context.var_dir)
        if not database.is_file():
            raise JiejianError(ErrorCode.API_NOT_READY, "数据库尚未准备完成")
        return {
            "schema_version": "1",
            "status": "ready",
            "worker": "running" if workers.is_running() else "stopped",
        }

    @router.get("/api/system/status", response_model=ApiResponse)
    def status() -> JSONResponse:
        return data_response(
            {
                "api": "available",
                "worker": "running" if workers.is_running() else "stopped",
                "browser": browser_availability(),
            }
        )

    return router

# 系统健康与就绪响应模型。

from typing import Literal

from product.backend.api.envelope import ApiModel


class HealthResponse(ApiModel):
    status: Literal["ok"]


class ReadyResponse(ApiModel):
    status: Literal["ready"]
    worker: Literal["running", "stopped"]
