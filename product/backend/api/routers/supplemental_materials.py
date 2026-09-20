# 补充材料控制面适配；严格 DTO 与既有 envelope，不承担执行或判定。
from fastapi import APIRouter, Query
from pydantic import Field
from product.backend.api.envelope import ApiModel, ApiResponse, data_response
from product.backend.workflows.supplemental_contract import SupplementalDocument


class MaterialPreviewRequest(ApiModel):
    document: SupplementalDocument


class MaterialCreateRequest(MaterialPreviewRequest):
    expected_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_id: str


class MaterialWithdrawRequest(ApiModel):
    expected_revision: int = Field(ge=1)
    request_id: str


class MaterialRevisionRequest(MaterialWithdrawRequest):
    title: str = Field(min_length=1, max_length=128)
    source_label: str = Field(min_length=1, max_length=128)
    claimed_resource_label: str | None = Field(default=None, max_length=128)


def build_supplemental_material_router(context):
    router = APIRouter()
    path = "/api/projects/{project_id}/actions/{action_id}/supplemental-materials"

    @router.post(path + "/preview", response_model=ApiResponse)
    def preview(project_id: str, action_id: str, body: MaterialPreviewRequest):
        return data_response(context.supplemental_materials.preview(project_id, action_id, body.document.model_dump(mode="json")))

    @router.post(path, response_model=ApiResponse)
    def create(project_id: str, action_id: str, body: MaterialCreateRequest):
        return data_response(context.supplemental_materials.create(project_id, action_id, **body.model_dump(mode="json")))

    @router.get(path, response_model=ApiResponse)
    def listing(project_id: str, action_id: str, limit: int = Query(100, ge=1, le=100)):
        return data_response(context.supplemental_materials.list(project_id, action_id, limit=limit))

    @router.get(path + "/{material_id}/revisions", response_model=ApiResponse)
    def revisions(project_id: str, action_id: str, material_id: str, limit: int = Query(100, ge=1, le=100), before_revision: int | None = Query(None, ge=1)):
        return data_response(context.supplemental_materials.list(project_id, action_id, material_id=material_id, limit=limit, before_revision=before_revision))

    @router.post(path + "/{material_id}/revisions", response_model=ApiResponse)
    def revise(project_id: str, action_id: str, material_id: str, body: MaterialRevisionRequest):
        return data_response(context.supplemental_materials.revise(project_id, action_id, material_id, **body.model_dump()))

    @router.post(path + "/{material_id}/withdraw", response_model=ApiResponse)
    def withdraw(project_id: str, action_id: str, material_id: str, body: MaterialWithdrawRequest):
        return data_response(context.supplemental_materials.withdraw(project_id, action_id, material_id, **body.model_dump()))

    return router
