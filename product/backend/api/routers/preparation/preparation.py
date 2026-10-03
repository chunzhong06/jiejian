# 投影动作准备只读真源并接受有限 ALLOW 技术选择，不修改权限或运行检查。

from fastapi import APIRouter
from product.backend.api.envelope import ApiResponse, data_response
from product.backend.api.envelope import ApiModel
from product.backend.core.preparation.requirements import PermissionIdentity
from pydantic import Field
from typing import Literal
from product.backend.workflows.preparation.materials.models import MaterialChange, MaterialReference, PreparationDraft


class AllowControlSelectionRequest(ApiModel):
    schema_version: Literal["1"]
    deny_permission: PermissionIdentity
    selected_allow_permission: PermissionIdentity
    expected_selection_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


def build_preparation_router(context) -> APIRouter:
    router = APIRouter()
    from product.backend.api.routers.preparation.proof_sources import build_proof_sources_router
    router.include_router(build_proof_sources_router(context))

    @router.get("/api/projects/{project_id}/preparation/materials/{action_id}/{kind}", response_model=ApiResponse)
    async def material_details(project_id: str, action_id: str, kind: Literal["execution", "resource", "evidence", "recovery"], action_revision: int, member_id: str | None = None):
        ref = MaterialReference(action_id=action_id, action_revision=action_revision, kind=kind, member_id=member_id)
        return data_response(context.preparation_materials.details(project_id, ref))

    @router.post("/api/projects/{project_id}/preparation/changes/preview", response_model=ApiResponse)
    async def preview_material(project_id: str, body: MaterialChange):
        return data_response(context.preparation_materials.preview(project_id, body))

    @router.post("/api/projects/{project_id}/preparation/changes", response_model=ApiResponse)
    async def save_material(project_id: str, body: MaterialChange):
        return data_response(context.preparation_materials.apply(project_id, body))

    @router.get("/api/projects/{project_id}/preparation/changes/{operation_id}", response_model=ApiResponse)
    async def material_receipt(project_id: str, operation_id: str):
        return data_response(context.preparation_materials.receipt(project_id, operation_id))

    @router.get("/api/projects/{project_id}/preparation/draft", response_model=ApiResponse)
    async def preparation_draft(project_id: str):
        return data_response(context.preparation_materials.draft(project_id))

    @router.put("/api/projects/{project_id}/preparation/draft", response_model=ApiResponse)
    async def save_preparation_draft(project_id: str, body: PreparationDraft):
        return data_response(context.preparation_materials.save_draft(project_id, body))

    @router.get("/api/projects/{project_id}/preparation", response_model=ApiResponse)
    async def get_preparation(project_id: str):
        return data_response(context.preparation.get(project_id).model_dump(mode="json"))

    @router.get("/api/projects/{project_id}/preparation/evidence/{action_id}", response_model=ApiResponse)
    async def get_evidence_details(project_id: str, action_id: str):
        return data_response(context.preparation.evidence_details(project_id, action_id).model_dump(mode="json"))

    @router.post("/api/projects/{project_id}/preparation/allow-control", response_model=ApiResponse)
    async def select_allow_control(project_id: str, body: AllowControlSelectionRequest):
        # 外层 LocalControlGuard 对全部写请求实施当前会话与精确 Origin 防护。
        binding = context.preparation.select_allow_control(
            project_id, deny_permission=body.deny_permission,
            selected_allow_permission=body.selected_allow_permission,
            expected_selection_fingerprint=body.expected_selection_fingerprint,
        )
        return data_response(binding.model_dump(mode="json"))

    return router
