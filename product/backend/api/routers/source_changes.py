# 代码变化只读 API；仅返回有界产品摘要，不暴露源码路径、内容或内部指纹。

from __future__ import annotations

from fastapi import APIRouter

from product.backend.api.envelope import ApiResponse, data_response
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.context import ApplicationCore


def build_source_changes_router(context: ApplicationCore) -> APIRouter:
    """组合最近变化和指定变化两个只读入口。"""

    router = APIRouter()

    @router.get(
        "/api/projects/{project_id}/source-changes/latest",
        response_model=ApiResponse,
    )
    async def latest_source_change(project_id: str):
        latest = context.source_changes.latest_view(project_id)
        return data_response(None if latest is None else latest.model_dump(mode="json"))

    @router.get(
        "/api/projects/{project_id}/source-changes/{change_id}",
        response_model=ApiResponse,
    )
    async def source_change(project_id: str, change_id: str):
        view = context.source_changes.view(change_id)
        if view.project_id != project_id:
            raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "代码变化不属于当前应用")
        return data_response(view.model_dump(mode="json"))

    return router
