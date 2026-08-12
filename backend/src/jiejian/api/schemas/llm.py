"""模型服务设置的版本化、秘密不回显 API Schema。"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator

from ...contracts.llm.config import (
    LLMProviderType,
    PROFILE_NAME_PATTERN,
    normalize_llm_base_url,
    validate_secret_ref,
)
from .common import ApiModel


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
    secret: SecretStr | None = Field(default=None, exclude=True, repr=False)

    @model_validator(mode="after")
    def validate_secret_input(self) -> LLMProfileCreateRequest:
        if self.secret is not None and self.secret_ref is not None:
            raise ValueError("secret and secret_ref cannot be supplied together")
        return self


class LLMProfileUpdateRequest(ApiModel):
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


class LLMProfileResponse(LLMProfileBase):
    created_at_us: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)
    secret_configured: bool
    connection_status: Literal["testing", "configured", "available", "unavailable", "unknown"] = "unknown"
    tested_at_us: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    error_code: str | None = Field(default=None, max_length=64)
    error_message: str | None = Field(default=None, max_length=256)
