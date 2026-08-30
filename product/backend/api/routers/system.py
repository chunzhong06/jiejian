# System API Router
# 提供控制面存活与依赖就绪探针；检查不得触发目标请求或其他业务副作用。

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from product.backend import __version__
from product.backend.workflows.context import ApplicationCore
from product.backend.infra.runtime.worker.supervisor import LocalWorkerSupervisor
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
                "version": __version__,
                "api": "available",
                "worker": "running" if workers.is_running() else "stopped",
                "browser": environment["playwright"]["status"],
                "environment": environment,
                "recovered_jobs": workers.recovered_jobs,
            }
        )

    @router.get("/api/system/maintenance", response_model=ApiResponse)
    def maintenance_status() -> JSONResponse:
        """读取三类可清理统计与永不进入普通清理的受保护摘要。"""

        try:
            return data_response(context.maintenance.status())
        except JiejianError:
            raise
        except Exception:
            raise JiejianError(
                ErrorCode.LOCAL_MAINTENANCE_FAILED,
                "本地运行数据状态读取失败",
            ) from None

    @router.post("/api/system/maintenance/{operation}", response_model=ApiResponse)
    def maintenance_operation(
        operation: Literal[
            "clear-assistant-cache",
            "clear-logs",
            "clear-temporary",
            "clear-all",
            "repair-runtime",
        ],
        body: MaintenanceOperationRequest,
    ) -> JSONResponse:
        """预览冻结计划；确认时只执行同一 plan_id 中的候选。"""

        try:
            if body.confirmed and not body.dry_run:
                if body.plan_id is None:
                    raise JiejianError(
                        ErrorCode.INPUT_INVALID,
                        "确认维护操作需要预览返回的 plan_id",
                    )
                result = context.maintenance.execute(
                    body.plan_id,
                    expected_scope=operation,
                )
            elif not body.confirmed and body.dry_run:
                result = context.maintenance.preview(operation)
            else:
                raise JiejianError(
                    ErrorCode.INPUT_INVALID,
                    "本地维护操作状态无效",
                )
            return data_response(result)
        except JiejianError:
            raise
        except Exception:
            raise JiejianError(
                ErrorCode.LOCAL_MAINTENANCE_FAILED,
                "本地运行数据维护失败",
            ) from None

    @router.post("/api/system/shutdown", response_model=ApiResponse, status_code=202)
    def shutdown() -> JSONResponse:
        """复用全局本地控制会话触发同一安全退出链。"""

        if shutdown_callback is None:
            raise JiejianError(ErrorCode.SERVE_FAILED, "当前服务未配置网页退出能力")
        shutdown_callback()
        return data_response(
            {
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


class MaintenanceOperationRequest(ApiModel):
    schema_version: Literal["1"]
    confirmed: bool = False
    dry_run: bool = True
    plan_id: str | None = None
