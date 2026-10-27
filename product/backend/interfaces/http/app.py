# FastAPI 控制面组合入口
# 装配 ApplicationCore、Router、异常映射和本地控制面生命周期；不承载领域判断。

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
import logging
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from product.backend.interfaces.http.frontend import ProductStaticFiles
from pydantic import ValidationError

from product.backend import __version__
from product.backend.bootstrap import ApplicationCore
from product.backend.domain.errors import JiejianError
from product.backend.interfaces.http.errors import jiejian_error_handler, validation_error_handler
from product.backend.interfaces.http.routers.applications.onboarding import build_onboarding_router
from product.backend.interfaces.http.routers.applications.projects import build_projects_router
from product.backend.interfaces.http.routers.system.system import build_system_router
from product.backend.interfaces.http.routers.preparation.test_identities import build_test_identities_router
from product.backend.interfaces.http.routers.boundaries.business_boundaries import build_business_boundaries_router
from product.backend.interfaces.http.routers.applications.experience import build_experience_router
from product.backend.interfaces.http.routers.preparation.supplemental_materials import build_supplemental_material_router
from product.backend.interfaces.http.routers.system.mcp_access import build_mcp_access_router
from product.backend.interfaces.http.routers.workspace import build_workspace_router
from product.backend.interfaces.http.routers.preparation.recordings import build_recordings_router
from product.backend.interfaces.http.routers.preparation.preparation import build_preparation_router
from product.backend.interfaces.http.routers.system.agent_workflow import build_agent_workflow_router
from product.backend.interfaces.http.routers.checks.checks import build_checks_router
from product.backend.interfaces.http.routers.checks.runs import build_runs_router
from product.backend.interfaces.http.routers.checks.results import build_results_router
from product.backend.interfaces.http.routers.changes.source_changes import build_source_changes_router
from product.backend.interfaces.http.routers.changes.development import build_development_router
from product.backend.interfaces.http.local_control import LocalControlGuard
from product.backend.interfaces.http.mcp import build_mcp_control
from product.backend.application.agent_access.service import MCPAccessController


logger = logging.getLogger("jiejian.api.startup")


