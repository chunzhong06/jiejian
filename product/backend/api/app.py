# FastAPI 控制面组合入口
# 装配 ApplicationCore、Router、异常映射和本地控制面生命周期；不承载领域判断。

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from product.backend import __version__
from product.backend.composition import ApplicationCore
from product.backend.core.errors import JiejianError
from product.backend.api.errors import jiejian_error_handler, request_validation_error_handler, validation_error_handler
from product.backend.api.routers.llm import build_llm_router
from product.backend.api.routers.onboarding import build_onboarding_router
from product.backend.api.routers.projects import build_projects_router
from product.backend.api.routers.system import build_system_router
from product.backend.api.routers.test_identities import build_test_identities_router
from product.backend.api.routers.business_boundaries import build_business_boundaries_router
from product.backend.api.routers.current_experience import build_current_experience_router
from product.backend.api.routers.mcp_access import build_mcp_access_router
from product.backend.api.routers.workspace import build_workspace_router
from product.backend.api.local_control import LocalControlGuard
from product.backend.api.mcp import build_mcp_control
from product.backend.workflows.mcp_access import MCPAccessController


logger = logging.getLogger("jiejian.api.startup")


def create_app(
    var_dir: Path = Path("var"),
    *,
    control_origin: str,
    control_session_token: str | None = None,
    frontend_dir: Path | None = None,
    start_worker: bool = True,
    llm_transport=None,
    llm_secret_store=None,
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
        llm_transport=llm_transport,
        llm_secret_store=llm_secret_store,
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
    )
    mcp_control = build_mcp_control(
        context,
        mcp_access,
        control_origin=local_control_guard.origin,
        control_host=local_control_guard.host,
    )
    app = FastAPI(title="界鉴本地控制面", version=__version__)
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
        RequestValidationError, request_validation_error_handler
    )
    app.add_exception_handler(ValidationError, validation_error_handler)

    app.include_router(build_system_router(context, shutdown_callback=shutdown_callback))
    app.include_router(build_projects_router(context))
    app.include_router(build_business_boundaries_router(context))
    app.include_router(build_workspace_router(context))
    app.include_router(build_current_experience_router())
    app.include_router(build_test_identities_router(context))
    app.include_router(build_mcp_access_router(context, mcp_access))
    app.include_router(build_llm_router(context))
    app.include_router(build_onboarding_router(context))

    @app.on_event("startup")
    async def startup() -> None:
        ready_started = perf_counter()
        app.state.mcp_lifespan = mcp_control.server.session_manager.run()
        await app.state.mcp_lifespan.__aenter__()
        if start_worker:
            context.worker.start()
        _log_startup_timing("ready_total", ready_started)
        # 可重建运行数据维护不属于产品可用性的前置条件，放到 ready 后的受控后台线程。
        app.state.local_maintenance_task = asyncio.create_task(
            _run_local_maintenance(context, app)
        )

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await asyncio.to_thread(context.worker.stop)
        mcp_access.close()
        mcp_lifespan = getattr(app.state, "mcp_lifespan", None)
        if mcp_lifespan is not None:
            await mcp_lifespan.__aexit__(None, None, None)
        maintenance = getattr(app.state, "local_maintenance_task", None)
        if maintenance is not None:
            await maintenance
        context.close()

    app.add_route(
        "/mcp",
        mcp_control.app,
        methods=["GET", "POST", "DELETE"],
        name="mcp",
    )

    if app.state.frontend_dir is not None and app.state.frontend_dir.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=app.state.frontend_dir, html=True),
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
