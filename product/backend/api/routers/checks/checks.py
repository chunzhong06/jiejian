# 当前全部业务动作的只读检查预览，保留未准备动作及其缺口。
from fastapi import APIRouter

from product.backend.api.envelope import ApiResponse, data_response
from product.backend.composition import ApplicationCore


def build_checks_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.get("/api/projects/{project_id}/check-preview", response_model=ApiResponse)
    def check_preview(project_id: str, change_id: str | None = None):
        return data_response(context.checks.preview(project_id,change_id=change_id).model_dump(mode="json"))

    return router
