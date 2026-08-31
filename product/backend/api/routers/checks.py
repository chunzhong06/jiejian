# 持续验证的准备、预览与提交 API；执行和判定仍由共享 ExecutionWorkflow 完成。

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import Field

from product.backend.api.envelope import ApiModel, ApiResponse, data_response
from product.backend.workflows.context import ApplicationCore


class CheckSubmitRequest(ApiModel):
    schema_version: Literal["1"]
    idempotency_key: str = Field(min_length=1, max_length=128)
    change_id: str | None = Field(default=None, pattern=r"^chg_[0-9a-f]{32}$")


class CheckPrepareRequest(ApiModel):
    schema_version: Literal["1"]
    change_id: str | None = Field(default=None, pattern=r"^chg_[0-9a-f]{32}$")


def build_checks_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/projects/{project_id}/check-preview",
        response_model=ApiResponse,
    )
    async def check_preview(project_id: str, change_id: str | None = None):
        return data_response(
            context.checks.preview(project_id, change_id=change_id).model_dump(mode="json")
        )

    @router.post(
        "/api/projects/{project_id}/check-preparation",
        response_model=ApiResponse,
    )
    async def prepare_check(project_id: str, body: CheckPrepareRequest):
        return data_response(
            context.checks.prepare(
                project_id,
                change_id=body.change_id,
            ).model_dump(mode="json")
        )

    @router.post(
        "/api/projects/{project_id}/checks",
        response_model=ApiResponse,
        status_code=202,
    )
    async def submit_check(project_id: str, body: CheckSubmitRequest):
        result, request, _ = context.checks.submit(
            project_id,
            idempotency_key=body.idempotency_key,
            change_id=body.change_id,
        )
        return data_response(
            {
                "job": result.job.model_dump(mode="json"),
                "run": result.run.model_dump(mode="json"),
                "schema_version": request.schema_version,
            },
            status_code=202,
        )

    return router
