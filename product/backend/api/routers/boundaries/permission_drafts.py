# 将显式用户文本交给受限草稿服务；不提供 proposal、审批或自动生效入口。

from typing import Literal

from fastapi import APIRouter
from pydantic import Field

from product.backend.api.envelope import ApiModel, ApiResponse, data_response


class PermissionDraftRequest(ApiModel):
    schema_version: Literal["1"]
    text: str = Field(min_length=1, max_length=2000)


def build_permission_drafts_router(context) -> APIRouter:
    router = APIRouter()

    @router.post("/api/projects/{project_id}/permission-drafts", response_model=ApiResponse)
    async def draft_permissions(project_id: str, body: PermissionDraftRequest):
        return data_response(context.permission_drafts.draft(project_id, body.text).model_dump(mode="json"))

    return router
