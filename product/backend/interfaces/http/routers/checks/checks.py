# 当前全部业务动作的只读检查预览，保留未准备动作及其缺口。
from fastapi import APIRouter
from pydantic import Field

from product.backend.interfaces.http.envelope import ApiModel, ApiResponse, data_response
from product.backend.bootstrap import ApplicationCore
from product.protocols.checks.execution_request import PermissionReference


class CheckScopeRequest(ApiModel):
    selected_permissions: list[PermissionReference] = Field(min_length=1, max_length=4096)


def build_checks_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.get("/api/projects/{project_id}/check-preview", response_model=ApiResponse)
    def check_preview(project_id: str, change_id: str | None = None):
        return data_response(context.checks.preview(project_id,change_id=change_id).model_dump(mode="json"))

    @router.post("/api/projects/{project_id}/check-preview", response_model=ApiResponse)
    def selected_preview(project_id: str, body: CheckScopeRequest):
        return data_response(context.checks.preview(project_id, selected_permissions=tuple(body.selected_permissions)).model_dump(mode="json"))

    return router
