# Permission Execution Profile API；只适配请求并调用共享 execution 应用服务。

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from product.backend.workflows.context import ApplicationCore
from product.backend.api.envelope import data_response
from product.backend.api.envelope import ApiResponse


def build_execution_profiles_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/execution-profiles",
        response_model=ApiResponse,
        status_code=201,
    )
    async def register_profile(body: ExecutionProfileCreateRequest):
        record = context.execution.register(
            Path(body.profile_path),
            accept_source_changes=body.accept_source_changes,
        )
        return data_response(record.model_dump(mode="json"), status_code=201)

    @router.get(
        "/api/projects/{project_id}/execution-profiles",
        response_model=ApiResponse,
    )
    async def list_profiles(project_id: str):
        return data_response(
            [item.model_dump(mode="json") for item in context.execution.list(project_id)]
        )

    @router.get(
        "/api/projects/{project_id}/execution-profiles/{profile_id}/contract",
        response_model=ApiResponse,
    )
    async def get_profile_contract(project_id: str, profile_id: str):
        contract = context.execution.current_contract(profile_id, project_id=project_id)
        return data_response(contract.model_dump(mode="json"))

    return router

"""Permission Execution Profile 控制面请求 DTO。"""

from pathlib import Path
from typing import Literal

from pydantic import Field

from product.backend.api.envelope import ApiModel


class ExecutionProfileCreateRequest(ApiModel):
    schema_version: Literal["1"] = "1"
    profile_path: str = Field(min_length=1, max_length=2048)
    accept_source_changes: bool = False
