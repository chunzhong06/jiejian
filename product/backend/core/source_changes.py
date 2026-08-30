# =============================================================================
# 源码变化与权限实现影响核心模型
#
# 定位
#   受控源码重分析、Agent 变更声明和长期权限实现映射之间的确定性事实边界。
#
# 职责
#   冻结文件指纹快照｜约束真实增删改｜表达逐 Intent 的直接实现影响或映射待审。
#
# 边界
#   不保存源码正文、diff、Git 凭据或命令；不修改 PermissionIntent revision、hash 或 policy epoch。
#
# 调用链
#   SourceChangeService / analyzer → Core models → Storage / application projection
# =============================================================================

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from product.backend.core.identifiers import PROJECT_ID_PATTERN, SHA256_PATTERN


_SNAPSHOT_ID_PATTERN = r"^snp_[0-9a-f]{32}$"
_CHANGE_ID_PATTERN = r"^chg_[0-9a-f]{32}$"
_INTENT_ID_PATTERN = r"^pin_[0-9a-f]{32}$"
_DRIVE_PATH = re.compile(r"^[A-Za-z]:/")
_REASON_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


class SourceChangeModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


def normalize_relative_source_path(value: str) -> str:
    """把外部线索限制为授权源码根下的规范相对路径。"""

    normalized = value.replace("\\", "/")
    if (
        not normalized
        or normalized != normalized.strip()
        or len(normalized) > 1024
        or normalized.startswith("/")
        or _DRIVE_PATH.match(normalized) is not None
        or any(ord(char) < 32 for char in normalized)
    ):
        raise ValueError("source path must be a bounded relative path")
    parts = normalized.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        raise ValueError("source path cannot escape or contain empty segments")
    return "/".join(parts)


def _canonical_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SourceFileFingerprint(SourceChangeModel):
    relative_path: str = Field(min_length=1, max_length=1024)
    content_sha256: str = Field(pattern=SHA256_PATTERN)

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        return normalize_relative_source_path(value)


def source_fingerprint(files: tuple[SourceFileFingerprint, ...]) -> str:
    digest = hashlib.sha256()
    for item in files:
        digest.update(item.relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(item.content_sha256))
    return digest.hexdigest()


def source_snapshot_id(project_id: str, fingerprint: str) -> str:
    digest = hashlib.sha256(f"{project_id}\0{fingerprint}".encode("utf-8")).hexdigest()
    return f"snp_{digest[:32]}"


class SourceRevisionSnapshot(SourceChangeModel):
    snapshot_id: str = Field(pattern=_SNAPSHOT_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    source_fingerprint: str = Field(pattern=SHA256_PATTERN)
    understanding_revision: int = Field(ge=0, le=1_000_000)
    files: tuple[SourceFileFingerprint, ...] = Field(default=(), max_length=512)
    created_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_snapshot(self) -> SourceRevisionSnapshot:
        ordered = tuple(sorted(self.files, key=lambda item: (item.relative_path.casefold(), item.relative_path)))
        identities = tuple(item.relative_path.casefold() for item in self.files)
        if self.files != ordered or len(set(identities)) != len(identities):
            raise ValueError("snapshot files must be sorted and path-unique")
        if self.source_fingerprint != source_fingerprint(self.files):
            raise ValueError("snapshot source fingerprint is inconsistent")
        if self.snapshot_id != source_snapshot_id(self.project_id, self.source_fingerprint):
            raise ValueError("snapshot id is inconsistent")
        return self


class ChangeManifest(SourceChangeModel):
    change_id: str = Field(pattern=_CHANGE_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    reason: str = Field(min_length=1, max_length=512)
    claimed_paths: tuple[str, ...] = Field(default=(), max_length=128)
    submitted_by: str = Field(min_length=1, max_length=128)
    created_at_us: int = Field(ge=0)

    @field_validator("reason", "submitted_by")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if value != value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError("manifest text must be trimmed printable text")
        return value

    @field_validator("claimed_paths")
    @classmethod
    def validate_claimed_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(normalize_relative_source_path(value) for value in values)
        ordered = tuple(sorted(normalized, key=lambda item: (item.casefold(), item)))
        if normalized != ordered or len({item.casefold() for item in normalized}) != len(normalized):
            raise ValueError("claimed paths must be sorted and unique")
        return normalized


class SourceChangeSet(SourceChangeModel):
    change_id: str = Field(pattern=_CHANGE_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    previous_snapshot_id: str | None = Field(default=None, pattern=_SNAPSHOT_ID_PATTERN)
    current_snapshot_id: str = Field(pattern=_SNAPSHOT_ID_PATTERN)
    status: Literal["COMPARABLE", "NO_BASELINE"]
    added_paths: tuple[str, ...] = Field(default=(), max_length=512)
    modified_paths: tuple[str, ...] = Field(default=(), max_length=512)
    removed_paths: tuple[str, ...] = Field(default=(), max_length=512)
    change_fingerprint: str = Field(pattern=SHA256_PATTERN)
    created_at_us: int = Field(ge=0)

    @field_validator("added_paths", "modified_paths", "removed_paths")
    @classmethod
    def validate_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(normalize_relative_source_path(value) for value in values)
        ordered = tuple(sorted(normalized, key=lambda item: (item.casefold(), item)))
        if normalized != ordered or len({item.casefold() for item in normalized}) != len(normalized):
            raise ValueError("change paths must be sorted and unique")
        return normalized

    def canonical_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"change_fingerprint", "created_at_us"})

    @property
    def changed_paths(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                (*self.added_paths, *self.modified_paths, *self.removed_paths),
                key=lambda item: (item.casefold(), item),
            )
        )

    @model_validator(mode="after")
    def validate_change_set(self) -> SourceChangeSet:
        path_groups = (self.added_paths, self.modified_paths, self.removed_paths)
        flattened = tuple(path for group in path_groups for path in group)
        if len({path.casefold() for path in flattened}) != len(flattened):
            raise ValueError("change path groups must be disjoint")
        if self.status == "NO_BASELINE":
            if self.previous_snapshot_id is not None or flattened:
                raise ValueError("no-baseline change set cannot claim a diff")
        elif self.previous_snapshot_id is None:
            raise ValueError("comparable change set requires previous snapshot")
        if self.change_fingerprint != _canonical_sha256(self.canonical_payload()):
            raise ValueError("change fingerprint is inconsistent")
        return self


