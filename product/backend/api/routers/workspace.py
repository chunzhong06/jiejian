# =============================================================================
# 定位
#   1.1.1 CURRENT 动作级工作区的 loopback HTTP 读入口。
#
# 职责
#   把 WorkspaceService 的权威投影装入统一 API envelope。
#
# 边界
#   只提供 GET；不接受页面状态、任务执行或旧 ProductStatus 写入。
#
# 调用链
#   CURRENT Web 工作台 -> /api/projects/{project_id}/workspace -> WorkspaceService。
# =============================================================================

from fastapi import APIRouter

from product.backend.api.envelope import ApiResponse, data_response
from product.backend.composition import ApplicationCore


def build_workspace_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.get("/api/projects/{project_id}/workspace", response_model=ApiResponse)
    async def get_workspace(project_id: str):
        return data_response(context.workspace.get(project_id).model_dump(mode="json"))

    return router


__all__ = ["build_workspace_router"]