def create_app(
    var_dir: Path = Path("var"),
    *,
    control_origin: str,
    control_session_token: str | None = None,
    frontend_dir: Path | None = None,
    start_worker: bool = True,
    secret_store=None,
    environ=None,
    clock_us=None,
    folder_selector=None,
    shutdown_callback=None,
    official_sample_root: Path | None = None,
) -> FastAPI:
    local_control_guard = LocalControlGuard(
        control_origin,
        session_token=control_session_token,
    )
    context = ApplicationCore(
        var_dir,
        control_origin=local_control_guard.origin,
        secret_store=secret_store,
        environ=environ,
        clock_us=clock_us,
        folder_selector=folder_selector,
        official_sample_root=official_sample_root,
    )
    mcp_access = MCPAccessController(
        f"{local_control_guard.origin}/mcp",
        context.secret_store,
        clock_us=clock_us,
        on_authority_changed=context.proof_preparation.cancel_unauthorized,
    )
    context.proof_preparation.bind_authority_checker(lambda project, authority: (
        authority == 'LOCAL_GUI' or mcp_access.execution_authority_active(project,authority)))
    mcp_control = build_mcp_control(
        context,
        mcp_access,
        control_origin=local_control_guard.origin,
        control_host=local_control_guard.host,
        frontend_dir=frontend_dir,
    )
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async def finish_maintenance():
            maintenance = getattr(app.state, 'local_maintenance_task', None)
            if maintenance is not None:
                await maintenance

        async def finish_batches():
            if hasattr(app.state, 'batch_coordinator'):
                app.state.batch_stop.set()
                context.preparation_batches.wake.set()
                await app.state.batch_coordinator

        async with AsyncExitStack() as cleanup:
            cleanup.callback(context.close)
            cleanup.push_async_callback(finish_maintenance)
            await cleanup.enter_async_context(mcp_control.server.session_manager.run())
            cleanup.callback(mcp_access.close)
            cleanup.push_async_callback(asyncio.to_thread, context.runtime_worker.stop)
            cleanup.push_async_callback(asyncio.to_thread, context.official_experience.close)
            cleanup.push_async_callback(asyncio.to_thread, context.worker.stop)
            cleanup.push_async_callback(finish_batches)
            ready_started = perf_counter()
            if start_worker:
                context.worker.start()
                context.runtime_worker.start()
                app.state.batch_stop = asyncio.Event()
                app.state.batch_coordinator = asyncio.create_task(
                    _advance_preparation_batches(context, app.state.batch_stop)
                )
            _log_startup_timing('ready_total', ready_started)
            app.state.local_maintenance_task = asyncio.create_task(_run_local_maintenance(context, app))
            yield

    app = FastAPI(title="界鉴本地控制面", version=__version__, lifespan=lifespan)
    app.state.context = context
    app.state.frontend_dir = frontend_dir.resolve() if frontend_dir else None
    app.state.local_control_guard = local_control_guard
    app.state.mcp_access = mcp_access
    app.state.mcp_server = mcp_control.server
    app.state.mcp_app = mcp_control.app

    @app.middleware("http")
    async def local_control_middleware(request: Request, call_next):
        """先建立 trace，再统一执行 Host、会话和写请求同源校验。"""

        trace_id = request.headers.get("x-trace-id") or f"tr_{uuid4().hex}"
        request.state.trace_id = trace_id
        decision = app.state.local_control_guard.authorize(request)
        if decision.allowed:
            response = await call_next(request)
            if decision.issue_session and response.status_code < 400:
                app.state.local_control_guard.issue_session_cookie(response)
        else:
            response = app.state.local_control_guard.rejected_response(trace_id)
        response.headers["x-trace-id"] = trace_id
        return response

    app.add_exception_handler(JiejianError, jiejian_error_handler)
    app.add_exception_handler(
        RequestValidationError, validation_error_handler
    )
    app.add_exception_handler(ValidationError, validation_error_handler)

    app.include_router(build_system_router(context, shutdown_callback=shutdown_callback))
    app.include_router(build_projects_router(context))
    app.include_router(build_business_boundaries_router(context))
    app.include_router(build_workspace_router(context))
    app.include_router(build_experience_router(context))
    app.include_router(build_supplemental_material_router(context))
    app.include_router(build_test_identities_router(context))
    app.include_router(build_recordings_router(context))
    app.include_router(build_preparation_router(context))
    app.include_router(build_agent_workflow_router(context))
    app.include_router(build_checks_router(context))
    app.include_router(build_runs_router(context))
    app.include_router(build_results_router(context))
    app.include_router(build_source_changes_router(context))
    app.include_router(build_development_router(context))
    from product.backend.application.agent_access.connections import AgentConnections
    app.state.agent_connections = AgentConnections(var_dir, mcp_access)
    app.include_router(build_mcp_access_router(context, mcp_access, app.state.agent_connections))
    app.include_router(build_onboarding_router(context))

    app.add_route(
        "/mcp",
        mcp_control.app,
        methods=["GET", "POST", "DELETE"],
        name="mcp",
    )

    if app.state.frontend_dir is not None and app.state.frontend_dir.is_dir():
        app.mount(
            "/",
            ProductStaticFiles(directory=app.state.frontend_dir, html=True),
            name="frontend",
        )

    return app


def _log_startup_timing(stage: str, started: float) -> None:
    logger.info(
        "startup stage completed",
        extra={
            "component": "api_startup",
            "event_code": "STARTUP_STAGE_COMPLETED",
            "stage": stage,
            "elapsed_ms": round((perf_counter() - started) * 1_000, 3),
        },
    )


async def _advance_preparation_batches(context, stopped):
    """有限后台编排只推进已确认批次；访问目标的子操作沿用原Worker边界。"""
    while not stopped.is_set():
        try:
            await asyncio.to_thread(context.preparation_batches.advance)
        except Exception:
            # 短暂存储读取失败不能终止整个协调器；下一轮仍先读取持久进度，绝不重放未知写入。
            logger.warning('preparation batch coordinator read failed')
        if not stopped.is_set():
            await asyncio.to_thread(context.preparation_batches.wait_for_work)


async def _run_local_maintenance(context: ApplicationCore, app: FastAPI) -> None:
    """维护失败只写诊断事实，不反向撤销已经成立的服务 readiness。"""

    started = perf_counter()
    try:
        app.state.startup_maintenance = await asyncio.to_thread(
            context.maintenance.startup_maintenance
        )
        _log_startup_timing("startup_maintenance", started)
    except Exception:
        app.state.startup_maintenance = {"status": "failed"}
        logger.exception(
            "startup local maintenance failed",
            extra={
                "component": "api_startup",
                "event_code": "STARTUP_MAINTENANCE_FAILED",
                "stage": "startup_maintenance",
                "elapsed_ms": round((perf_counter() - started) * 1_000, 3),
            },
        )