class IntentChangeImpact(SourceChangeModel):
    intent_id: str = Field(pattern=_INTENT_ID_PATTERN)
    intent_revision: int = Field(ge=1)
    intent_hash: str = Field(pattern=SHA256_PATTERN)
    classification: Literal[
        "DIRECTLY_AFFECTED",
        "MAPPING_REVIEW_REQUIRED",
        "NO_DIRECT_EVIDENCE",
    ]
    message: str
    relevant_paths: tuple[str, ...] = Field(default=(), max_length=128)
    reason_codes: tuple[str, ...] = Field(default=(), max_length=32)
    binding_updated_at_us: int | None = Field(default=None, ge=0)

    @field_validator("relevant_paths")
    @classmethod
    def validate_relevant_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(normalize_relative_source_path(value) for value in values)
        ordered = tuple(sorted(normalized, key=lambda item: (item.casefold(), item)))
        if normalized != ordered or len({item.casefold() for item in normalized}) != len(normalized):
            raise ValueError("impact paths must be sorted and unique")
        return normalized

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values) or any(_REASON_CODE.fullmatch(value) is None for value in values):
            raise ValueError("impact reason codes must be unique bounded tokens")
        return values

    @model_validator(mode="after")
    def validate_message(self) -> IntentChangeImpact:
        messages = {
            "DIRECTLY_AFFECTED": "发现直接实现关联",
            "MAPPING_REVIEW_REQUIRED": "实现映射需要人工复核",
            "NO_DIRECT_EVIDENCE": "当前没有发现直接实现关联",
        }
        if self.message != messages[self.classification]:
            raise ValueError("impact message is inconsistent")
        if not self.reason_codes:
            raise ValueError("intent impact requires reason codes")
        if (
            self.classification != "MAPPING_REVIEW_REQUIRED"
            and self.binding_updated_at_us is None
        ):
            raise ValueError("resolved impact requires the assessed binding revision marker")
        return self


class ChangeImpactAssessment(SourceChangeModel):
    change_id: str = Field(pattern=_CHANGE_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    change_fingerprint: str = Field(pattern=SHA256_PATTERN)
    complete: bool
    reason_codes: tuple[str, ...] = Field(default=(), max_length=32)
    impacts: tuple[IntentChangeImpact, ...] = Field(default=(), max_length=1024)
    impact_fingerprint: str = Field(pattern=SHA256_PATTERN)
    created_at_us: int = Field(ge=0)

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values) or any(_REASON_CODE.fullmatch(value) is None for value in values):
            raise ValueError("assessment reason codes must be unique bounded tokens")
        return values

    def canonical_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"impact_fingerprint", "created_at_us"})

    @model_validator(mode="after")
    def validate_assessment(self) -> ChangeImpactAssessment:
        ordered = tuple(sorted(self.impacts, key=lambda item: item.intent_id))
        identities = tuple(item.intent_id for item in self.impacts)
        if self.impacts != ordered or len(set(identities)) != len(identities):
            raise ValueError("intent impacts must be sorted and unique")
        if self.complete == bool(self.reason_codes):
            raise ValueError("only incomplete assessments carry assessment reason codes")
        if not self.complete and any(
            item.classification == "NO_DIRECT_EVIDENCE" for item in self.impacts
        ):
            raise ValueError("incomplete assessment cannot claim no direct evidence")
        if self.impact_fingerprint != _canonical_sha256(self.canonical_payload()):
            raise ValueError("impact fingerprint is inconsistent")
        return self


class RevalidationPlan(SourceChangeModel):
    """把一次变化映射为既有权限考题的重验要求，不裁剪当前完整 Coverage。"""

    change_id: str = Field(pattern=_CHANGE_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    impact_fingerprint: str = Field(pattern=SHA256_PATTERN)
    required_intent_ids: tuple[str, ...] = Field(default=(), max_length=4096)
    source_fingerprint: str = Field(pattern=SHA256_PATTERN)
    full_active_scope: Literal[True] = True

    @field_validator("required_intent_ids")
    @classmethod
    def validate_required_intent_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if (
            values != tuple(sorted(values))
            or len(set(values)) != len(values)
            or any(re.fullmatch(_INTENT_ID_PATTERN, value) is None for value in values)
        ):
            raise ValueError("required intent IDs must be unique and sorted")
        return values


def source_change_fingerprint(payload: dict[str, Any]) -> str:
    return _canonical_sha256(payload)


def change_impact_fingerprint(payload: dict[str, Any]) -> str:
    return _canonical_sha256(payload)


__all__ = [
    "ChangeImpactAssessment",
    "ChangeManifest",
    "IntentChangeImpact",
    "RevalidationPlan",
    "SourceChangeSet",
    "SourceFileFingerprint",
    "SourceRevisionSnapshot",
    "change_impact_fingerprint",
    "normalize_relative_source_path",
    "source_change_fingerprint",
    "source_fingerprint",
    "source_snapshot_id",
]
