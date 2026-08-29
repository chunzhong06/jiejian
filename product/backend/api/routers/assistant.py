# AI 辅助路由；项目和结果 GET 只读缓存，所有模型生成都要求显式 POST。

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from fastapi import APIRouter
from pydantic import Field

from product.backend.api.envelope import ApiModel, ApiResponse, data_response
from product.backend.workflows.assistant.diagnosis import ErrorDiagnosisContext, diagnose_error
from product.backend.workflows.assistant.templates import AssistantTemplateId
from product.backend.workflows.context import ApplicationCore


class ProjectAssistantSurface(StrEnum):
    NEXT_STEP = "next-step"
    CANDIDATE_REVIEW = "candidate-review"
    IDENTITY_PREPARATION = "identity-preparation"
    RECORDING_REVIEW = "recording-review"
    PERMISSION_REVIEW = "permission-review"
    OBSERVATION_RECOVERY = "observation-recovery"
    CHECK_PREVIEW_EXPLANATION = "check-preview-explanation"


_PROJECT_TEMPLATE = {
    ProjectAssistantSurface.NEXT_STEP: AssistantTemplateId.NEXT_STEP,
    ProjectAssistantSurface.CANDIDATE_REVIEW: AssistantTemplateId.CANDIDATE_REVIEW,
    ProjectAssistantSurface.IDENTITY_PREPARATION: AssistantTemplateId.IDENTITY_PREPARATION,
    ProjectAssistantSurface.RECORDING_REVIEW: AssistantTemplateId.RECORDING_REVIEW,
    ProjectAssistantSurface.PERMISSION_REVIEW: AssistantTemplateId.PERMISSION_REVIEW,
    ProjectAssistantSurface.OBSERVATION_RECOVERY: AssistantTemplateId.OBSERVATION_RECOVERY,
    ProjectAssistantSurface.CHECK_PREVIEW_EXPLANATION: AssistantTemplateId.CHECK_PREVIEW_EXPLANATION,
}


class AssistantGenerateRequest(ApiModel):
    schema_version: Literal["1"]
    retry: bool = False


class ErrorAssistantRequest(ApiModel):
    schema_version: Literal["1"]
    error_code: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,95}$")
    retry: bool = False


def build_assistant_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/projects/{project_id}/assistant/{surface}",
        response_model=ApiResponse,
    )
    async def get_project_assistant(project_id: str, surface: ProjectAssistantSurface):
        return data_response(
            context.assistant_service.get_project(
                project_id,
                _PROJECT_TEMPLATE[surface],
            ).model_dump(mode="json")
        )

    @router.post(
        "/api/projects/{project_id}/assistant/{surface}",
        response_model=ApiResponse,
    )
    async def generate_project_assistant(
        project_id: str,
        surface: ProjectAssistantSurface,
        body: AssistantGenerateRequest,
    ):
        return data_response(
            context.assistant_service.generate_project(
                project_id,
                _PROJECT_TEMPLATE[surface],
                retry=body.retry,
            ).model_dump(mode="json")
        )

    @router.get("/api/runs/{run_id}/assistant/result", response_model=ApiResponse)
    async def get_result_assistant(run_id: str):
        return data_response(context.assistant_service.get_result(run_id).model_dump(mode="json"))

    @router.post("/api/runs/{run_id}/assistant/result", response_model=ApiResponse)
    async def generate_result_assistant(run_id: str, body: AssistantGenerateRequest):
        return data_response(
            context.assistant_service.generate_result(run_id, retry=body.retry).model_dump(mode="json")
        )

    @router.post("/api/assistant/error", response_model=ApiResponse)
    async def generate_error_assistant(body: ErrorAssistantRequest):
        # 浏览器只回传稳定错误码；诊断事实必须在服务端重新形成，不能信任客户端回传的字段。
        diagnosis = diagnose_error(ErrorDiagnosisContext(error_code=body.error_code))
        return data_response(
            context.assistant_service.generate_error(
                body.error_code,
                diagnosis,
                retry=body.retry,
            ).model_dump(mode="json")
        )

    return router


__all__ = [
    "AssistantGenerateRequest",
    "ErrorAssistantRequest",
    "ProjectAssistantSurface",
    "build_assistant_router",
]
