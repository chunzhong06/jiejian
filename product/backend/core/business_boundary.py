# =============================================================================
# 稳定业务边界领域事实
#
# 职责
#   定义 Actor/Action revision、内嵌 EffectCatalog 与实现绑定的不可变语义。
#
# 边界
#   不依赖 discovery Candidate；候选只由 Proposal/Binding workflow 作为来源事实读取。
# =============================================================================

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from product.backend.core.approval import HumanApproval
from product.backend.core.identifiers import PROJECT_ID_PATTERN, SHA256_PATTERN
from product.backend.core.verification.permissions import SecurityEffectKind


ACTOR_ID_PATTERN = r"^bar_[0-9a-f]{32}$"
ACTION_ID_PATTERN = r"^bac_[0-9a-f]{32}$"
EFFECT_ID_PATTERN = r"^bef_[0-9a-f]{32}$"
SOURCE_PROPOSAL_ID_PATTERN = r"^bpr_[0-9a-f]{32}$"
_PROJECTION_PATH = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")


class BoundaryModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, hide_input_in_errors=True
    )


class BusinessRevisionState(StrEnum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class BusinessActionOperationKind(StrEnum):
    READ = "READ"
    CHANGE = "CHANGE"
    DELETE = "DELETE"
    EXPORT = "EXPORT"
    ADMIN = "ADMIN"
    CUSTOM = "CUSTOM"


# B1 卡使用的短名与 A1 冻结枚举指向同一真源。
BoundaryEffectiveState = BusinessRevisionState
BusinessOperationKind = BusinessActionOperationKind


class ImplementationBindingStatus(StrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    MISSING = "MISSING"
    AMBIGUOUS = "AMBIGUOUS"


class ImplementationCandidateSnapshot(BoundaryModel):
    candidate_id: str = Field(pattern=r"^(role|action)_[0-9a-f]{32}$")
    candidate_fingerprint: str = Field(pattern=SHA256_PATTERN)
    evidence_fingerprint: str = Field(pattern=SHA256_PATTERN)


def boundary_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _trimmed_text(value: str, field_name: str) -> str:
    if value != value.strip() or not value or any(ord(char) < 32 for char in value):
        raise ValueError(f"{field_name} must be trimmed printable text")
    return value


class BusinessEffectDefinition(BoundaryModel):
    effect_id: str = Field(pattern=EFFECT_ID_PATTERN)
    business_label: str = Field(min_length=1, max_length=256)
    effect_kind: SecurityEffectKind
    resource_concept: str = Field(min_length=1, max_length=128)
    expected_state: str | None = Field(default=None, min_length=1, max_length=512)
    protected_projection: tuple[str, ...] = Field(default=(), max_length=64)
    description: str = Field(min_length=1, max_length=1024)

    @field_validator("business_label", "resource_concept", "expected_state", "description")
    @classmethod
    def validate_text(cls, value: str | None, info) -> str | None:
        return None if value is None else _trimmed_text(value, info.field_name)

    @field_validator("protected_projection")
    @classmethod
    def normalize_projection(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values) or any(
            _PROJECTION_PATH.fullmatch(value) is None for value in values
        ):
            raise ValueError("protected projection must contain unique bounded paths")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_effect_kind(self) -> BusinessEffectDefinition:
        if self.effect_kind is SecurityEffectKind.DATA_DISCLOSURE:
            if not self.protected_projection:
                raise ValueError("DATA_DISCLOSURE requires protected projection")
        elif self.protected_projection:
            raise ValueError("protected projection only applies to DATA_DISCLOSURE")
        return self

    def business_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"effect_id"})


class BusinessActor(BoundaryModel):
    actor_id: str = Field(pattern=ACTOR_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    current_revision: int = Field(ge=1)
    created_at_us: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_times(self) -> BusinessActor:
        if self.updated_at_us < self.created_at_us:
            raise ValueError("business actor update precedes creation")
        return self


class BusinessActorRevision(BoundaryModel):
    actor_id: str = Field(pattern=ACTOR_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    revision: int = Field(ge=1)
    display_name: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=1024)
    semantic_fingerprint: str = Field(pattern=SHA256_PATTERN)
    effective_state: BusinessRevisionState
    approval: HumanApproval
    created_at_us: int = Field(ge=0)

    @field_validator("display_name", "description")
    @classmethod
    def validate_text(cls, value: str, info) -> str:
        return _trimmed_text(value, info.field_name)

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "project_id": self.project_id,
            "display_name": self.display_name,
            "description": self.description,
            "effective_state": self.effective_state.value,
        }

    @model_validator(mode="after")
    def validate_revision(self) -> BusinessActorRevision:
        if self.semantic_fingerprint != boundary_sha256(self.semantic_payload()):
            raise ValueError("business actor fingerprint is inconsistent")
        if self.approval.approved_at_us != self.created_at_us:
            raise ValueError("business actor creation time must match approval")
        return self


