# FastAPI 控制面组合入口
# 装配 ApplicationCore、Router、异常映射和本地 Worker 生命周期；不承载领域判断。

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
from product.backend.workflows.context import ApplicationCore
from product.backend.infra.runtime.worker.supervisor import LocalWorkerSupervisor
from product.backend.core.errors import JiejianError
from product.backend.api.errors import jiejian_error_handler, request_validation_error_handler, validation_error_handler
from product.backend.api.routers.contracts import build_contracts_router
from product.backend.api.routers.jobs import build_jobs_router
from product.backend.api.routers.llm import build_llm_router
from product.backend.api.routers.onboarding import build_onboarding_router
from product.backend.api.routers.projects import build_projects_router
from product.backend.api.routers.execution_profiles import build_execution_profiles_router
from product.backend.api.routers.recordings import build_recordings_router
from product.backend.api.routers.results import build_results_router
from product.backend.api.routers.gating import build_gating_router
from product.backend.api.routers.runs import build_runs_router
from product.backend.api.routers.system import build_system_router
from product.backend.api.routers.test_identities import build_test_identities_router
from product.backend.api.routers.permission_intents import build_permission_intents_router
from product.backend.api.routers.checks import build_checks_router
from product.backend.api.routers.assistant import build_assistant_router
from product.backend.api.routers.experience import build_experience_router
from product.backend.api.routers.mcp_access import build_mcp_access_router
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
    workers = LocalWorkerSupervisor(
        context.var_dir,
        context.uow_factory,
        context.job_queue,
        attempt_service=context.job_attempts,
        environment_provider=context.environment_for_secret_names,
        clock_us=clock_us,
    )
    mcp_access = MCPAccessController(
        f"{local_control_guard.origin}/mcp",
        context.secret_store,
        clock_us=clock_us,
    )
    mcp_control = build_mcp_control(
        context,
        workers,
        mcp_access,
        control_origin=local_control_guard.origin,
        control_host=local_control_guard.host,
    )
    results = context.results
    app = FastAPI(title="界鉴本地控制面", version=__version__)
    app.state.context = context
    app.state.worker_supervisor = workers
    app.state.results = results
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

    app.include_router(build_system_router(context, workers, shutdown_callback=shutdown_callback))
    app.include_router(build_projects_router(context))
    app.include_router(build_test_identities_router(context))
    app.include_router(build_permission_intents_router(context))
    app.include_router(build_checks_router(context))
    app.include_router(build_assistant_router(context))
    app.include_router(build_experience_router(context))
    app.include_router(build_mcp_access_router(context, mcp_access))
    app.include_router(build_execution_profiles_router(context))
    app.include_router(build_contracts_router(context))
    app.include_router(build_recordings_router(context))
    app.include_router(build_runs_router(context, results))
    app.include_router(build_jobs_router(context))
    app.include_router(build_llm_router(context))
    app.include_router(build_onboarding_router(context))
    app.include_router(build_results_router(context, results))
    app.include_router(build_gating_router(context))

    @app.on_event("startup")
    async def startup() -> None:
        from product.backend.infra.artifacts.run_publication import RunPublisher
        from product.backend.infra.runtime.jobs.reconciliation import RunReconciler

        ready_started = perf_counter()
        app.state.mcp_lifespan = mcp_control.server.session_manager.run()
        await app.state.mcp_lifespan.__aenter__()
        stage_started = perf_counter()
        reconciliation = RunReconciler(
            context.var_dir,
            context.uow_factory,
            RunPublisher(context.var_dir, context.uow_factory),
        ).reconcile()
        app.state.startup_reconciliation = reconciliation
        _log_startup_timing("run_reconciliation", stage_started)
        # 派生结果按项目顺序恢复；页面读取依赖该顺序边界，因此继续留在 ready 前。
        stage_started = perf_counter()
        app.state.startup_finalization = context.result_finalizer.reconcile()
        _log_startup_timing("result_finalization", stage_started)
        if start_worker:
            stage_started = perf_counter()
            workers.start()
            _log_startup_timing("worker_start", stage_started)
        _log_startup_timing("ready_total", ready_started)
        # 可重建运行数据维护不属于产品可用性的前置条件，放到 ready 后的受控后台线程。
        app.state.local_maintenance_task = asyncio.create_task(
            _run_local_maintenance(context, app)
        )

    @app.on_event("shutdown")
    async def shutdown() -> None:
        mcp_access.close()
        workers.stop()
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
