# System API Router
# 提供控制面存活与依赖就绪探针；检查不得触发目标请求或其他业务副作用。

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from product.backend.workflows.context import ApplicationCore
from product.backend.infra.runtime.worker_supervisor import LocalWorkerSupervisor
from product.backend.infra.runtime.diagnostics import runtime_environment_details
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage import default_database_path
from product.backend.api.envelope import ApiResponse, data_response


def build_system_router(
    context: ApplicationCore,
    workers: LocalWorkerSupervisor,
    *,
    shutdown_callback=None,
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
        environment = runtime_environment_details()
        return data_response(
            {
                "api": "available",
                "worker": "running" if workers.is_running() else "stopped",
                "browser": environment["playwright"]["status"],
                "environment": environment,
                "recovered_jobs": workers.recovered_jobs,
            }
        )

    @router.get("/api/system/cache", response_model=ApiResponse)
    def cache_status() -> JSONResponse:
        """只读取同一缓存服务的状态，不遍历或删除 data。"""

        return data_response(context.cache.status())

    @router.post("/api/system/cache/{operation}", response_model=ApiResponse)
    def cache_operation(
        operation: Literal["prune", "clean", "runtime-repair"],
        body: CacheOperationRequest,
    ) -> JSONResponse:
        """统一执行 GUI/CLI 同语义的预览、确认和维护操作。"""

        if operation == "prune":
            result = context.cache.prune(dry_run=body.dry_run)
        elif operation == "clean":
            result = context.cache.clean(
                confirmed=body.confirmed,
                dry_run=body.dry_run,
            )
        else:
            result = context.cache.repair_runtime(
                confirmed=body.confirmed,
                dry_run=body.dry_run,
            )
        return data_response(result)

    @router.post("/api/system/shutdown", response_model=ApiResponse, status_code=202)
    def shutdown(
        x_jiejian_control: str | None = Header(default=None, alias="X-Jiejian-Control"),
    ) -> JSONResponse:
        """只接受带专用控制头的同源退出请求，避免简单跨站请求关闭服务。"""

        if x_jiejian_control != "shutdown":
            raise JiejianError(ErrorCode.INPUT_INVALID, "退出请求缺少本地控制确认")
        if shutdown_callback is None:
            raise JiejianError(ErrorCode.SERVE_FAILED, "当前服务未配置网页退出能力")
        shutdown_callback()
        return data_response(
            {
                "schema_version": "1",
                "status": "stopping",
                "message": "界鉴正在安全退出，完成后可关闭浏览器页面。",
            },
            status_code=202,
        )

    return router

# 系统健康与就绪响应模型。

from typing import Literal

from product.backend.api.envelope import ApiModel


class HealthResponse(ApiModel):
    schema_version: Literal["1"] = "1"
    status: Literal["ok"]


class ReadyResponse(ApiModel):
    schema_version: Literal["1"] = "1"
    status: Literal["ready"]
    worker: Literal["running", "stopped"]


class CacheOperationRequest(ApiModel):
    schema_version: Literal["1"]
    confirmed: bool = False
    dry_run: bool = True
