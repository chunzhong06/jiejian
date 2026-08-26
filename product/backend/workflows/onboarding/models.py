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
