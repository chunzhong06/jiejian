# LLM profile 与显式连接测试 API；只适配请求并调用共享 profile 应用服务。
# 安全边界：响应不包含秘密正文，路由不直接连接 provider。

from __future__ import annotations

from fastapi import APIRouter
from pydantic import Field, SecretStr, field_validator, model_validator

from product.backend.composition import ApplicationCore
from product.backend.api.envelope import data_response
from product.backend.api.envelope import ApiResponse
from product.backend.infra.llm.catalog import LLMModelCatalog
from product.backend.infra.llm.config import LLMProviderType


def build_llm_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.get("/api/llm/settings", response_model=ApiResponse)
    async def get_llm_settings():
        return data_response(context.llm_profiles.get_settings().model_dump(mode="json"))

    @router.patch("/api/llm/settings", response_model=ApiResponse)
    async def patch_llm_settings(body: LLMSettingsRequest):
        settings = context.llm_profiles.update_settings(
            enabled=body.enabled,
            default_profile_name=body.default_profile_name,
        )
        return data_response(settings.model_dump(mode="json"))

    @router.post("/api/llm/models/discover", response_model=ApiResponse)
    async def discover_llm_models(body: LLMModelDiscoverRequest):
        secret = body.secret.get_secret_value()
        try:
            catalog = context.llm_profiles.discover_models(
                body.provider,
                secret,
                base_url=body.base_url,
                allow_local_http=body.allow_local_http,
            )
        finally:
            secret = ""
        return data_response(_catalog_response(catalog))

    @router.post("/api/llm/profiles/{profile_name}/models/refresh", response_model=ApiResponse)
    async def refresh_llm_models(profile_name: str):
        return data_response(_catalog_response(context.llm_profiles.refresh_models(profile_name)))

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

    @router.put("/api/llm/default-profile", response_model=ApiResponse)
    async def save_default_profile(body: LLMDefaultProfileRequest):
        values = body.model_dump(mode="python", exclude={"secret", "schema_version"}, exclude_none=True)
        secret = body.secret.get_secret_value() if body.secret is not None else None
        profile = context.llm_profiles.save_default_profile(values, secret=secret)
        return data_response(profile.model_dump(mode="json"))

    return router

"""模型服务设置的版本化、秘密不回显 API Schema。"""

from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator

from product.backend.infra.llm.config import LLMProviderType, PROFILE_NAME_PATTERN, normalize_llm_base_url, validate_secret_ref
from product.backend.api.envelope import ApiModel


class LLMSettingsRequest(ApiModel):
    schema_version: Literal["1"]
    enabled: bool
    default_profile_name: str | None = Field(default=None, pattern=PROFILE_NAME_PATTERN)


class LLMModelDiscoverRequest(ApiModel):
    schema_version: Literal["1"]
    provider: LLMProviderType
    secret: SecretStr = Field(exclude=True, repr=False)
    base_url: str | None = Field(default=None, max_length=2048)
    allow_local_http: bool = False

    @field_validator("provider", mode="before")
    @classmethod
    def parse_provider(cls, value: object) -> LLMProviderType:
        try:
            return value if isinstance(value, LLMProviderType) else LLMProviderType(value)
        except (TypeError, ValueError):
            raise ValueError("unsupported LLM provider") from None

    @model_validator(mode="after")
    def validate_provider_base(self) -> LLMModelDiscoverRequest:
        if self.provider is not LLMProviderType.OPENAI_COMPATIBLE and (
            self.base_url is not None or self.allow_local_http
        ):
            raise ValueError("正式供应商不接受自定义 base_url")
        return self


class LLMProfileBase(ApiModel):
    profile_name: str = Field(pattern=PROFILE_NAME_PATTERN)
    provider: LLMProviderType
    model: str = Field(min_length=1, max_length=256)
    reasoning_effort: str | None = Field(default=None, max_length=16)
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

    @model_validator(mode="after")
    def validate_formal_provider_base(self) -> LLMProfileBase:
        if self.provider is not LLMProviderType.OPENAI_COMPATIBLE and (
            self.base_url is not None or self.allow_local_http
        ):
            raise ValueError("正式供应商不接受自定义 base_url")
        return self


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
    reasoning_effort: str | None = Field(default=None, max_length=16)
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


class LLMDefaultProfileRequest(LLMProfileBase):
    schema_version: Literal["1"]
    # 普通保存的目标由全局设置服务端推导，不能由请求体选择 profile。
    profile_name: str | None = None
    secret: SecretStr | None = Field(default=None, exclude=True, repr=False)


def _catalog_response(catalog: LLMModelCatalog) -> dict[str, object]:
    return {
        "provider": catalog.provider.value,
        "models": [
            {
                "model": item.model,
                "display_name": item.display_name,
                "reasoning_options": list(item.reasoning_options),
                "reasoning_default_label": item.reasoning_default_label,
                "structured_output_mode": item.structured_output_mode,
            }
            for item in catalog.models
        ],
        "manual_model_allowed": catalog.manual_model_allowed,
        "truncated": catalog.truncated,
    }
