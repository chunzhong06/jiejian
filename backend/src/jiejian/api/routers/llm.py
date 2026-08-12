"""LLM profile 设置与显式连接测试的薄 API Router。"""

from __future__ import annotations

from fastapi import APIRouter

from ...application.context import ApplicationContext
from ..responses import data_response
from ..schemas.common import ApiResponse
from ..schemas.llm import (
    LLMProfileCreateRequest,
    LLMProfileResponse,
    LLMProfileUpdateRequest,
)


def build_llm_router(context: ApplicationContext) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v1/llm/profiles", response_model=ApiResponse)
    async def list_llm_profiles():
        return data_response(
            [item.model_dump(mode="json") for item in context.llm_profiles.list()]
        )

    @router.get(
        "/api/v1/llm/profiles/{profile_name}",
        response_model=ApiResponse,
    )
    async def get_llm_profile(profile_name: str):
        return data_response(context.llm_profiles.get(profile_name).model_dump(mode="json"))

    @router.post(
        "/api/v1/llm/profiles",
        response_model=ApiResponse,
        status_code=201,
    )
    async def create_llm_profile(body: LLMProfileCreateRequest):
        values = body.model_dump(mode="python", exclude={"secret"})
        secret = body.secret.get_secret_value() if body.secret is not None else None
        profile = context.llm_profiles.create(values, secret=secret)
        return data_response(profile.model_dump(mode="json"), status_code=201)

    @router.patch(
        "/api/v1/llm/profiles/{profile_name}",
        response_model=ApiResponse,
    )
    async def update_llm_profile(profile_name: str, body: LLMProfileUpdateRequest):
        values = body.model_dump(
            mode="python",
            exclude={"secret"},
            exclude_unset=True,
        )
        secret = body.secret.get_secret_value() if body.secret is not None else None
        profile = context.llm_profiles.update(profile_name, values, secret=secret)
        return data_response(profile.model_dump(mode="json"))

    @router.post(
        "/api/v1/llm/profiles/{profile_name}/test",
        response_model=ApiResponse,
    )
    def test_llm_profile(profile_name: str):
        profile = context.llm_profiles.test_connection(profile_name)
        return data_response(profile.model_dump(mode="json"))

    return router
