# 首次使用与演示 API：只负责请求适配、ApplicationCore 调用和版本化脱敏响应。
# 安全边界：选择目录不扫描，识别只经受限 onboarding，路由本身不执行目标。

from __future__ import annotations

from fastapi import APIRouter

from product.backend.workflows.context import ApplicationCore
from product.backend.api.envelope import data_response
from product.backend.api.envelope import ApiResponse
from product.backend.workflows.onboarding.models import DemoVariant, OnboardingConfirmations, OnboardingSessionUpdate


def build_onboarding_router(context: ApplicationCore) -> APIRouter:
    """构造首次使用与演示路由；所有业务和安全判断委托给 ApplicationCore。"""

    router = APIRouter()

    @router.post("/api/onboarding/select-folder", response_model=ApiResponse)
    def select_folder():
        result = context.onboarding.select_folder()
        return data_response(result.model_dump(mode="json", exclude_none=True))

    @router.post("/api/onboarding/inspect", response_model=ApiResponse)
    def inspect_folder(body: OnboardingInspectRequest):
        result = context.onboarding.inspect(body.path)
        return data_response(result.model_dump(mode="json"))

    @router.post("/api/onboarding/sessions", response_model=ApiResponse, status_code=201)
    def create_session(body: OnboardingSessionCreateRequest):
        result = context.onboarding.create_session(body.path, body.project_name)
        return data_response(result.model_dump(mode="json"), status_code=201)

    @router.get("/api/onboarding/sessions/{session_id}", response_model=ApiResponse)
    def get_session(session_id: str):
        return data_response(context.onboarding.get_session(session_id).model_dump(mode="json"))

    @router.patch("/api/onboarding/sessions/{session_id}", response_model=ApiResponse)
    def update_session(session_id: str, body: OnboardingSessionUpdateRequest):
        values = body.model_dump(exclude_unset=True)
        confirmations = values.get("confirmations")
        if confirmations is not None:
            values["confirmations"] = OnboardingConfirmations.model_validate(confirmations, strict=True)
        result = context.onboarding.update_session(
            session_id, OnboardingSessionUpdate.model_validate(values, strict=True)
        )
        return data_response(result.model_dump(mode="json"))

    @router.post("/api/onboarding/sessions/{session_id}/credentials", response_model=ApiResponse)
    def put_credentials(session_id: str, body: OnboardingCredentialsRequest):
        result = context.onboarding.put_credentials(
            session_id, body.primary.get_secret_value(), body.comparison.get_secret_value()
        )
        return data_response(result.model_dump(mode="json"))

    @router.post("/api/onboarding/sessions/{session_id}/quick-check", response_model=ApiResponse, status_code=202)
    def quick_check(session_id: str, _body: OnboardingQuickCheckRequest):
        result = context.onboarding.quick_check(session_id)
        return data_response(result.model_dump(mode="json"), status_code=202)

    @router.post("/api/onboarding/demo/start", response_model=ApiResponse)
    def start_demo(body: OnboardingDemoStartRequest):
        return data_response(context.demo.start(body.variant).model_dump(mode="json"))

    @router.get("/api/onboarding/demo", response_model=ApiResponse)
    def get_demo():
        return data_response(context.demo.status().model_dump(mode="json"))

    @router.post("/api/onboarding/demo/stop", response_model=ApiResponse)
    def stop_demo():
        return data_response(context.demo.stop().model_dump(mode="json"))

    return router

# 请求模型留在传输层，不把 FastAPI/Pydantic 约束泄漏到 onboarding 领域能力。

from pydantic import Field, SecretStr

from product.backend.api.envelope import ApiModel


class OnboardingInspectRequest(ApiModel):
    path: str = Field(min_length=1, max_length=32_768)


class OnboardingSessionCreateRequest(ApiModel):
    path: str = Field(min_length=1, max_length=32_768)
    project_name: str = Field(min_length=1, max_length=128)


class OnboardingSessionUpdateRequest(ApiModel):
    revision: int = Field(ge=0, le=1_000_000)
    project_name: str | None = Field(default=None, min_length=1, max_length=128)
    target_address: str | None = Field(default=None, max_length=256)
    primary_display_name: str | None = Field(default=None, max_length=64)
    comparison_display_name: str | None = Field(default=None, max_length=64)
    primary_resource_id: str | None = Field(default=None, max_length=128)
    comparison_resource_id: str | None = Field(default=None, max_length=128)
    read_only_path_template: str | None = Field(default=None, max_length=512)
    recovery_path: str | None = Field(default=None, max_length=512)
    startup_candidate_source: str | None = Field(default=None, max_length=256)
    confirmations: dict[str, bool] | None = None


class OnboardingCredentialsRequest(ApiModel):
    primary: SecretStr = Field(min_length=1, max_length=4096, exclude=True, repr=False)
    comparison: SecretStr = Field(min_length=1, max_length=4096, exclude=True, repr=False)


class OnboardingQuickCheckRequest(ApiModel):
    pass


class OnboardingDemoStartRequest(ApiModel):
    variant: DemoVariant
