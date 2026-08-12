# =============================================================================
# Verification Run API Router
#
# 定位
#   Run 提交、列表和详情读取的 HTTP 应用边界
#
# 职责
#   提交冻结执行请求｜区分生命周期与 Verdict｜读取已发布结果
#
# 调用链
#   FastAPI → runs router → Execution submission / PublishedResultReader
# =============================================================================

from __future__ import annotations

import os
import time

from fastapi import APIRouter

from ...application.context import ApplicationContext
from ...results.published import PublishedResultReader
from ...domain.lifecycle import RunLifecycle
from ...errors import ErrorCode, JiejianError
from ...execution.submission import SubmitExecutionV1
from ..responses import data_response
from ..schemas.common import ApiResponse
from ..schemas.runs import RunCreateRequest


def _run_list_item(
    record: object, job: object, results: PublishedResultReader
) -> dict[str, object]:
    payload = {
        **record.model_dump(mode="json"),
        "job": job.model_dump(mode="json") if job else None,
    }
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


def build_runs_router(
    context: ApplicationContext, results: PublishedResultReader
) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/v1/projects/{project_id}/runs",
        response_model=ApiResponse,
        status_code=202,
    )
    async def create_run(project_id: str, body: RunCreateRequest):
        request = context.execution_requests.execution_request(project_id)
        now_us = time.time_ns() // 1_000
        result = context.execution_submission.submit(
            SubmitExecutionV1(
                schema_version="1",
                request=request,
                idempotency_key=body.idempotency_key,
                now_us=now_us,
                available_at_us=now_us,
            ),
            known_secrets=tuple(
                os.environ.get(item.secret_ref.removeprefix("env:"), "")
                for item in request.project_snapshot.identities
            ),
        )
        return data_response(
            {
                "job": result.job.model_dump(mode="json"),
                "run": result.run.model_dump(mode="json"),
            },
            status_code=202,
        )

    @router.get("/api/v1/projects/{project_id}/runs", response_model=ApiResponse)
    async def list_runs(project_id: str):
        context.projects.get(project_id)
        with context.uow_factory() as work:
            runs = tuple(work.runs.list_for_project(project_id))
            jobs = {item.run_id: work.jobs.get_by_run(item.run_id) for item in runs}
        return data_response([_run_list_item(item, jobs[item.run_id], results) for item in runs])

    @router.get("/api/v1/runs/{run_id}", response_model=ApiResponse)
    async def get_run(run_id: str):
        with context.uow_factory() as work:
            run = work.runs.get(run_id)
        if run is None:
            raise JiejianError(ErrorCode.JOB_NOT_FOUND, "运行不存在")
        with context.uow_factory() as work:
            job = work.jobs.get_by_run(run_id)
        published = (
            results.read(run_id)
            if run.lifecycle in {RunLifecycle.COMPLETED, RunLifecycle.SAFETY_STOPPED}
            else None
        )
        view = {
            **run.model_dump(mode="json"),
            "job": job.model_dump(mode="json") if job else None,
            "result_integrity": "VERIFIED" if published else "UNAVAILABLE",
            **results.overview(run_id, published=published),
        }
        return data_response(view)

    return router
