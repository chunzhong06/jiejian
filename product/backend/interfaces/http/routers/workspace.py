# 把 WorkspaceService 的权威投影装入统一 API envelope。
# 只提供 GET；不接受页面状态、任务执行或旧 ProductStatus 写入。

from typing import Annotated
from fastapi import APIRouter, Query

from product.backend.interfaces.http.envelope import ApiResponse, data_response
from product.backend.bootstrap import ApplicationCore


def build_workspace_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.get("/api/projects/{project_id}/workspace", response_model=ApiResponse)
    def get_workspace(project_id: str):
        return data_response(context.workspace.get(project_id).model_dump(mode="json"))

    @router.get('/api/projects/{project_id}/workspace/preparation', response_model=ApiResponse)
    def preparation_work(project_id: str, action_id: Annotated[list[str], Query(min_length=1, max_length=256)]):
        return data_response(context.workspace.preparation_work(project_id, tuple(action_id)).model_dump(mode='json'))

    @router.get('/api/projects/{project_id}/workspace/revision', response_model=ApiResponse)
    def workspace_revision(project_id: str):
        context.projects.get(project_id)
        return data_response(context.workspace_revision.read())

    return router


__all__ = ["build_workspace_router"]
