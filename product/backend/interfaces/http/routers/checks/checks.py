# 当前全部业务动作的只读检查预览，保留未准备动作及其缺口。
from fastapi import APIRouter
from pydantic import Field

from product.backend.interfaces.http.envelope import ApiModel, ApiResponse, data_response
from product.backend.bootstrap import ApplicationCore
from product.protocols.checks.execution_request import PermissionReference
from product.backend.application.checks.routines import SaveCheckRoutine


class CheckScopeRequest(ApiModel):
    selected_permissions: list[PermissionReference] = Field(min_length=1, max_length=4096)


def build_checks_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.get('/api/projects/{project_id}/check-routines', response_model=ApiResponse)
    def routines(project_id: str):
        return data_response(context.check_routines.list(project_id))

    @router.post('/api/projects/{project_id}/check-routines', response_model=ApiResponse)
    def save_routine(project_id: str, body: SaveCheckRoutine):
        return data_response(context.check_routines.save(project_id, body))

    @router.delete('/api/projects/{project_id}/check-routines/{routine_id}', response_model=ApiResponse)
    def delete_routine(project_id: str, routine_id: str):
        context.check_routines.delete(project_id, routine_id)
        return data_response({'deleted': True})

    @router.get("/api/projects/{project_id}/check-preview", response_model=ApiResponse)
    def check_preview(project_id: str, change_id: str | None = None):
        return data_response(context.checks.preview(project_id,change_id=change_id).model_dump(mode="json"))

    @router.post("/api/projects/{project_id}/check-preview", response_model=ApiResponse)
    def selected_preview(project_id: str, body: CheckScopeRequest):
        return data_response(context.checks.preview(project_id, selected_permissions=tuple(body.selected_permissions)).model_dump(mode="json"))

    return router
