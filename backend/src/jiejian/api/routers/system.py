# =============================================================================
# System API Router
#
# 定位
#   控制面进程存活与依赖就绪状态的 HTTP 观察边界
#
# 职责
#   返回健康状态｜核对存储和 Worker 就绪｜保持探针无目标副作用
#
# 调用链
#   FastAPI → system router → Storage / LocalWorkerManager
# =============================================================================

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ...application.context import ApplicationContext
from ...runtime.worker_manager import LocalWorkerManager
from ...runtime.diagnostics import browser_availability
from ...errors import ErrorCode, JiejianError
from ...storage import default_database_path
from ..schemas.common import ApiResponse, HealthResponse, ReadyResponse
from ..responses import data_response


def build_system_router(
    context: ApplicationContext, workers: LocalWorkerManager
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

    @router.get("/api/v1/system/status", response_model=ApiResponse)
    def status() -> JSONResponse:
        return data_response(
            {
                "api": "available",
                "worker": "running" if workers.is_running() else "stopped",
                "browser": browser_availability(),
            }
        )

    return router
