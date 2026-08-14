# 定位：首次使用目录选择和只读项目识别的 HTTP 适配器。
# 职责：解析请求、调用 onboarding 应用能力和返回脱敏版本化结果；不扫描、不执行目标。

from __future__ import annotations

from fastapi import APIRouter

from ...application.context import ApplicationContext
from ..responses import data_response
from ..schemas.common import ApiResponse
from ..schemas.onboarding import OnboardingInspectRequest
from ..schemas.onboarding import (
    OnboardingCredentialsRequest,
    OnboardingQuickCheckRequest,
    OnboardingSessionCreateRequest,
    OnboardingSessionUpdateRequest,
)
from ...onboarding.models import OnboardingConfirmations, OnboardingSessionUpdate


def build_onboarding_router(context: ApplicationContext) -> APIRouter:
    router = APIRouter()

    @router.post("/api/v1/onboarding/select-folder", response_model=ApiResponse)
    def select_folder():
        result = context.onboarding.select_folder()
        return data_response(result.model_dump(mode="json", exclude_none=True))

    @router.post("/api/v1/onboarding/inspect", response_model=ApiResponse)
    def inspect_folder(body: OnboardingInspectRequest):
        result = context.onboarding.inspect(body.path)
        return data_response(result.model_dump(mode="json"))

    @router.post("/api/v1/onboarding/sessions", response_model=ApiResponse, status_code=201)
    def create_session(body: OnboardingSessionCreateRequest):
        result = context.onboarding.create_session(body.path, body.project_name)
        return data_response(result.model_dump(mode="json"), status_code=201)

    @router.get("/api/v1/onboarding/sessions/{session_id}", response_model=ApiResponse)
    def get_session(session_id: str):
        return data_response(context.onboarding.get_session(session_id).model_dump(mode="json"))

    @router.patch("/api/v1/onboarding/sessions/{session_id}", response_model=ApiResponse)
    def update_session(session_id: str, body: OnboardingSessionUpdateRequest):
        values = body.model_dump(exclude_unset=True)
        confirmations = values.get("confirmations")
        if confirmations is not None:
            values["confirmations"] = OnboardingConfirmations.model_validate(confirmations, strict=True)
        result = context.onboarding.update_session(
            session_id, OnboardingSessionUpdate.model_validate(values, strict=True)
        )
        return data_response(result.model_dump(mode="json"))

    @router.post("/api/v1/onboarding/sessions/{session_id}/credentials", response_model=ApiResponse)
    def put_credentials(session_id: str, body: OnboardingCredentialsRequest):
        result = context.onboarding.put_credentials(
            session_id, body.primary.get_secret_value(), body.comparison.get_secret_value()
        )
        return data_response(result.model_dump(mode="json"))

    @router.post("/api/v1/onboarding/sessions/{session_id}/quick-check", response_model=ApiResponse, status_code=202)
    def quick_check(session_id: str, _body: OnboardingQuickCheckRequest):
        result = context.onboarding.quick_check(session_id)
        return data_response(result.model_dump(mode="json"), status_code=202)

    @router.post("/api/v1/onboarding/demo/start", response_model=ApiResponse)
    def start_demo():
        return data_response(context.demo.start().model_dump(mode="json"))

    @router.get("/api/v1/onboarding/demo", response_model=ApiResponse)
    def get_demo():
        return data_response(context.demo.status().model_dump(mode="json"))

    @router.post("/api/v1/onboarding/demo/stop", response_model=ApiResponse)
    def stop_demo():
        return data_response(context.demo.stop().model_dump(mode="json"))

    return router
