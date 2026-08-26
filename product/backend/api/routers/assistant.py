# AI 辅助工作台路由；GET 只读确定性事实，POST 才进入受控模型调用。

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter

from product.backend.api.envelope import ApiModel, ApiResponse, data_response
from product.backend.workflows.context import ApplicationCore


class AssistantRefreshRequest(ApiModel):
    schema_version: Literal["1"]
    retry: bool = False


def build_assistant_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.get("/api/projects/{project_id}/assistant/guidance", response_model=ApiResponse)
    async def get_assistant_guidance(project_id: str):
        return data_response(context.assistant_service.get(project_id).model_dump(mode="json"))

    @router.post("/api/projects/{project_id}/assistant/guidance/refresh", response_model=ApiResponse)
    async def refresh_assistant_guidance(project_id: str, body: AssistantRefreshRequest):
        return data_response(
            context.assistant_service.refresh(project_id, retry=body.retry).model_dump(mode="json")
        )

    return router


__all__ = ["AssistantRefreshRequest", "build_assistant_router"]
