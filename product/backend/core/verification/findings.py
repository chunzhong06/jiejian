# =============================================================================
# Finding 领域模型
#
# 定位
#   将单次 Evidence 的事实身份规范化为跨 Run 可复用的安全问题身份
#
# 职责
#   生成稳定 Finding ID｜约束 Occurrence 状态与证据引用｜拒绝未界定字段
#
# 边界
#   身份不包含 run_id、时间或易变响应；领域模型不读取 Evidence 文件或修改 Verdict。
#
# 调用链
#   PublishedResultReader → FindingInput → Finding application/storage
# =============================================================================

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from product.backend.core.identifiers import PROJECT_ID_PATTERN, RUN_ID_PATTERN
from product.backend.core.lifecycle import CaseVerdict, DomainModel

_FINDING_ID = r"^finding_[0-9a-f]{32}$"
_OCCURRENCE_ID = r"^occ_[0-9a-f]{32}$"
_SAFE_TEXT = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_SECRET_TEXT = re.compile(
    r"(?:bearer|authorization|cookie|credential|password|passwd|secret|token|api[_-]?key)",
    re.IGNORECASE,
)


def _normalize_text(value: str, field_name: str) -> str:
    value = value.strip()
    if not _SAFE_TEXT.fullmatch(value) or _SECRET_TEXT.search(value):
        raise ValueError(f"{field_name} must be a bounded non-secret token")
    return value


def _normalize_tokens(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    normalized = tuple(sorted({_normalize_text(value, field_name) for value in values}))
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _reject_secret_material(value: Any) -> None:
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, (tuple, list)):
            pending.extend(item)
        elif isinstance(item, str) and _SECRET_TEXT.search(item):
            raise ValueError("finding data must not contain secret material")


class FindingIdentity(DomainModel):
    """只由规范化稳定问题身份组成；不得包含 Run、Case、时间或实际对象值。"""

    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    permission_intent: tuple[str, ...] = Field(min_length=1, max_length=32)
    subject_class: tuple[str, ...] = Field(min_length=1, max_length=32)
    action: str = Field(min_length=1, max_length=128)
    resource_class: tuple[str, ...] = Field(min_length=1, max_length=64)
    resource_relation: tuple[str, ...] = Field(min_length=1, max_length=128)
    problem_category: str = Field(min_length=1, max_length=128)

    @field_validator("action", "problem_category")
    @classmethod
    def normalize_scalar(cls, value: str, info: Any) -> str:
        return _normalize_text(value, info.field_name)

    @field_validator(
        "permission_intent",
        "subject_class",
        "resource_class",
        "resource_relation",
    )
    @classmethod
    def normalize_tokens(cls, value: tuple[str, ...], info: Any) -> tuple[str, ...]:
        return _normalize_tokens(value, info.field_name)

    def canonical_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"schema_version"})

    def stable_key_sha256(self) -> str:
        encoded = json.dumps(
            self.canonical_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def finding_id(self) -> str:
        return f"finding_{self.stable_key_sha256()[:32]}"


class FindingInput(DomainModel):
    """从已验证 publication 提取的一条候选；Evidence 本文仍留在发布工件。"""

    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    run_id: str = Field(pattern=RUN_ID_PATTERN)
    evidence_id: str = Field(pattern=r"^ev_[0-9a-f]{20}$")
    case_id: str = Field(min_length=1, max_length=128)
    identity: FindingIdentity
    verdict: CaseVerdict
    severity: Literal["low", "medium", "high", "critical", "unknown"]
    object_context: dict[str, Any] = Field(default_factory=dict)
    coverage_context: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_input(self) -> FindingInput:
        _reject_secret_material(self.model_dump(mode="python"))
        return self


class OccurrenceStatus(StrEnum):
    APPEARED = "APPEARED"
    PRESENT = "PRESENT"
    DISAPPEARED = "DISAPPEARED"
    REAPPEARED = "REAPPEARED"
    CHANGED = "CHANGED"


class Finding(DomainModel):
    finding_id: str = Field(pattern=_FINDING_ID)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    identity: FindingIdentity
    first_seen_at_us: int = Field(ge=0)
    last_seen_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_identity(self) -> Finding:
        if self.finding_id != self.identity.finding_id() or self.project_id != self.identity.project_id:
            raise ValueError("finding ID does not match its stable identity")
        if self.last_seen_at_us < self.first_seen_at_us:
            raise ValueError("finding time order is invalid")
        return self


class FindingOccurrence(DomainModel):
    occurrence_id: str = Field(pattern=_OCCURRENCE_ID)
    finding_id: str = Field(pattern=_FINDING_ID)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    run_id: str = Field(pattern=RUN_ID_PATTERN)
    status: OccurrenceStatus
    verdict: CaseVerdict
    severity: Literal["low", "medium", "high", "critical", "unknown"]
    evidence_refs: tuple[str, ...] = Field(min_length=1, max_length=64)
    object_context: dict[str, Any] = Field(default_factory=dict)
    coverage_context: dict[str, Any] = Field(default_factory=dict)
    created_at_us: int = Field(ge=0)

    @field_validator("evidence_refs")
    @classmethod
    def normalize_evidence_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted(set(values)))
        if any(not re.fullmatch(r"^ev_[0-9a-f]{20}$", value) for value in normalized):
            raise ValueError("occurrence evidence_refs must contain Evidence IDs")
        return normalized

    @model_validator(mode="after")
    def validate_occurrence(self) -> FindingOccurrence:
        if self.finding_id != self.finding_id.strip() or self.project_id != self.project_id.strip():
            raise ValueError("occurrence identifiers must be normalized")
        _reject_secret_material(self.model_dump(mode="python"))
        return self


def occurrence_id_for(finding_id: str, run_id: str) -> str:
    """为同一 Finding/Run 生成幂等 Occurrence ID，不使用随机值或时间。"""

    return f"occ_{hashlib.sha256(f'{finding_id}:{run_id}'.encode('ascii')).hexdigest()[:32]}"
