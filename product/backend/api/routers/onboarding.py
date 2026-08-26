# 首次使用 API：只适配目录选择与受限识别，不再承载手工快速检查。

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import Field

from product.backend.api.envelope import ApiModel, ApiResponse, data_response
from product.backend.workflows.context import ApplicationCore


class OnboardingInspectRequest(ApiModel):
    schema_version: Literal["1"]
    path: str = Field(min_length=1, max_length=32_768)


def build_onboarding_router(context: ApplicationCore) -> APIRouter:
    """构造只读首次使用路由；选择目录本身不触发识别。"""

    router = APIRouter()

    @router.post("/api/onboarding/select-folder", response_model=ApiResponse)
    def select_folder():
        result = context.onboarding.select_folder()
        return data_response(result.model_dump(mode="json", exclude_none=True))

    @router.post("/api/onboarding/inspect", response_model=ApiResponse)
    def inspect_folder(body: OnboardingInspectRequest):
        result = context.onboarding.inspect(body.path)
        return data_response(result.model_dump(mode="json"))

    return router
