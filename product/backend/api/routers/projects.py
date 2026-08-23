# Project API Router
# 适配 Project 接入和当前 PermissionContract 读取，不在路由层推断治理结论。

from __future__ import annotations

from typing import Literal
from pathlib import Path

from fastapi import APIRouter
from pydantic import Field

from product.backend.workflows.context import ApplicationCore
from product.backend.api.envelope import data_response
from product.backend.api.envelope import ApiResponse
from product.backend.api.envelope import ApiModel


def build_projects_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.post("/api/projects", response_model=ApiResponse)
    async def register_project(body: ProjectRegisterRequest):
        record, _ = context.projects.register(Path(body.profile_path))
        return data_response(record.model_dump(mode="json"))

    @router.get("/api/projects", response_model=ApiResponse)
    async def list_projects():
        return data_response(
            [record.model_dump(mode="json") for record in context.projects.list()]
        )

    @router.get("/api/projects/{project_id}", response_model=ApiResponse)
    async def get_project(project_id: str):
        return data_response(context.projects.get(project_id).model_dump(mode="json"))

    @router.get(
        "/api/projects/{project_id}/contracts", response_model=ApiResponse
    )
    async def list_contracts(project_id: str):
        record = context.projects.get(project_id)
        if record.governed_contract_id is None or record.governed_contract_version is None:
            return data_response([])
        version = context.projects.current_contract(project_id)
        contract = version.snapshot
        return data_response(
            [
                {
                    "schema_version": "1",
                    "status": version.status.value,
                    "id": contract.contract_id,
                    "version": contract.version,
                    "rules": [item.model_dump(mode="json") for item in contract.rules],
                }
            ]
        )

    return router


class ProjectRegisterRequest(ApiModel):
    schema_version: Literal["1"]
    profile_path: str = Field(min_length=1, max_length=2048)