class BusinessAction(BoundaryModel):
    action_id: str = Field(pattern=ACTION_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    current_revision: int = Field(ge=1)
    created_at_us: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_times(self) -> BusinessAction:
        if self.updated_at_us < self.created_at_us:
            raise ValueError("business action update precedes creation")
        return self


class BusinessActionRevision(BoundaryModel):
    action_id: str = Field(pattern=ACTION_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    revision: int = Field(ge=1)
    display_name: str = Field(min_length=1, max_length=256)
    description: str = Field(min_length=1, max_length=1024)
    primary_resource_concept: str = Field(min_length=1, max_length=128)
    operation_kind: BusinessActionOperationKind
    state_changing: bool
    effect_catalog: tuple[BusinessEffectDefinition, ...] = Field(min_length=1, max_length=16)
    semantic_fingerprint: str = Field(pattern=SHA256_PATTERN)
    effective_state: BusinessRevisionState
    approval: HumanApproval
    created_at_us: int = Field(ge=0)

    @field_validator("display_name", "description", "primary_resource_concept")
    @classmethod
    def validate_text(cls, value: str, info) -> str:
        return _trimmed_text(value, info.field_name)

    @field_validator("effect_catalog")
    @classmethod
    def normalize_effect_catalog(
        cls, values: tuple[BusinessEffectDefinition, ...]
    ) -> tuple[BusinessEffectDefinition, ...]:
        effect_ids = tuple(item.effect_id for item in values)
        semantics = tuple(
            json.dumps(
                item.business_payload(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            for item in values
        )
        if len(set(effect_ids)) != len(effect_ids):
            raise ValueError("effect catalog IDs must be unique")
        if len(set(semantics)) != len(semantics):
            raise ValueError("effect catalog business semantics must be unique")
        return tuple(sorted(values, key=lambda item: item.effect_id))

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "project_id": self.project_id,
            "display_name": self.display_name,
            "description": self.description,
            "primary_resource_concept": self.primary_resource_concept,
            "operation_kind": self.operation_kind.value,
            "state_changing": self.state_changing,
            "effect_catalog": [item.model_dump(mode="json") for item in self.effect_catalog],
            "effective_state": self.effective_state.value,
        }

    @model_validator(mode="after")
    def validate_revision(self) -> BusinessActionRevision:
        if self.semantic_fingerprint != boundary_sha256(self.semantic_payload()):
            raise ValueError("business action fingerprint is inconsistent")
        if self.approval.approved_at_us != self.created_at_us:
            raise ValueError("business action creation time must match approval")
        return self


class _ImplementationBinding(BoundaryModel):
    understanding_revision: int = Field(ge=0, le=1_000_000)
    source_fingerprint: str | None = Field(default=None, pattern=SHA256_PATTERN)
    basis_version: Literal[1, 2]
    source_proposal_id: str | None = Field(
        default=None, pattern=SOURCE_PROPOSAL_ID_PATTERN
    )
    confirmed_at_us: int | None = Field(default=None, ge=0)
    candidate_snapshots: tuple[ImplementationCandidateSnapshot, ...] = Field(
        default=(), max_length=64
    )
    binding_fingerprint: str = Field(pattern=SHA256_PATTERN)
    updated_at_us: int = Field(ge=0)

    @field_validator("candidate_snapshots")
    @classmethod
    def normalize_candidate_snapshots(
        cls, values: tuple[ImplementationCandidateSnapshot, ...]
    ) -> tuple[ImplementationCandidateSnapshot, ...]:
        candidate_ids = tuple(item.candidate_id for item in values)
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("binding candidate snapshots must be unique")
        return tuple(sorted(values, key=lambda item: item.candidate_id))

    def _validate_basis(self, candidate_ids: tuple[str, ...]) -> None:
        snapshot_ids = tuple(item.candidate_id for item in self.candidate_snapshots)
        if self.basis_version == 1:
            if snapshot_ids or self.source_proposal_id is not None or self.confirmed_at_us is not None:
                raise ValueError("legacy binding cannot invent approval provenance")
            return
        if snapshot_ids != candidate_ids:
            raise ValueError("v2 binding snapshots must match selected candidates")
        if self.source_proposal_id is None or self.confirmed_at_us is None:
            raise ValueError("v2 binding requires approval provenance")
        if self.confirmed_at_us != self.updated_at_us:
            raise ValueError("binding confirmation time must match its approved update")


class ActorImplementationBinding(_ImplementationBinding):
    actor_id: str = Field(pattern=ACTOR_ID_PATTERN)
    actor_revision: int = Field(ge=1)
    role_candidate_ids: tuple[str, ...] = Field(default=(), max_length=64)

    @field_validator("role_candidate_ids")
    @classmethod
    def normalize_candidates(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values) or any(
            re.fullmatch(r"^role_[0-9a-f]{32}$", value) is None for value in values
        ):
            raise ValueError("actor binding candidates are invalid")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_binding(self) -> ActorImplementationBinding:
        if any(not item.candidate_id.startswith("role_") for item in self.candidate_snapshots):
            raise ValueError("actor binding snapshots must reference role candidates")
        self._validate_basis(self.role_candidate_ids)
        payload = self._fingerprint_payload()
        if self.binding_fingerprint != boundary_sha256(payload):
            raise ValueError("actor binding fingerprint is inconsistent")
        return self

    def _fingerprint_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "actor_id": self.actor_id,
            "actor_revision": self.actor_revision,
            "understanding_revision": self.understanding_revision,
            "source_fingerprint": self.source_fingerprint,
            "role_candidate_ids": list(self.role_candidate_ids),
        }
        if self.basis_version == 2:
            payload["basis_version"] = self.basis_version
            payload["source_proposal_id"] = self.source_proposal_id
            payload["confirmed_at_us"] = self.confirmed_at_us
            payload["candidate_snapshots"] = [
                item.model_dump(mode="json") for item in self.candidate_snapshots
            ]
        return payload


class ActionImplementationBinding(_ImplementationBinding):
    action_id: str = Field(pattern=ACTION_ID_PATTERN)
    action_revision: int = Field(ge=1)
    action_candidate_ids: tuple[str, ...] = Field(default=(), max_length=64)

    @field_validator("action_candidate_ids")
    @classmethod
    def normalize_candidates(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values) or any(
            re.fullmatch(r"^action_[0-9a-f]{32}$", value) is None for value in values
        ):
            raise ValueError("action binding candidates are invalid")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_binding(self) -> ActionImplementationBinding:
        if any(not item.candidate_id.startswith("action_") for item in self.candidate_snapshots):
            raise ValueError("action binding snapshots must reference action candidates")
        self._validate_basis(self.action_candidate_ids)
        payload = self._fingerprint_payload()
        if self.binding_fingerprint != boundary_sha256(payload):
            raise ValueError("action binding fingerprint is inconsistent")
        return self

    def _fingerprint_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "action_id": self.action_id,
            "action_revision": self.action_revision,
            "understanding_revision": self.understanding_revision,
            "source_fingerprint": self.source_fingerprint,
            "action_candidate_ids": list(self.action_candidate_ids),
        }
        if self.basis_version == 2:
            payload["basis_version"] = self.basis_version
            payload["source_proposal_id"] = self.source_proposal_id
            payload["confirmed_at_us"] = self.confirmed_at_us
            payload["candidate_snapshots"] = [
                item.model_dump(mode="json") for item in self.candidate_snapshots
            ]
        return payload


__all__ = [
    "ACTION_ID_PATTERN", "ACTOR_ID_PATTERN", "EFFECT_ID_PATTERN",
    "SOURCE_PROPOSAL_ID_PATTERN",
    "ActionImplementationBinding", "ActorImplementationBinding",
    "BoundaryEffectiveState", "BusinessAction", "BusinessActionOperationKind",
    "BusinessActionRevision", "BusinessActor", "BusinessActorRevision",
    "BusinessEffectDefinition", "BusinessOperationKind", "BusinessRevisionState",
    "ImplementationBindingStatus", "ImplementationCandidateSnapshot", "boundary_sha256",
]
