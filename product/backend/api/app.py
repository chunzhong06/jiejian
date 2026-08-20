# FastAPI 控制面组合入口
# 装配 ApplicationCore、Router、异常映射和本地 Worker 生命周期；不承载领域判断。

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from product.backend.workflows.context import ApplicationCore
from product.backend.infra.runtime.worker_supervisor import LocalWorkerSupervisor
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
    context = ApplicationCore(
        var_dir,
        llm_transport=llm_transport,
        llm_secret_store=llm_secret_store,
        environ=environ,
        clock_us=clock_us,
        folder_selector=folder_selector,
    )
    workers = LocalWorkerSupervisor(
        context.var_dir,
        context.uow_factory,
        context.job_queue,
        attempt_service=context.job_attempts,
        environment_provider=context.environment_for_secret_names,
        clock_us=clock_us,
    )
    results = context.results
    app = FastAPI(title="界鉴本地控制面", version="0.1.0")
    app.state.context = context
    app.state.worker_supervisor = workers
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
