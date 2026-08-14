# =============================================================================
# FastAPI 控制面组合入口
#
# 定位
#   稳定 create_app 入口与各能力 Router、生命周期资源之间的装配边界
#
# 职责
#   创建 ApplicationContext｜注册 Router 和异常映射｜管理本地 Worker 生命周期
#
# 调用链
#   jiejian.api:create_app → FastAPI app → capability routers / LocalWorkerManager
# =============================================================================

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from ..application.context import ApplicationContext
from ..runtime.worker_manager import LocalWorkerManager
from ..errors import JiejianError
from .errors import (
    jiejian_error_handler,
    request_validation_error_handler,
    validation_error_handler,
)
from .routers.contracts import build_contracts_router
from .routers.jobs import build_jobs_router
from .routers.llm import build_llm_router
from .routers.onboarding import build_onboarding_router
from .routers.projects import build_projects_router
from .routers.permission_execution import build_permission_execution_router
from .routers.recordings import build_recordings_router
from .routers.results import build_results_router
from .routers.runs import build_runs_router
from .routers.system import build_system_router


def create_app(
    var_dir: Path = Path("var"),
    *,
    frontend_dir: Path | None = None,
    start_worker: bool = True,
    llm_transport=None,
    llm_secret_store=None,
    environ=None,
    clock_us=None,
    folder_selector=None,
) -> FastAPI:
    context = ApplicationContext(
        var_dir,
        llm_transport=llm_transport,
        llm_secret_store=llm_secret_store,
        environ=environ,
        clock_us=clock_us,
        folder_selector=folder_selector,
    )
    workers = LocalWorkerManager(
        context.var_dir,
        context.uow_factory,
        context.job_queue,
        environment_provider=context.environment_for_secret_names,
    )
    results = context.results
    app = FastAPI(title="界鉴本地控制面", version="0.1.0")
    app.state.context = context
    app.state.worker_manager = workers
    app.state.results = results
    app.state.frontend_dir = frontend_dir.resolve() if frontend_dir else None

    @app.middleware("http")
    async def trace_middleware(request: Request, call_next):
        trace_id = request.headers.get("x-trace-id") or f"tr_{uuid4().hex}"
        request.state.trace_id = trace_id
        response = await call_next(request)
        response.headers["x-trace-id"] = trace_id
        return response

    app.add_exception_handler(JiejianError, jiejian_error_handler)
    app.add_exception_handler(
        RequestValidationError, request_validation_error_handler
    )
    app.add_exception_handler(ValidationError, validation_error_handler)

    app.include_router(build_system_router(context, workers))
    app.include_router(build_projects_router(context))
    app.include_router(build_permission_execution_router(context))
    app.include_router(build_contracts_router(context))
    app.include_router(build_recordings_router(context))
    app.include_router(build_runs_router(context, results))
    app.include_router(build_jobs_router(context))
    app.include_router(build_llm_router(context))
    app.include_router(build_onboarding_router(context))
    app.include_router(build_results_router(context, results))

    @app.on_event("startup")
    async def startup() -> None:
        if start_worker:
            workers.start()

    @app.on_event("shutdown")
    async def shutdown() -> None:
        workers.stop()
        context.close()

    if app.state.frontend_dir is not None and app.state.frontend_dir.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=app.state.frontend_dir, html=True),
            name="frontend",
        )

    return app
