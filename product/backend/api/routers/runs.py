# Verification Run API Router
# 适配 Run 提交与只读查询；生命周期、Verdict 和 publication 语义由共享应用层维护。

from __future__ import annotations

from typing import Literal
from fastapi import APIRouter
from pydantic import Field

from product.backend.workflows.context import ApplicationCore
from product.backend.workflows.results.published import PublishedResultReader
from product.backend.core.lifecycle import RunLifecycle
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage import FindingFinalizationState
from product.backend.api.envelope import data_response
from product.backend.api.envelope import ApiResponse
from product.backend.api.envelope import ApiModel


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
    context: ApplicationCore, results: PublishedResultReader
) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/projects/{project_id}/runs",
        response_model=ApiResponse,
        status_code=202,
    )
    async def create_run(project_id: str, body: RunCreateRequest):
        result, request, _ = context.execution.submit(
            body.profile_id,
            project_id=project_id,
            idempotency_key=body.idempotency_key,
        )
        return data_response(
            {
                "job": result.job.model_dump(mode="json"),
                "run": result.run.model_dump(mode="json"),
                "schema_version": request.schema_version,
            },
            status_code=202,
        )

    @router.get("/api/projects/{project_id}/runs", response_model=ApiResponse)
    async def list_runs(project_id: str):
        context.projects.get(project_id)
        with context.uow_factory() as work:
            runs = tuple(work.runs.list_for_project(project_id))
            jobs = {item.run_id: work.jobs.get_by_run(item.run_id) for item in runs}
        return data_response([_run_list_item(item, jobs[item.run_id], results) for item in runs])

    @router.get("/api/runs/{run_id}", response_model=ApiResponse)
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
        try:
            finalization = context.result_finalizer.status(run_id)
        except JiejianError as exc:
            if exc.code != ErrorCode.RESULT_FINALIZATION_NOT_FOUND.value:
                raise
            finalization_summary = {
                "findings_state": None,
                "base_report_state": None,
                "base_report_id": None,
                "last_error_code": None,
            }
        else:
            finalization_summary = {
                "findings_state": finalization.findings_state.value,
                "base_report_state": finalization.base_report_state.value,
                "base_report_id": finalization.base_report_id,
                "last_error_code": (
                    finalization.base_report_error_code
                    or finalization.findings_error_code
                ),
            }
            if finalization.findings_state is FindingFinalizationState.COMPLETE:
                view["finding_count"] = len(context.findings.findings_for_run(run_id))
        view["finalization"] = finalization_summary
        return data_response(view)

    return router


class RunCreateRequest(ApiModel):
    schema_version: Literal["1"]
    profile_id: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=128)
