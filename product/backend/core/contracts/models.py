# Contract 契约需求、候选与版本治理模型。

from __future__ import annotations

from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from product.backend.core.identifiers import LONG_SLUG_ID_PATTERN, PROJECT_ID_PATTERN, SHA256_PATTERN
from product.backend.core.lifecycle import ContractStatus
from product.backend.core.verification.permissions import PermissionContract


class ContractSourceType(StrEnum):
    PROJECT_CONFIG = "project_config"


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


class ContractProvenance(GovernanceModel):
    sources: tuple[SourceReference, ...] = Field(default=(), max_length=512)

    @model_validator(mode="after")
    def validate_references(self) -> ContractProvenance:
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
    snapshot: PermissionContract
    provenance: ContractProvenance
    supersedes_version: int | None = Field(default=None, ge=1)
    audit: tuple[ContractAuditEntry, ...] = Field(min_length=1, max_length=64)
    created_at_us: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_version(self) -> ContractVersion:
        if self.snapshot.contract_id != self.contract_id or self.snapshot.version != self.version:
            raise ValueError("contract snapshot identity is inconsistent")
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
