# Contract 分析 的分析结果纯模型。

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.contracts.models import ContractCandidate, ContractSourceType, Requirement, SourceReference
from product.backend.core.identifiers import CANDIDATE_ID_PATTERN, LONG_SLUG_ID_PATTERN, PROJECT_ID_PATTERN
from product.backend.core.lifecycle import ContractStatus
from product.backend.core.contracts.models import CandidateSuggestion
from product.backend.core.verification.permissions import PermissionRule


class AnalysisModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class AnalysisSeverity(StrEnum):
    WARNING = "WARNING"
    BLOCKING = "BLOCKING"


class AnalysisReasonCode(StrEnum):
    AMBIGUOUS_SOURCE = "AMBIGUOUS_SOURCE"
    UNSUPPORTED_SOURCE = "UNSUPPORTED_SOURCE"
    SOURCE_PATH_OUTSIDE_PROJECT = "SOURCE_PATH_OUTSIDE_PROJECT"
    SOURCE_SUFFIX_DENIED = "SOURCE_SUFFIX_DENIED"
    SOURCE_TOO_LARGE = "SOURCE_TOO_LARGE"
    SOURCE_HASH_MISMATCH = "SOURCE_HASH_MISMATCH"
    INVALID_OPENAPI = "INVALID_OPENAPI"
    DUPLICATE_CANDIDATE = "DUPLICATE_CANDIDATE"
    CONFLICTING_CANDIDATE = "CONFLICTING_CANDIDATE"
    RULE_UNEXECUTABLE = "RULE_UNEXECUTABLE"
    OBSERVER_UNAVAILABLE = "OBSERVER_UNAVAILABLE"
    REQUIREMENT_UNCOVERED = "REQUIREMENT_UNCOVERED"
    CONTRACT_RULE_DISAPPEARED = "CONTRACT_RULE_DISAPPEARED"
    ROUTE_CHANGED = "ROUTE_CHANGED"
    BEHAVIOR_CHANGED = "BEHAVIOR_CHANGED"
    LLM_REQUIREMENT_CONFLICT = "LLM_REQUIREMENT_CONFLICT"


class AnalysisIssue(AnalysisModel):
    code: AnalysisReasonCode
    severity: AnalysisSeverity
    subject_id: str = Field(min_length=1, max_length=1024)
    candidate_ids: tuple[str, ...] = Field(default=(), max_length=512)
    requirement_ids: tuple[str, ...] = Field(default=(), max_length=512)
    detail: str = Field(min_length=1, max_length=256)


class CandidateBatch(AnalysisModel):
    adapter: str = Field(min_length=1, max_length=64)
    candidates: tuple[ContractCandidate, ...] = Field(default=(), max_length=2048)
    issues: tuple[AnalysisIssue, ...] = Field(default=(), max_length=2048)
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class MergedCandidate(AnalysisModel):
    merged_id: str = Field(pattern=CANDIDATE_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    suggestion: CandidateSuggestion
    candidate_ids: tuple[str, ...] = Field(min_length=1, max_length=512)
    requirement_ids: tuple[str, ...] = Field(default=(), max_length=512)
    sources: tuple[SourceReference, ...] = Field(min_length=1, max_length=512)
    fingerprint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CandidateMergeResult(AnalysisModel):
    candidates: tuple[MergedCandidate, ...] = Field(default=(), max_length=2048)
    issues: tuple[AnalysisIssue, ...] = Field(default=(), max_length=2048)
    canonical_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
class ContractReviewAssessment(AnalysisModel):
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    contract_id: str = Field(pattern=LONG_SLUG_ID_PATTERN)
    version: int = Field(ge=1)
    status: ContractStatus
    eligible: bool
    blocking_issues: tuple[AnalysisIssue, ...] = Field(default=(), max_length=2048)
    warnings: tuple[AnalysisIssue, ...] = Field(default=(), max_length=2048)
    canonical_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

class RuleDiff(AnalysisModel):
    rule_id: str = Field(pattern=LONG_SLUG_ID_PATTERN)
    before: PermissionRule
    after: PermissionRule


class ProvenanceDelta(AnalysisModel):
    requirement_ids: tuple[str, ...] = Field(default=(), max_length=512)
    candidate_ids: tuple[str, ...] = Field(default=(), max_length=512)
    sources: tuple[SourceReference, ...] = Field(default=(), max_length=512)


class ContractVersionDiff(AnalysisModel):
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    contract_id: str = Field(pattern=LONG_SLUG_ID_PATTERN)
    from_version: int = Field(ge=1)
    to_version: int = Field(ge=1)
    from_status: ContractStatus
    to_status: ContractStatus
    added: tuple[PermissionRule, ...] = Field(default=(), max_length=2048)
    removed: tuple[PermissionRule, ...] = Field(default=(), max_length=2048)
    changed: tuple[RuleDiff, ...] = Field(default=(), max_length=2048)
    provenance_added: ProvenanceDelta
    provenance_removed: ProvenanceDelta
    canonical_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
