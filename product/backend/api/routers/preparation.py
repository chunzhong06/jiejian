# 投影动作准备只读真源并接受有限 ALLOW 技术选择，不修改权限或运行检查。

from fastapi import APIRouter
from product.backend.api.envelope import ApiResponse, data_response
from product.backend.api.envelope import ApiModel
from product.backend.core.assurance import PermissionIdentity
from pydantic import Field
from typing import Literal


class AllowControlSelectionRequest(ApiModel):
    schema_version: Literal["1"]
    deny_permission: PermissionIdentity
    selected_allow_permission: PermissionIdentity
    expected_selection_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


def build_preparation_router(context) -> APIRouter:
    router = APIRouter()

    @router.get("/api/projects/{project_id}/preparation", response_model=ApiResponse)
    async def get_preparation(project_id: str):
        return data_response(context.preparation.get(project_id).model_dump(mode="json"))

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
