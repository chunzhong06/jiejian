# 首次使用目录选择与只读识别请求模型。

from __future__ import annotations

from pydantic import Field, SecretStr

from .common import ApiModel


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
