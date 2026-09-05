# 仅注册三个 CURRENT AI 入口；GET 冷读取，POST 显式生成，焦点由服务端复核。
from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import Field

from product.backend.api.envelope import ApiModel, ApiResponse, data_response
from product.backend.core.business_boundary import ACTION_ID_PATTERN, ACTOR_ID_PATTERN
from product.backend.core.identifiers import RECORDING_ID_PATTERN
from product.backend.workflows.assistant.templates import AssistantTemplateId


class ProjectAssistantSurface(StrEnum):
    IMPLEMENTATION_MAPPING = "implementation-mapping"
    RECORDING_REVIEW = "recording-review"
    PREPARATION_EXPLANATION = "preparation-explanation"


_PROJECT_TEMPLATE = {
    ProjectAssistantSurface.IMPLEMENTATION_MAPPING: AssistantTemplateId.IMPLEMENTATION_MAPPING,
    ProjectAssistantSurface.RECORDING_REVIEW: AssistantTemplateId.BUSINESS_RECORDING_REVIEW,
    ProjectAssistantSurface.PREPARATION_EXPLANATION: AssistantTemplateId.PREPARATION_EXPLANATION,
}


class AssistantGenerateRequest(ApiModel):
    schema_version: Literal["1"]
    retry: bool = False


class AssistantFocus(ApiModel):
    business_actor_id: str | None = Field(default=None, pattern=ACTOR_ID_PATTERN)
    business_action_id: str | None = Field(default=None, pattern=ACTION_ID_PATTERN)
    recording_id: str | None = Field(default=None, pattern=RECORDING_ID_PATTERN)


def build_assistant_router(context) -> APIRouter:
    router = APIRouter()

    @router.get("/api/projects/{project_id}/assistant/{surface}", response_model=ApiResponse)
    async def get_project_assistant(project_id: str, surface: ProjectAssistantSurface, focus: Annotated[AssistantFocus, Query()]):
        return data_response(context.assistant_service.get_project(project_id, _PROJECT_TEMPLATE[surface],
            **focus.model_dump()).model_dump(mode="json"))

    @router.post("/api/projects/{project_id}/assistant/{surface}", response_model=ApiResponse)
    async def generate_project_assistant(project_id: str, surface: ProjectAssistantSurface,
            body: AssistantGenerateRequest, focus: Annotated[AssistantFocus, Query()]):
        return data_response(context.assistant_service.generate_project(project_id, _PROJECT_TEMPLATE[surface],
            retry=body.retry, **focus.model_dump()).model_dump(mode="json"))

    return router


__all__ = ["AssistantGenerateRequest", "ProjectAssistantSurface", "build_assistant_router"]
