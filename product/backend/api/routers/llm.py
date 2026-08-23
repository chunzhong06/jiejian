# LLM profile 与显式连接测试 API；只适配请求并调用共享 profile 应用服务。
# 安全边界：响应不包含秘密正文，路由不直接连接 provider。

from __future__ import annotations

from fastapi import APIRouter

from product.backend.workflows.context import ApplicationCore
from product.backend.api.envelope import data_response
from product.backend.api.envelope import ApiResponse


def build_llm_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.get("/api/llm/profiles", response_model=ApiResponse)
    async def list_llm_profiles():
        return data_response(
            [item.model_dump(mode="json") for item in context.llm_profiles.list()]
        )

    @router.get(
        "/api/llm/profiles/{profile_name}",
        response_model=ApiResponse,
    )
    async def get_llm_profile(profile_name: str):
        return data_response(context.llm_profiles.get(profile_name).model_dump(mode="json"))

    @router.post(
        "/api/llm/profiles",
        response_model=ApiResponse,
        status_code=201,
    )
    async def create_llm_profile(body: LLMProfileCreateRequest):
        values = body.model_dump(mode="python", exclude={"secret"})
        values.pop("schema_version", None)
        secret = body.secret.get_secret_value() if body.secret is not None else None
        profile = context.llm_profiles.create(values, secret=secret)
        return data_response(profile.model_dump(mode="json"), status_code=201)

    @router.patch(
        "/api/llm/profiles/{profile_name}",
        response_model=ApiResponse,
    )
    async def update_llm_profile(profile_name: str, body: LLMProfileUpdateRequest):
        values = body.model_dump(
            mode="python",
            exclude={"secret"},
            exclude_unset=True,
        )
        values.pop("schema_version", None)
        secret = body.secret.get_secret_value() if body.secret is not None else None
        profile = context.llm_profiles.update(profile_name, values, secret=secret)
        return data_response(profile.model_dump(mode="json"))

    @router.post(
        "/api/llm/profiles/{profile_name}/test",
        response_model=ApiResponse,
    )
    def test_llm_profile(profile_name: str):
        profile = context.llm_profiles.test_connection(profile_name)
        return data_response(profile.model_dump(mode="json"))

    return router

"""模型服务设置的版本化、秘密不回显 API Schema。"""

from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator

from product.backend.infra.llm.config import LLMProviderType, PROFILE_NAME_PATTERN, normalize_llm_base_url, validate_secret_ref
from product.backend.api.envelope import ApiModel


class LLMProfileBase(ApiModel):
    profile_name: str = Field(pattern=PROFILE_NAME_PATTERN)
    provider: LLMProviderType
    model: str = Field(min_length=1, max_length=256)
    allow_local_http: bool = False
    base_url: str | None = Field(default=None, max_length=2048)
    timeout_ms: int = Field(default=30_000, ge=100, le=300_000)
    max_input_bytes: int = Field(default=131_072, ge=1, le=1_048_576)
    max_output_bytes: int = Field(default=65_536, ge=1, le=1_048_576)
    max_budget_microusd: int = Field(default=1_000_000, ge=0, le=1_000_000_000)
    enabled: bool = True
    secret_ref: str | None = Field(default=None, max_length=256)

    @field_validator("provider", mode="before")
    @classmethod
    def parse_provider(cls, value: object) -> LLMProviderType:
        if isinstance(value, LLMProviderType):
            return value
        if isinstance(value, str):
            try:
                return LLMProviderType(value)
            except ValueError:
                pass
        raise ValueError("unsupported LLM provider")

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return normalize_llm_base_url(
            value,
            allow_local_http=bool(info.data.get("allow_local_http", False)),
        )

    @field_validator("secret_ref")
    @classmethod
    def validate_secret_reference(cls, value: str | None) -> str | None:
        return None if value is None else validate_secret_ref(value)


class LLMProfileCreateRequest(LLMProfileBase):
    schema_version: Literal["1"]
    secret: SecretStr | None = Field(default=None, exclude=True, repr=False)

    @model_validator(mode="after")
    def validate_secret_input(self) -> LLMProfileCreateRequest:
        if self.secret is not None and self.secret_ref is not None:
            raise ValueError("secret and secret_ref cannot be supplied together")
        return self


class LLMProfileUpdateRequest(ApiModel):
    schema_version: Literal["1"]
    provider: LLMProviderType | None = None
    model: str | None = Field(default=None, min_length=1, max_length=256)
    allow_local_http: bool | None = None
    base_url: str | None = Field(default=None, max_length=2048)
    timeout_ms: int | None = Field(default=None, ge=100, le=300_000)
    max_input_bytes: int | None = Field(default=None, ge=1, le=1_048_576)
    max_output_bytes: int | None = Field(default=None, ge=1, le=1_048_576)
    max_budget_microusd: int | None = Field(default=None, ge=0, le=1_000_000_000)
    enabled: bool | None = None
    secret_ref: str | None = Field(default=None, max_length=256)
    secret: SecretStr | None = Field(default=None, exclude=True, repr=False)

    @model_validator(mode="after")
    def validate_secret_input(self) -> LLMProfileUpdateRequest:
        if self.secret is not None and self.secret_ref is not None:
            raise ValueError("secret and secret_ref cannot be supplied together")
        return self

    @field_validator("base_url")
    @classmethod
    def validate_base_url_syntax(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_llm_base_url(
            value,
            allow_local_http=True,
            require_local_http_authorization=False,
        )

    @field_validator("secret_ref")
    @classmethod
    def validate_secret_reference(cls, value: str | None) -> str | None:
        return None if value is None else validate_secret_ref(value)


class LLMProfileResponse(ApiModel):
    profile_name: str = Field(pattern=PROFILE_NAME_PATTERN)
    provider: LLMProviderType
    model: str = Field(min_length=1, max_length=256)
    allow_local_http: bool = False
    base_url: str | None = Field(default=None, max_length=2048)
    timeout_ms: int = Field(default=30_000, ge=100, le=300_000)
    max_input_bytes: int = Field(default=131_072, ge=1, le=1_048_576)
    max_output_bytes: int = Field(default=65_536, ge=1, le=1_048_576)
    max_budget_microusd: int = Field(default=1_000_000, ge=0, le=1_000_000_000)
    enabled: bool = True
    secret_ref: str | None = Field(default=None, max_length=256)
    created_at_us: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)
    secret_configured: bool
    connection_status: Literal["testing", "configured", "available", "unavailable", "unknown"] = "unknown"
    tested_at_us: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    error_code: str | None = Field(default=None, max_length=64)
    error_message: str | None = Field(default=None, max_length=256)
