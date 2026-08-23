# 定位：首次使用项目识别的版本化、脱敏结果和安全预算模型。
# 职责：定义选择状态、候选说明、缺项和扫描边界；不读取文件或调用外部系统。

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OnboardingModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class DiscoveryLimits(OnboardingModel):
    max_depth: int = Field(default=2, ge=0, le=2)
    max_entries: int = Field(default=256, ge=1, le=256)
    max_file_bytes: int = Field(default=262_144, ge=1, le=262_144)
    max_total_bytes: int = Field(default=1_048_576, ge=1, le=1_048_576)
    max_candidates: int = Field(default=32, ge=1, le=32)


class DiscoveryCandidate(OnboardingModel):
    label: str = Field(min_length=1, max_length=128)
    command: str = Field(min_length=1, max_length=256)
    source: str = Field(min_length=1, max_length=256)
    confirmation_required: Literal[True] = True
    executed: Literal[False] = False
    safety_note: str = Field(min_length=1, max_length=256)


class DiscoveryHint(OnboardingModel):
    detail: str = Field(min_length=1, max_length=256)
    source: str = Field(min_length=1, max_length=128)
    confirmation_required: Literal[True] = True


class DiscoveryMissingItem(OnboardingModel):
    key: Literal[
        "startup",
        "target_address",
        "test_accounts",
        "authorized_scope",
        "recovery",
    ]
    label: str = Field(min_length=1, max_length=64)
    state: Literal["待确认", "缺少"]
    reason: str = Field(min_length=1, max_length=256)
    confirmation_required: Literal[True] = True


class DiscoveryWarning(OnboardingModel):
    code: Literal[
        "REPARSE_SKIPPED",
        "READ_SKIPPED",
        "UNSUPPORTED_FORMAT",
        "DEPTH_LIMIT",
    ]
    message: str = Field(min_length=1, max_length=256)


class DiscoveryResult(OnboardingModel):
    detected_types: tuple[str, ...] = Field(default=(), max_length=32)
    start_candidates: tuple[DiscoveryCandidate, ...] = Field(default=(), max_length=32)
    config_hints: tuple[DiscoveryHint, ...] = Field(default=(), max_length=64)
    interface_hints: tuple[DiscoveryHint, ...] = Field(default=(), max_length=32)
    auth_hints: tuple[DiscoveryHint, ...] = Field(default=(), max_length=32)
    missing_items: tuple[DiscoveryMissingItem, ...] = Field(min_length=5, max_length=5)
    warnings: tuple[DiscoveryWarning, ...] = Field(default=(), max_length=64)


class FolderSelectionResult(OnboardingModel):
    status: Literal["selected", "cancelled", "unavailable"]
    path: str | None = Field(default=None, min_length=1, max_length=32_768)
    message: str | None = Field(default=None, min_length=1, max_length=256)


class OnboardingConfirmations(OnboardingModel):
    app_started: bool = False
    target_authorized: bool = False
    recovery_confirmed: bool = False
    dangerous_inference_confirmed: bool = False


class OnboardingSession(OnboardingModel):
    session_id: str = Field(pattern=r"^onb_[0-9a-f]{32}$")
    revision: int = Field(default=0, ge=0, le=1_000_000)
    status: Literal["DRAFT", "READY", "SUBMITTED"] = "DRAFT"
    source_path: str = Field(min_length=1, max_length=32_768)
    project_name: str = Field(min_length=1, max_length=128)
    mode: Literal["quick"] = "quick"
    target_address: str | None = Field(default=None, max_length=256)
    primary_display_name: str | None = Field(default=None, max_length=64)
    comparison_display_name: str | None = Field(default=None, max_length=64)
    primary_resource_id: str | None = Field(default=None, max_length=128)
    comparison_resource_id: str | None = Field(default=None, max_length=128)
    read_only_path_template: str | None = Field(default=None, max_length=512)
    recovery_path: str | None = Field(default=None, max_length=512)
    startup_candidate_source: str | None = Field(default=None, max_length=256)
    confirmations: OnboardingConfirmations = Field(default_factory=OnboardingConfirmations)
    primary_secret_ref: str = Field(pattern=r"^env:JIEJIAN_ONB_[A-Z0-9_]{1,110}_PRIMARY$")
    comparison_secret_ref: str = Field(pattern=r"^env:JIEJIAN_ONB_[A-Z0-9_]{1,110}_COMPARISON$")
    project_id: str = Field(pattern=r"^onboarding_[a-z0-9_-]{1,55}$")
    submitted_run_id: str | None = Field(default=None, pattern=r"^run_[0-9a-f]{32}$")
    submitted_job_id: str | None = Field(default=None, pattern=r"^job_[0-9a-f]{32}$")


class OnboardingSessionView(OnboardingModel):
    session_id: str
    revision: int
    status: Literal["DRAFT", "READY", "SUBMITTED"]
    source_path: str
    project_name: str
    mode: Literal["quick"]
    target_address: str | None = None
    primary_display_name: str | None = None
    comparison_display_name: str | None = None
    primary_resource_id: str | None = None
    comparison_resource_id: str | None = None
    read_only_path_template: str | None = None
    recovery_path: str | None = None
    startup_candidate_source: str | None = None
    confirmations: OnboardingConfirmations
    primary_configured: bool
    comparison_configured: bool
    missing_items: tuple[str, ...] = ()


class OnboardingSessionUpdate(OnboardingModel):
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
    confirmations: OnboardingConfirmations | None = None


class OnboardingCredentialStatus(OnboardingModel):
    primary_configured: bool
    comparison_configured: bool


class OnboardingQuickCheckResult(OnboardingModel):
    session: OnboardingSessionView
    project_id: str
    run_id: str
    job_id: str
    created: bool
