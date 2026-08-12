# 阶段 5 契约需求、候选与版本治理模型。

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..domain.identifiers import (
    CANDIDATE_ID_PATTERN,
    LONG_SLUG_ID_PATTERN,
    PROJECT_ID_PATTERN,
    REQUIREMENT_ID_PATTERN,
    SHA256_PATTERN,
)
from ..domain.lifecycle import ContractStatus
from ..verification.models import ContractRule, SecurityContract


class ContractSourceType(StrEnum):
    REQUIREMENT_TEXT = "requirement_text"
    PROJECT_CONFIG = "project_config"
    RECORDING_FLOW = "recording_flow"
    STATIC_ANALYSIS = "static_analysis"
    LLM = "llm"


class ContractAuditAction(StrEnum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    ACTIVATED = "ACTIVATED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class GovernanceModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    schema_version: Literal["1"] = "1"


class SourceReference(GovernanceModel):
    source_type: ContractSourceType
    locator: str = Field(min_length=1, max_length=1024)
    content_sha256: str = Field(pattern=SHA256_PATTERN)

    @field_validator("locator")
    @classmethod
    def validate_locator(cls, value: str) -> str:
        if value != value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError("source locator must be trimmed and contain no controls")
        return value


class Requirement(GovernanceModel):
    requirement_id: str = Field(pattern=REQUIREMENT_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    source: SourceReference
    text: str = Field(min_length=1, max_length=16_384)
    security_tags: tuple[str, ...] = Field(default=(), max_length=64)
    created_by: str = Field(min_length=1, max_length=128)
    created_at_us: int = Field(ge=0)

    @field_validator("text", "created_by")
    @classmethod
    def validate_trimmed_text(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("audit text must be trimmed")
        return value

    @field_validator("security_tags")
    @classmethod
    def validate_security_tags(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values) or any(
            not value
            or len(value) > 64
            or not value[0].islower()
            or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for char in value)
            for value in values
        ):
            raise ValueError("security tags must be unique lowercase slugs")
        return values


class LLMGenerationMetadata(GovernanceModel):
    provider_id: str = Field(min_length=1, max_length=128)
    model_id: str = Field(min_length=1, max_length=128)
    adapter_version: str = Field(min_length=1, max_length=32)
    prompt_template_id: str = Field(min_length=1, max_length=128)
    prompt_template_version: str = Field(min_length=1, max_length=32)
    prompt_template_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provenance_schema_version: Literal["2"] | None = None
    provider: str | None = Field(default=None, min_length=1, max_length=32)
    profile_name: str | None = Field(default=None, min_length=1, max_length=128)
    model: str | None = Field(default=None, min_length=1, max_length=256)
    prompt_version: str | None = Field(default=None, min_length=1, max_length=32)
    started_at_us: int | None = Field(default=None, ge=0)
    duration_us: int | None = Field(default=None, ge=0)
    budget_limit_microusd: int | None = Field(default=None, ge=0, le=1_000_000_000)
    estimated_cost_microusd: int | None = Field(default=None, ge=0, le=1_000_000_000)

    @field_validator(
        "provider_id",
        "model_id",
        "adapter_version",
        "prompt_template_id",
        "prompt_template_version",
        "provider",
        "profile_name",
        "model",
        "prompt_version",
    )
    @classmethod
    def validate_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value != value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError("LLM generation metadata text must be trimmed and printable")
        return value


class ContractCandidate(GovernanceModel):
    candidate_id: str = Field(pattern=CANDIDATE_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    source: SourceReference
    rule: ContractRule
    requirement_ids: tuple[str, ...] = Field(default=(), max_length=256)
    created_by: str = Field(min_length=1, max_length=128)
    created_at_us: int = Field(ge=0)
    llm_metadata: LLMGenerationMetadata | None = None

    @field_validator("requirement_ids")
    @classmethod
    def validate_requirement_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        import re

        if len(set(values)) != len(values) or any(
            re.fullmatch(REQUIREMENT_ID_PATTERN, value) is None for value in values
        ):
            raise ValueError("candidate requirement references are invalid")
        return values

    @field_validator("created_by")
    @classmethod
    def validate_actor(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("audit actor must be trimmed")
        return value

    @model_validator(mode="after")
    def validate_llm_metadata(self) -> ContractCandidate:
        if self.source.source_type is ContractSourceType.LLM and self.llm_metadata is None:
            raise ValueError("LLM candidates require generation metadata")
        if self.source.source_type is not ContractSourceType.LLM and self.llm_metadata is not None:
            raise ValueError("non-LLM candidates cannot carry LLM metadata")
        return self
class ContractProvenance(GovernanceModel):
    requirement_ids: tuple[str, ...] = Field(default=(), max_length=512)
    candidate_ids: tuple[str, ...] = Field(default=(), max_length=512)
    sources: tuple[SourceReference, ...] = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def validate_references(self) -> ContractProvenance:
        import re

        if len(set(self.requirement_ids)) != len(self.requirement_ids) or any(
            re.fullmatch(REQUIREMENT_ID_PATTERN, value) is None
            for value in self.requirement_ids
        ):
            raise ValueError("contract requirement references are invalid")
        if len(set(self.candidate_ids)) != len(self.candidate_ids) or any(
            re.fullmatch(CANDIDATE_ID_PATTERN, value) is None
            for value in self.candidate_ids
        ):
            raise ValueError("contract candidate references are invalid")
        if len(set(self.sources)) != len(self.sources):
            raise ValueError("contract sources must be unique")
        return self


class ContractAuditEntry(GovernanceModel):
    action: ContractAuditAction
    actor: str = Field(min_length=1, max_length=128)
    occurred_at_us: int = Field(ge=0)

    @field_validator("actor")
    @classmethod
    def validate_actor(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("audit actor must be trimmed")
        return value


class ContractVersion(GovernanceModel):
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    contract_id: str = Field(pattern=LONG_SLUG_ID_PATTERN)
    version: int = Field(ge=1)
    status: ContractStatus = ContractStatus.DRAFT
    snapshot: SecurityContract
    provenance: ContractProvenance
    supersedes_version: int | None = Field(default=None, ge=1)
    audit: tuple[ContractAuditEntry, ...] = Field(min_length=1, max_length=64)
    created_at_us: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_version(self) -> ContractVersion:
        if (
            self.snapshot.id != self.contract_id
            or self.snapshot.version != self.version
            or self.snapshot.status is not self.status
        ):
            raise ValueError("contract snapshot identity is inconsistent")
        rule_ids = tuple(rule.id for rule in self.snapshot.rules)
        if len(set(rule_ids)) != len(rule_ids):
            raise ValueError("contract rule IDs must be unique")
        if self.updated_at_us < self.created_at_us:
            raise ValueError("contract update time precedes creation")
        if (
            self.audit[0].occurred_at_us != self.created_at_us
            or self.audit[-1].occurred_at_us != self.updated_at_us
        ):
            raise ValueError("contract audit times must match version times")
        if (self.version == 1) != (self.supersedes_version is None):
            raise ValueError("only the first contract version omits supersedes_version")
        if self.version > 1 and self.supersedes_version != self.version - 1:
            raise ValueError("contract revisions must supersede the preceding version")
        expected_actions = {
            ContractStatus.DRAFT: (ContractAuditAction.CREATED,),
            ContractStatus.REVIEW: (
                ContractAuditAction.CREATED,
                ContractAuditAction.SUBMITTED,
            ),
            ContractStatus.ACTIVE: (
                ContractAuditAction.CREATED,
                ContractAuditAction.SUBMITTED,
                ContractAuditAction.ACTIVATED,
            ),
            ContractStatus.REJECTED: (
                ContractAuditAction.CREATED,
                ContractAuditAction.SUBMITTED,
                ContractAuditAction.REJECTED,
            ),
            ContractStatus.SUPERSEDED: (
                ContractAuditAction.CREATED,
                ContractAuditAction.SUBMITTED,
                ContractAuditAction.ACTIVATED,
                ContractAuditAction.SUPERSEDED,
            ),
        }[self.status]
        if tuple(entry.action for entry in self.audit) != expected_actions:
            raise ValueError("contract audit trail does not match status")
        if any(
            earlier.occurred_at_us > later.occurred_at_us
            for earlier, later in zip(self.audit, self.audit[1:])
        ):
            raise ValueError("contract audit times must be ordered")
        return self
