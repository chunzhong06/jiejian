# 将动作准备只读真源投影为控制面响应，不创建材料或运行检查。

from fastapi import APIRouter
from product.backend.api.envelope import ApiResponse, data_response


def build_preparation_router(context) -> APIRouter:
    router = APIRouter()

    @router.get("/api/projects/{project_id}/preparation", response_model=ApiResponse)
    async def get_preparation(project_id: str):
        return data_response(context.preparation.get(project_id).model_dump(mode="json"))

    return router
