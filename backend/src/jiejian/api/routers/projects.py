# =============================================================================
# Project API Router
#
# 定位
#   Project 接入与显式 YAML Contract 激活的 HTTP 适配器
#
# 职责
#   校验项目请求｜调用 Project 服务｜保留显式 Contract 公共行为
#
# 调用链
#   FastAPI → projects router → ProjectControlService / ContractWorkbench
# =============================================================================

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from ...application.context import ApplicationContext
from ..responses import data_response
from ..schemas.common import ApiResponse
from ..schemas.projects import ContractActivateRequest, ProjectRegisterRequest


def build_projects_router(context: ApplicationContext) -> APIRouter:
    router = APIRouter()

    @router.post("/api/v1/projects", response_model=ApiResponse)
    async def register_project(body: ProjectRegisterRequest):
        record, _ = context.projects.register(Path(body.path), revalidate=body.revalidate)
        return data_response(record.model_dump(mode="json"))

    @router.get("/api/v1/projects", response_model=ApiResponse)
    async def list_projects():
        return data_response(
            [record.model_dump(mode="json") for record in context.projects.list()]
        )

    @router.get("/api/v1/projects/{project_id}", response_model=ApiResponse)
    async def get_project(project_id: str):
        return data_response(context.projects.get(project_id).model_dump(mode="json"))

    @router.post(
        "/api/v1/projects/{project_id}/revalidate", response_model=ApiResponse
    )
    async def revalidate_project(project_id: str):
        record, _ = context.projects.revalidate(project_id)
        return data_response(record.model_dump(mode="json"))

    @router.get(
        "/api/v1/projects/{project_id}/contracts", response_model=ApiResponse
    )
    async def list_contracts(project_id: str):
        record = context.projects.get(project_id)
        if not record.active_contract_path:
            return data_response([])
        contract = context.projects.current_bundle(project_id)[1].contract
        return data_response(
            [
                {
                    "schema_version": "1",
                    "path": record.active_contract_path,
                    "hash": record.active_contract_hash,
                    "status": contract.status.value,
                    "id": contract.id,
                    "version": contract.version,
                    "rules": [item.model_dump(mode="json") for item in contract.rules],
                }
            ]
        )

    @router.post(
        "/api/v1/projects/{project_id}/contracts/activate",
        response_model=ApiResponse,
    )
    async def activate_contract(project_id: str, body: ContractActivateRequest):
        record = context.projects.activate_contract(project_id, Path(body.path))
        return data_response(record.model_dump(mode="json"))

    return router
