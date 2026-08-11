"""FastAPI 本地控制面；该模块不导入目标传输或 Playwright。"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from fastapi import FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from ..application.results import PublishedResultReader
from ..application.services import ApplicationContext, build_execution_request
from ..application.worker_manager import LocalWorkerManager
from ..domain.lifecycle import JobState, RunLifecycle
from ..domain.recording import RecordingState
from ..errors import ErrorCode, JiejianError
from ..protocols import (
    RecordingBudgetV1,
    RecordingRunnerRequestV1,
    RecordingSessionRefV1,
    parse_flow_draft_review_command,
)
from ..recording.application import RecordingApplicationService, SubmitRecordingV1
from ..recording.request_store import RecordingRequestStore
from ..recording.workflow import RecordingWorkflow
from ..redaction import redact
from ..storage import default_database_path
from ..worker import (
    ExecutionRequestStore,
    ExecutionSubmissionService,
    RequestCancellationV1,
    SubmitExecutionV1,
)
from .schemas import (
    ApiResponse,
    ContractActivateRequest,
    HealthResponse,
    ProjectRegisterRequest,
    RecordingCreateRequest,
    ReadyResponse,
    ReviewRequest,
    RunCreateRequest,
)


def create_app(
    var_dir: Path = Path("var"),
    *,
    frontend_dir: Path | None = None,
    start_worker: bool = True,
) -> FastAPI:
    context = ApplicationContext(var_dir)
    workers = LocalWorkerManager(context.var_dir, context.uow_factory)
    results = PublishedResultReader(context.var_dir, context.uow_factory)
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

    @app.exception_handler(JiejianError)
    async def jiejian_error_handler(request: Request, exc: JiejianError):
        return JSONResponse(status_code=_status_for(exc.code), content={"schema_version": "1", "error": exc.to_dict(), "trace_id": request.state.trace_id})

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(request: Request, exc: RequestValidationError):
        error = JiejianError(ErrorCode.INPUT_INVALID, "请求参数无效")
        return JSONResponse(status_code=422, content={"schema_version": "1", "error": error.to_dict(), "trace_id": request.state.trace_id})

    @app.exception_handler(ValidationError)
    async def validation_error_handler(request: Request, exc: ValidationError):
        error = JiejianError(ErrorCode.INPUT_INVALID, "请求参数无效")
        return JSONResponse(status_code=422, content={"schema_version": "1", "error": error.to_dict(), "trace_id": request.state.trace_id})

    @app.get("/health", operation_id="health", response_model=HealthResponse)
    async def health() -> dict[str, Any]:
        return {"schema_version": "1", "status": "ok"}

    @app.get("/ready", operation_id="ready", response_model=ReadyResponse)
    async def ready() -> dict[str, Any]:
        database = default_database_path(context.var_dir)
        if not database.is_file():
            raise JiejianError(ErrorCode.API_NOT_READY, "数据库尚未准备完成")
        return {"schema_version": "1", "status": "ready", "worker": "running" if workers.is_running() else "stopped"}

    @app.post("/api/v1/projects", response_model=ApiResponse)
    async def register_project(body: ProjectRegisterRequest):
        record, _ = context.projects.register(Path(body.path), revalidate=body.revalidate)
        return _data(record.model_dump(mode="json"))

    @app.get("/api/v1/projects", response_model=ApiResponse)
    async def list_projects():
        return _data([record.model_dump(mode="json") for record in context.projects.list()])

    @app.get("/api/v1/projects/{project_id}", response_model=ApiResponse)
    async def get_project(project_id: str):
        return _data(context.projects.get(project_id).model_dump(mode="json"))

    @app.post("/api/v1/projects/{project_id}/revalidate", response_model=ApiResponse)
    async def revalidate_project(project_id: str):
        record, _ = context.projects.revalidate(project_id)
        return _data(record.model_dump(mode="json"))

    @app.get("/api/v1/projects/{project_id}/contracts", response_model=ApiResponse)
    async def list_contracts(project_id: str):
        record = context.projects.get(project_id)
        if not record.active_contract_path:
            return _data([])
        contract = context.projects.current_bundle(project_id)[1].contract
        return _data([
            {
                "schema_version": "1",
                "path": record.active_contract_path,
                "hash": record.active_contract_hash,
                "status": contract.status.value,
                "id": contract.id,
                "version": contract.version,
                "rules": [item.model_dump(mode="json") for item in contract.rules],
            }
        ])

    @app.post("/api/v1/projects/{project_id}/contracts/activate", response_model=ApiResponse)
    async def activate_contract(project_id: str, body: ContractActivateRequest):
        record = context.projects.activate_contract(project_id, Path(body.path))
        return _data(record.model_dump(mode="json"))

    @app.post("/api/v1/projects/{project_id}/recordings", response_model=ApiResponse, status_code=202)
    async def create_recording(project_id: str, body: RecordingCreateRequest):
        record, bundle = context.projects.current_bundle(project_id)
        selected = tuple(body.identities) if body.identities else tuple(item.id for item in bundle.project.identities)
        known = {item.id for item in bundle.project.identities}
        if not selected or len(set(selected)) != len(selected) or any(item not in known for item in selected):
            raise JiejianError(ErrorCode.INPUT_INVALID, "录制身份选择无效")
        now_us = time.time_ns() // 1_000
        request = RecordingRunnerRequestV1(
            schema_version="1",
            recording_id=f"rec_{uuid4().hex}",
            project_id=project_id,
            created_at_us=now_us,
            target_scope=bundle.project.target,
            sessions=tuple(
                RecordingSessionRefV1(
                    schema_version="1",
                    identity_id=item,
                    session_ref=f"session_{uuid4().hex}",
                    expires_at_us=now_us + body.duration_seconds * 1_000_000,
                )
                for item in selected
            ),
            budget=RecordingBudgetV1(schema_version="1", max_duration_us=body.duration_seconds * 1_000_000, max_contexts=len(selected)),
            headless=body.headless,
            trace_enabled=False,
        )
        result = RecordingApplicationService(context.uow_factory, RecordingRequestStore(context.var_dir)).submit(
            SubmitRecordingV1(schema_version="1", request=request, flow_id=bundle.flow.id, idempotency_key=body.idempotency_key, now_us=now_us, available_at_us=now_us)
        )
        return _data({"job": result.job.model_dump(mode="json"), "recording": result.recording.model_dump(mode="json")}, status_code=202)

    @app.get("/api/v1/recordings/{recording_id}", response_model=ApiResponse)
    async def get_recording(recording_id: str):
        view = RecordingWorkflow(context.uow_factory).status(recording_id).model_dump(mode="json")
        with context.uow_factory() as work:
            job = work.jobs.get_by_recording(recording_id)
        view["job"] = job.model_dump(mode="json") if job else None
        return _data(view)

    @app.get("/api/v1/projects/{project_id}/recordings", response_model=ApiResponse)
    async def list_recordings(project_id: str):
        context.projects.get(project_id)
        with context.uow_factory() as work:
            return _data([
                {
                    **item.model_dump(mode="json"),
                    "job": (
                        job.model_dump(mode="json")
                        if (job := work.jobs.get_by_recording(item.recording_id))
                        else None
                    ),
                }
                for item in work.recordings.list_for_project(project_id)
            ])

    @app.post("/api/v1/recordings/{recording_id}/review", response_model=ApiResponse)
    async def review_recording(recording_id: str, body: ReviewRequest):
        command = parse_flow_draft_review_command(json.dumps(body.command, ensure_ascii=False).encode("utf-8"))
        view = RecordingWorkflow(context.uow_factory).review(recording_id, command, bindings=body.bindings)
        return _data(view.model_dump(mode="json"))

    @app.post("/api/v1/recordings/{recording_id}/finalize", response_model=ApiResponse)
    async def finalize_recording(recording_id: str):
        view = RecordingWorkflow(context.uow_factory).finalize(recording_id, var_dir=context.var_dir, now_us=time.time_ns() // 1_000)
        return _data(view.model_dump(mode="json"))

    @app.post("/api/v1/projects/{project_id}/runs", response_model=ApiResponse, status_code=202)
    async def create_run(project_id: str, body: RunCreateRequest):
        _, bundle = context.projects.current_bundle(project_id)
        request = build_execution_request(bundle)
        now_us = time.time_ns() // 1_000
        result = ExecutionSubmissionService(context.uow_factory, ExecutionRequestStore(context.var_dir)).submit(
            SubmitExecutionV1(schema_version="1", request=request, idempotency_key=body.idempotency_key, now_us=now_us, available_at_us=now_us),
            known_secrets=tuple(os.environ.get(item.secret_ref.removeprefix("env:"), "") for item in bundle.project.identities),
        )
        return _data({"job": result.job.model_dump(mode="json"), "run": result.run.model_dump(mode="json")}, status_code=202)

    @app.get("/api/v1/projects/{project_id}/runs", response_model=ApiResponse)
    async def list_runs(project_id: str):
        context.projects.get(project_id)
        with context.uow_factory() as work:
            runs = tuple(work.runs.list_for_project(project_id))
            jobs = {item.run_id: work.jobs.get_by_run(item.run_id) for item in runs}
        return _data([_run_list_item(item, jobs[item.run_id], results) for item in runs])

    @app.get("/api/v1/runs/{run_id}", response_model=ApiResponse)
    async def get_run(run_id: str):
        with context.uow_factory() as work:
            run = work.runs.get(run_id)
        if run is None:
            raise JiejianError(ErrorCode.JOB_NOT_FOUND, "运行不存在")
        with context.uow_factory() as work:
            job = work.jobs.get_by_run(run_id)
        published = results.read(run_id) if run.lifecycle in {RunLifecycle.COMPLETED, RunLifecycle.SAFETY_STOPPED} else None
        view = {
            **run.model_dump(mode="json"),
            "job": job.model_dump(mode="json") if job else None,
            "result_integrity": "VERIFIED" if published else "UNAVAILABLE",
            **results.overview(run_id, published=published),
        }
        return _data(view)

    @app.post("/api/v1/jobs/{job_id}/cancel", response_model=ApiResponse)
    async def cancel_job(job_id: str):
        from ..worker.queue import JobQueueService
        result = JobQueueService(context.uow_factory).request_cancellation(RequestCancellationV1(schema_version="1", job_id=job_id, now_us=time.time_ns() // 1_000))
        return _data(result.model_dump(mode="json"))

    @app.get("/api/v1/jobs/{job_id}/events", response_model=None)
    async def job_events(job_id: str, request: Request, after: int | None = Query(default=None, ge=0), last_event_id: str | None = Header(default=None, alias="Last-Event-ID")):
        after = after if after is not None else _cursor(last_event_id)
        with context.uow_factory() as work:
            if work.jobs.get(job_id) is None:
                raise JiejianError(ErrorCode.JOB_NOT_FOUND, "任务不存在")

        def stream() -> Iterator[str]:
            cursor = after
            while True:
                with context.uow_factory() as work:
                    job = work.jobs.get(job_id)
                    events = work.job_events.list_for_job(job_id) if job else ()
                if job is None:
                    break
                for event in events:
                    if event.sequence <= cursor:
                        continue
                    cursor = event.sequence
                    payload = {
                        "schema_version": "1",
                        "job_id": job_id,
                        "sequence": event.sequence,
                        "event_type": event.event_type,
                        "source_state": event.source_state.value if event.source_state else None,
                        "target_state": event.target_state.value if event.target_state else None,
                        "occurred_at_us": event.occurred_at_us,
                        "metadata": redact(dict(event.metadata)),
                    }
                    yield f"id: {event.sequence}\ndata: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
                if job.state in {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED}:
                    break
                yield ": keep-alive\n\n"
                time.sleep(0.25)
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/v1/runs/{run_id}/report", response_model=ApiResponse)
    async def get_report(run_id: str):
        return _data(results.report(results.read(run_id)))

    @app.get("/api/v1/runs/{run_id}/evidence", response_model=ApiResponse)
    async def list_evidence(run_id: str):
        return _data([item.model_dump(mode="json") for item in results.read(run_id).evidence])

    @app.get("/api/v1/runs/{run_id}/findings", response_model=ApiResponse)
    async def list_findings(run_id: str):
        view = results.read(run_id)
        return _data(results.findings(view))

    @app.get("/api/v1/runs/{run_id}/evidence/{evidence_id}", response_model=ApiResponse)
    async def get_evidence(run_id: str, evidence_id: str):
        view = results.read(run_id)
        return _data(results.evidence_detail(view, evidence_id))

    @app.on_event("startup")
    async def startup() -> None:
        if start_worker:
            workers.start()

    @app.on_event("shutdown")
    async def shutdown() -> None:
        workers.stop()
        context.close()

    if app.state.frontend_dir is not None and app.state.frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=app.state.frontend_dir, html=True), name="frontend")

    return app


def _data(value: Any, *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"schema_version": "1", "data": value})


def _run_list_item(record: Any, job: Any, results: PublishedResultReader) -> dict[str, Any]:
    payload = {**record.model_dump(mode="json"), "job": job.model_dump(mode="json") if job else None}
    if record.lifecycle not in {RunLifecycle.COMPLETED, RunLifecycle.SAFETY_STOPPED}:
        payload["result_integrity"] = "UNAVAILABLE"
        return payload
    try:
        results.read(record.run_id)
    except JiejianError:
        payload["result_integrity"] = "INVALID"
        payload["verdict"] = None
        payload["reason_codes"] = []
    else:
        payload["result_integrity"] = "VERIFIED"
    return payload


def _cursor(value: str | None) -> int:
    if value is None:
        return 0
    try:
        return max(int(value), 0)
    except ValueError:
        return 0


def _status_for(code: str) -> int:
    if code in {
        ErrorCode.PROJECT_NOT_FOUND.value,
        ErrorCode.CONTRACT_NOT_FOUND.value,
        ErrorCode.RECORD_NOT_FOUND.value,
        ErrorCode.JOB_NOT_FOUND.value,
        ErrorCode.REPORT_NOT_FOUND.value,
        ErrorCode.ARTIFACT_NOT_PUBLISHED.value,
    }:
        return 404
    if code in {
        ErrorCode.PROJECT_SOURCE_DRIFT.value,
        ErrorCode.PROJECT_NOT_REVALIDATED.value,
        ErrorCode.CONTRACT_NOT_ACTIVE.value,
        ErrorCode.JOB_CANCEL_CONFLICT.value,
        ErrorCode.JOB_TERMINAL_CONFLICT.value,
    }:
        return 409
    if code in {ErrorCode.API_NOT_READY.value, ErrorCode.API_BINDING_REJECTED.value, ErrorCode.SERVE_FAILED.value}:
        return 503
    return 400
