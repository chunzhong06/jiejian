# =============================================================================
# 应用理解核心模型
#
# 定位
#   普通用户接入流程、持久化仓储与 API 之间共享的不可变应用理解事实
#
# 职责
#   约束连接与授权状态｜定义角色/动作候选及结构证据｜校验 revision 与时间不变量
#
# 边界
#   候选不是权限结论；本模块不读取源码、不访问网络，也不生成 Profile、Contract 或执行计划。
#
# 调用链
#   Application Understanding workflow / analyzer → Core models → Storage / API projection
# =============================================================================

from __future__ import annotations

import hashlib
import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from product.backend.core.identifiers import PROJECT_ID_PATTERN, SHA256_PATTERN


def canonical_role_key(value: str) -> str:
    """把技术角色名和用户补充名称折叠为稳定、可持久化的比较键。"""

    cleaned = value.strip().removesuffix("Role").removesuffix("_role").casefold()
    key = re.sub(r"[^\w]+", "_", cleaned, flags=re.UNICODE).strip("_")
    if not key or key in {
        "role",
        "roles",
        "scope",
        "scopes",
        "permission",
        "permissions",
    }:
        raise ValueError("role name does not produce a stable canonical key")
    return key[:128]


def candidate_id(kind: Literal["role", "action"], canonical_key: str) -> str:
    """候选身份只由类型和 canonical key 决定，避免重新分析改变引用。"""

    digest = hashlib.sha256(
        f"{kind}\0{canonical_key}".encode("utf-8")
    ).hexdigest()[:32]
    return f"{kind}_{digest}"


class UnderstandingModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class CandidateDecision(StrEnum):
    PROPOSED = "PROPOSED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class CandidateOrigin(StrEnum):
    DETECTED = "DETECTED"
    MANUAL = "MANUAL"


class CandidateConfidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ActionRiskHint(StrEnum):
    READ = "READ"
    WRITE = "WRITE"
    DELETE = "DELETE"
    ADMIN = "ADMIN"
    UNKNOWN = "UNKNOWN"


class CandidateEvidence(UnderstandingModel):
    relative_path: str = Field(min_length=1, max_length=1024)
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    symbol: str | None = Field(default=None, min_length=1, max_length=256)
    detector: str = Field(min_length=1, max_length=64)
    content_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_line_order(self) -> CandidateEvidence:
        if self.line_end < self.line_start:
            raise ValueError("candidate evidence line range is reversed")
        return self


class RoleCandidate(UnderstandingModel):
    candidate_id: str = Field(pattern=r"^role_[0-9a-f]{32}$")
    canonical_key: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=128)
    confidence: CandidateConfidence
    decision: CandidateDecision = CandidateDecision.PROPOSED
    origin: CandidateOrigin = CandidateOrigin.DETECTED
    stale: bool = False
    evidence: tuple[CandidateEvidence, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def validate_origin_evidence(self) -> RoleCandidate:
        if self.origin is CandidateOrigin.DETECTED and not self.evidence:
            raise ValueError("detected role candidate requires evidence")
        return self


class ActionCandidate(UnderstandingModel):
    candidate_id: str = Field(pattern=r"^action_[0-9a-f]{32}$")
    canonical_key: str = Field(min_length=1, max_length=256)
    display_name: str = Field(min_length=1, max_length=256)
    confidence: CandidateConfidence
    risk_hint: ActionRiskHint = ActionRiskHint.UNKNOWN
    decision: CandidateDecision = CandidateDecision.PROPOSED
    origin: CandidateOrigin = CandidateOrigin.DETECTED
    stale: bool = False
    evidence: tuple[CandidateEvidence, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def validate_origin_evidence(self) -> ActionCandidate:
        if self.origin is CandidateOrigin.DETECTED and not self.evidence:
            raise ValueError("detected action candidate requires evidence")
        return self


class ApplicationUnderstanding(UnderstandingModel):
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    source_root: str = Field(min_length=1, max_length=32_768)
    confirmed_endpoint: str | None = Field(default=None, min_length=1, max_length=2048)
    endpoint_source_fingerprint: str | None = Field(default=None, pattern=SHA256_PATTERN)
    endpoint_confirmed_at_us: int | None = Field(default=None, ge=0)
    endpoint_last_checked_at_us: int | None = Field(default=None, ge=0)
    endpoint_reachable: bool | None = None
    source_analysis_authorized: bool = False
    source_analysis_authorized_at_us: int | None = Field(default=None, ge=0)
    source_fingerprint: str | None = Field(default=None, pattern=SHA256_PATTERN)
    analysis_completed_at_us: int | None = Field(default=None, ge=0)
    role_candidates: tuple[RoleCandidate, ...] = Field(default=(), max_length=256)
    action_candidates: tuple[ActionCandidate, ...] = Field(default=(), max_length=512)
    revision: int = Field(default=0, ge=0, le=1_000_000)
    created_at_us: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_state_pairs(self) -> ApplicationUnderstanding:
        endpoint_values = (
            self.confirmed_endpoint,
            self.endpoint_source_fingerprint,
            self.endpoint_confirmed_at_us,
            self.endpoint_last_checked_at_us,
            self.endpoint_reachable,
        )
        if any(value is not None for value in endpoint_values) and any(
            value is None for value in endpoint_values
        ):
            raise ValueError("confirmed endpoint state must be complete")
        if self.source_analysis_authorized != (
            self.source_analysis_authorized_at_us is not None
        ):
            raise ValueError("source analysis authorization state is inconsistent")
        if (self.source_fingerprint is None) != (
            self.analysis_completed_at_us is None
        ):
            raise ValueError("source analysis completion state is inconsistent")
        if self.source_fingerprint is not None and not self.source_analysis_authorized:
            raise ValueError("source analysis result requires explicit authorization")
        if self.updated_at_us < self.created_at_us:
            raise ValueError("application understanding update precedes creation")
        return self
