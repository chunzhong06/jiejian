# 当前检查提交与状态接口；只接受冻结计划指纹，执行及发布由独立 Worker 承担。
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query
from pydantic import Field

from product.backend.api.envelope import ApiModel, ApiResponse, data_response
from product.backend.composition import ApplicationCore
from product.backend.core.identifiers import RUN_ID_PATTERN
from product.backend.core.lifecycle import RunLifecycle, RunVerdict


class RunCreateRequest(ApiModel):
    schema_version: Literal["2"]
    expected_plan_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=128)
    change_id: str | None = Field(default=None,pattern=r"^chg_[0-9a-f]{32}$")


def build_runs_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.post("/api/projects/{project_id}/runs", response_model=ApiResponse, status_code=202)
    def create_run(project_id: str, body: RunCreateRequest):
        submitted = context.checks.submit(project_id, expected_plan_fingerprint=body.expected_plan_fingerprint,
            idempotency_key=body.idempotency_key,change_id=body.change_id)
        status = context.check_results.status(submitted.run.run_id, project_id=project_id)
        return data_response({"run": status.run.model_dump(mode="json"),
            "job": status.job.model_dump(mode="json")}, status_code=202)

    @router.get("/api/projects/{project_id}/runs", response_model=ApiResponse)
    def list_runs(project_id: str):
        return data_response([item.model_dump(mode="json") for item in context.check_results.list_for_project(project_id)])

    @router.get("/api/projects/{project_id}/check-history", response_model=ApiResponse)
    def check_history(project_id: str, limit: int = Query(25, ge=1, le=50),
                      before_created_at_us: int | None = Query(None, ge=0),
                      before_run_id: str | None = Query(None, pattern=RUN_ID_PATTERN),
                      query: str | None = Query(None, max_length=128),
                      verdict: RunVerdict | None = None, lifecycle: RunLifecycle | None = None):
        return data_response(context.check_results.history(project_id, limit=limit,
            before_created_at_us=before_created_at_us, before_run_id=before_run_id,
            query=query, verdict=verdict, lifecycle=lifecycle).model_dump(mode="json"))

    @router.get("/api/runs/{run_id}", response_model=ApiResponse)
    def get_run(run_id: str):
        return data_response(context.check_results.status(run_id).model_dump(mode="json"))

    return router
