# System API Router
# 提供控制面存活与依赖就绪探针；检查不得触发目标请求或其他业务副作用。

from __future__ import annotations

from typing import Literal
from typing import Annotated
from pydantic import Field

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from product.backend import __version__
from product.backend.bootstrap import ApplicationCore
from product.backend.infrastructure.runtime.diagnostics import runtime_environment_details
from product.backend.infrastructure.runtime.frontend_assets import frontend_asset_identity
from product.backend.infrastructure.runtime.system_status import SystemRuntimeView
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.infrastructure.storage import default_database_path
from product.backend.interfaces.http.envelope import ApiResponse, data_response


def build_system_router(
    context: ApplicationCore,
    *,
    shutdown_callback=None,
) -> APIRouter:
    router = APIRouter()
    runtime_view = SystemRuntimeView(None, context.worker_status)

    @router.get('/api/system/summary', response_model=ApiResponse)
    def summary() -> JSONResponse:
        return data_response(runtime_view.summary())

    @router.get('/api/system/diagnostics', response_model=ApiResponse)
    def diagnostics(request: Request) -> JSONResponse:
        runtime_view.frontend_dir = getattr(request.app.state, 'frontend_dir', None)
        return data_response({**runtime_view.inspect(), 'last_exit': context.updates.last_exit()})

    @router.post('/api/system/diagnostics', response_model=ApiResponse)
    def refresh_diagnostics(request: Request) -> JSONResponse:
        runtime_view.frontend_dir = getattr(request.app.state, 'frontend_dir', None)
        return data_response({**runtime_view.inspect(refresh=True), 'last_exit': context.updates.last_exit()})

    @router.get("/health", operation_id="health", response_model=HealthResponse)
    async def health() -> dict[str, str]:
        return {"schema_version": "1", "status": "ok"}

    @router.get("/ready", operation_id="ready", response_model=ReadyResponse)
    def ready() -> dict[str, object]:
        database = default_database_path(context.var_dir)
        if not database.is_file():
            raise JiejianError(ErrorCode.API_NOT_READY, "数据库尚未准备完成")
        if context.worker_status()['worker'] == 'running':
            context.updates.ready()
        return {
            "schema_version": "1",
            "status": "ready",
            **context.worker_status(),
        }

    @router.get("/api/system/status", response_model=ApiResponse)
    def status(request: Request) -> JSONResponse:
        environment = runtime_environment_details()
        return data_response(
            {
                "version": __version__,
                "api": "available",
                **context.worker_status(),
                "browser": environment["playwright"]["status"],
                "environment": environment,
                "frontend_identity": frontend_asset_identity(getattr(request.app.state, 'frontend_dir', None)),
            }
        )

    @router.get('/api/system/updates', response_model=ApiResponse)
    def update_info() -> JSONResponse:
        return data_response(context.updates.info())

    @router.post('/api/system/updates/preview', response_model=ApiResponse)
    def update_preview(body: UpdatePreviewRequest) -> JSONResponse:
        return data_response(context.updates.preview(body.directory, body.return_path))

    @router.get('/api/system/updates/{operation_id}', response_model=ApiResponse)
    def update_outcome(operation_id: str) -> JSONResponse:
        return data_response(context.updates.read(operation_id).model_dump(mode='json'))

    @router.post('/api/system/updates/{operation_id}/confirm', response_model=ApiResponse, status_code=202)
    def update_confirm(operation_id: str) -> JSONResponse:
        if shutdown_callback is None:
            raise JiejianError(ErrorCode.SERVE_FAILED, '当前服务未配置发行交接能力')
        result = context.updates.confirm(operation_id)
        if result['phase'] == 'WAITING_FOR_EXIT':
            shutdown_callback()
        return data_response(result, status_code=202)

    @router.get("/api/system/maintenance", response_model=ApiResponse)
    def maintenance_status() -> JSONResponse:
        """读取已登记运行生成物、活动引用保护及无法确认的来源，不扫描业务资料。"""

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
                    item_ids=body.item_ids,
                )
            elif not body.confirmed and body.dry_run:
                if body.item_ids is not None:
                    raise JiejianError(ErrorCode.INPUT_INVALID, "请先读取完整清理预览，再选择项目")
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

    @router.get("/api/system/maintenance/plans/{plan_id}", response_model=ApiResponse)
    def maintenance_outcome(plan_id: str) -> JSONResponse:
        """只读回查未知清理回执；查询绝不再次执行删除。"""
        return data_response(context.maintenance.outcome(plan_id))

    @router.post('/api/system/maintenance/plans/{plan_id}/review', response_model=ApiResponse)
    def review_maintenance_interruption(plan_id: str) -> JSONResponse:
        return data_response(context.maintenance.review_interruption(plan_id))

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

from product.backend.interfaces.http.envelope import ApiModel


class HealthResponse(ApiModel):
    schema_version: Literal["1"] = "1"
    status: Literal["ok"]


class ReadyResponse(ApiModel):
    schema_version: Literal["1"] = "1"
    status: Literal["ready"]
    worker: Literal["running", "stopped", "unavailable"]
    worker_capabilities: tuple[
        Literal["CHECK", "RECORDING", "PROOF_PREFLIGHT", "REFERENCE_CAPTURE", "IDENTITY_PREPARATION"], ...
    ]
    check: Literal["available", "unavailable"]
    recovered_jobs: int


class MaintenanceOperationRequest(ApiModel):
    schema_version: Literal["1"]
    confirmed: bool = False
    dry_run: bool = True
    plan_id: str | None = Field(default=None, min_length=1, max_length=128)
    item_ids: list[Annotated[str, Field(min_length=1, max_length=128)]] | None = Field(default=None, min_length=1, max_length=10000)


class UpdatePreviewRequest(ApiModel):
    directory: str = Field(min_length=1, max_length=4096)
    return_path: str = Field(default='/workspace', max_length=256)
