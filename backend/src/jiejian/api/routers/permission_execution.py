"""Permission Execution Profile V2 API；只调用共享应用服务。"""

from __future__ import annotations

import time
from pathlib import Path

from fastapi import APIRouter

from ...application.context import ApplicationContext
from ..responses import data_response
from ..schemas.common import ApiResponse
from ..schemas.permission_execution import (
    PermissionExecutionProfileCreateRequest,
    PermissionExecutionRunRequest,
)


def build_permission_execution_router(context: ApplicationContext) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/v2/permission-execution-profiles",
        response_model=ApiResponse,
        status_code=201,
    )
    async def register_profile(body: PermissionExecutionProfileCreateRequest):
        record = context.permission_execution.register(
            Path(body.path),
            revalidate=body.revalidate,
        )
        return data_response(record.model_dump(mode="json"), status_code=201)

    @router.get(
        "/api/v2/projects/{project_id}/permission-execution-profiles",
        response_model=ApiResponse,
    )
    async def list_profiles(project_id: str):
        return data_response(
            [item.model_dump(mode="json") for item in context.permission_execution.list(project_id)]
        )

    @router.post(
        "/api/v2/projects/{project_id}/runs",
        response_model=ApiResponse,
        status_code=202,
    )
    async def submit_profile_run(project_id: str, body: PermissionExecutionRunRequest):
        result, request, _ = context.permission_execution.submit(
            body.profile_id,
            project_id=project_id,
            idempotency_key=body.idempotency_key,
            max_attempts=body.max_attempts,
            now_us=time.time_ns() // 1_000,
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
