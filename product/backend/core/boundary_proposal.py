# =============================================================================
# Business Boundary Proposal 与 Decision 不可变事实
#
# 职责
#   冻结用户提交的本地 item 引用、discovery 来源快照、Proposal fingerprint 与最终 Decision。
#
# 边界
#   Proposal 写入后不更新；正式 ID、Approval、epoch 与服务端来源指纹不接受客户端自述。
# =============================================================================

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from product.backend.core.business_boundary import (
    ACTION_ID_PATTERN,
    ACTOR_ID_PATTERN,
    EFFECT_ID_PATTERN,
    BoundaryModel,
    BusinessActionOperationKind,
    BusinessRevisionState,
    boundary_sha256,
)
from product.backend.core.identifiers import PROJECT_ID_PATTERN, SHA256_PATTERN
from product.backend.core.permission_intent import (
    PermissionIntentEffectiveState,
    PermissionIntentRelation,
)
from product.backend.core.permission_semantics import (
    PermissionExpectation,
    BusinessEffectKind,
)


PROPOSAL_ID_PATTERN = r"^bpr_[0-9a-f]{32}$"
DECISION_ID_PATTERN = r"^bpd_[0-9a-f]{32}$"
ACTOR_ITEM_ID_PATTERN = r"^pactr_[0-9a-f]{16}$"
ACTION_ITEM_ID_PATTERN = r"^pactn_[0-9a-f]{16}$"
EFFECT_ITEM_ID_PATTERN = r"^peff_[0-9a-f]{16}$"
PERMISSION_ITEM_ID_PATTERN = r"^pperm_[0-9a-f]{16}$"
INTENT_ID_PATTERN = r"^pin_[0-9a-f]{32}$"


class ProposalWriteMode(StrEnum):
    CREATE = "CREATE"
    REFERENCE = "REFERENCE"
    APPEND_REVISION = "APPEND_REVISION"


class ProposalCandidateKind(StrEnum):
    ROLE = "ROLE"
    ACTION = "ACTION"


class BoundaryDecisionKind(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


def _text(value: str, field_name: str) -> str:
    if value != value.strip() or not value or any(ord(char) < 32 for char in value):
        raise ValueError(f"{field_name} must be trimmed printable text")
    return value


class CandidateSourceSnapshot(BoundaryModel):
    candidate_kind: ProposalCandidateKind
    candidate_id: str
    candidate_fingerprint: str = Field(pattern=SHA256_PATTERN)
    evidence_fingerprint: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_candidate_id(self) -> CandidateSourceSnapshot:
        pattern = (
            r"^role_[0-9a-f]{32}$"
            if self.candidate_kind is ProposalCandidateKind.ROLE
            else r"^action_[0-9a-f]{32}$"
        )
        if re.fullmatch(pattern, self.candidate_id) is None:
            raise ValueError("proposal candidate kind and ID are inconsistent")
        return self


class BoundarySourceSnapshot(BoundaryModel):
    basis_version: Literal[1, 2] = 1
    application_understanding_revision: int = Field(ge=0, le=1_000_000)
    source_fingerprint: str = Field(pattern=SHA256_PATTERN)
    candidates: tuple[CandidateSourceSnapshot, ...] = Field(default=(), max_length=768)

    @field_validator("candidates")
    @classmethod
    def normalize_candidates(
        cls, values: tuple[CandidateSourceSnapshot, ...]
    ) -> tuple[CandidateSourceSnapshot, ...]:
        keys = tuple((item.candidate_kind.value, item.candidate_id) for item in values)
        if len(set(keys)) != len(keys):
            raise ValueError("proposal source candidates must be unique")
        return tuple(sorted(values, key=lambda item: (item.candidate_kind.value, item.candidate_id)))


class ProposedEffectItem(BoundaryModel):
    item_id: str = Field(pattern=EFFECT_ITEM_ID_PATTERN)
    effect_id: str | None = Field(default=None, pattern=EFFECT_ID_PATTERN)
    business_label: str = Field(min_length=1, max_length=256)
    effect_kind: BusinessEffectKind
    resource_concept: str = Field(min_length=1, max_length=128)
    expected_state: str | None = Field(default=None, min_length=1, max_length=512)
    protected_projection: tuple[str, ...] = Field(default=(), max_length=64)
    description: str = Field(min_length=1, max_length=1024)

    @field_validator("business_label", "resource_concept", "expected_state", "description")
    @classmethod
    def validate_text(cls, value: str | None, info) -> str | None:
        return None if value is None else _text(value, info.field_name)

    @field_validator("protected_projection")
    @classmethod
    def normalize_projection(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values) or any(
            re.fullmatch(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$", value) is None
            for value in values
        ):
            raise ValueError("protected projection is invalid")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_projection_kind(self) -> ProposedEffectItem:
        if self.effect_kind is BusinessEffectKind.DATA_DISCLOSURE:
            if not self.protected_projection:
                raise ValueError("DATA_DISCLOSURE requires protected projection")
        elif self.protected_projection:
            raise ValueError("protected projection only applies to DATA_DISCLOSURE")
        return self


class _ProposedRevisionItem(BoundaryModel):
    write_mode: ProposalWriteMode
    expected_current_revision: int | None = Field(default=None, ge=1)
    source_candidate_ids: tuple[str, ...] = Field(default=(), max_length=64)

    def _validate_write_mode(self, formal_id: str | None) -> None:
        if self.write_mode is ProposalWriteMode.CREATE:
            if formal_id is not None or self.expected_current_revision is not None:
                raise ValueError("CREATE item cannot provide formal identity")
        elif formal_id is None or self.expected_current_revision is None:
            raise ValueError("REFERENCE/APPEND_REVISION require formal identity and revision")


class ProposedActorItem(_ProposedRevisionItem):
    item_id: str = Field(pattern=ACTOR_ITEM_ID_PATTERN)
    actor_id: str | None = Field(default=None, pattern=ACTOR_ID_PATTERN)
    display_name: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=1024)
    effective_state: BusinessRevisionState

    @field_validator("display_name", "description")
    @classmethod
    def validate_text(cls, value: str, info) -> str:
        return _text(value, info.field_name)

    @field_validator("source_candidate_ids")
    @classmethod
    def normalize_sources(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values) or any(
            re.fullmatch(r"^role_[0-9a-f]{32}$", value) is None for value in values
        ):
            raise ValueError("actor source candidates are invalid")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_item(self) -> ProposedActorItem:
        self._validate_write_mode(self.actor_id)
        return self


class ProposedActionItem(_ProposedRevisionItem):
    item_id: str = Field(pattern=ACTION_ITEM_ID_PATTERN)
    action_id: str | None = Field(default=None, pattern=ACTION_ID_PATTERN)
    display_name: str = Field(min_length=1, max_length=256)
    description: str = Field(min_length=1, max_length=1024)
    primary_resource_concept: str = Field(min_length=1, max_length=128)
    operation_kind: BusinessActionOperationKind
    state_changing: bool
    effect_catalog: tuple[ProposedEffectItem, ...] = Field(min_length=1, max_length=16)
    effective_state: BusinessRevisionState

    @field_validator("display_name", "description", "primary_resource_concept")
    @classmethod
    def validate_text(cls, value: str, info) -> str:
        return _text(value, info.field_name)

    @field_validator("source_candidate_ids")
    @classmethod
    def normalize_sources(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values) or any(
            re.fullmatch(r"^action_[0-9a-f]{32}$", value) is None for value in values
        ):
            raise ValueError("action source candidates are invalid")
        return tuple(sorted(values))

    @field_validator("effect_catalog")
    @classmethod
    def normalize_effects(cls, values: tuple[ProposedEffectItem, ...]) -> tuple[ProposedEffectItem, ...]:
        if len({item.item_id for item in values}) != len(values):
            raise ValueError("proposal effect item IDs must be unique")
        return tuple(sorted(values, key=lambda item: item.item_id))

    @model_validator(mode="after")
    def validate_item(self) -> ProposedActionItem:
        self._validate_write_mode(self.action_id)
        return self


class ProposedPermissionItem(BoundaryModel):
    item_id: str = Field(pattern=PERMISSION_ITEM_ID_PATTERN)
    write_mode: ProposalWriteMode
    intent_id: str | None = Field(default=None, pattern=INTENT_ID_PATTERN)
    expected_current_revision: int | None = Field(default=None, ge=1)
    effective_state: PermissionIntentEffectiveState
    subject_actor_item_id: str = Field(pattern=ACTOR_ITEM_ID_PATTERN)
    business_action_item_id: str = Field(pattern=ACTION_ITEM_ID_PATTERN)
    resource_owner_actor_item_id: str = Field(pattern=ACTOR_ITEM_ID_PATTERN)
    relation: PermissionIntentRelation
    expectation: PermissionExpectation
    protected_effect_item_ids: tuple[str, ...] = Field(min_length=1, max_length=16)

    @field_validator("protected_effect_item_ids")
    @classmethod
    def normalize_effect_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values):
            raise ValueError("permission effect references must be unique")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_item(self) -> ProposedPermissionItem:
        if self.write_mode is ProposalWriteMode.CREATE:
            if self.intent_id is not None or self.expected_current_revision is not None:
                raise ValueError("CREATE permission cannot provide formal identity")
        elif self.intent_id is None or self.expected_current_revision is None:
            raise ValueError("REFERENCE/APPEND permission requires formal identity and revision")
        return self


class BoundaryProposalBundle(BoundaryModel):
    proposal_id: str = Field(pattern=PROPOSAL_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    source_snapshot: BoundarySourceSnapshot
    proposed_actors: tuple[ProposedActorItem, ...] = Field(default=(), max_length=256)
    proposed_actions: tuple[ProposedActionItem, ...] = Field(default=(), max_length=512)
    proposed_permissions: tuple[ProposedPermissionItem, ...] = Field(default=(), max_length=1024)
    unresolved_questions: tuple[str, ...] = Field(default=(), max_length=128)
    provenance: str = Field(min_length=1, max_length=512)
    proposal_fingerprint: str = Field(pattern=SHA256_PATTERN)
    created_at_us: int = Field(ge=0)

    @field_validator("proposed_actors", "proposed_actions", "proposed_permissions")
    @classmethod
    def normalize_items(cls, values: tuple[Any, ...]) -> tuple[Any, ...]:
        if len({item.item_id for item in values}) != len(values):
            raise ValueError("proposal local item IDs must be unique")
        return tuple(sorted(values, key=lambda item: item.item_id))

    @field_validator("unresolved_questions")
    @classmethod
    def validate_questions(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_text(value, "unresolved_questions") for value in values)
        if len(set(normalized)) != len(normalized):
            raise ValueError("unresolved questions must be unique")
        return normalized

    @field_validator("provenance")
    @classmethod
    def validate_provenance(cls, value: str) -> str:
        return _text(value, "provenance")

    def fingerprint_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json", exclude={"proposal_fingerprint"})
        if self.source_snapshot.basis_version == 1:
            # 历史已持久 Proposal 的 fingerprint 中没有 basis_version；
            # 读取兼容不能反过来让不可变 Proposal 看似被修改。
            payload["source_snapshot"].pop("basis_version", None)
        return payload

    @model_validator(mode="after")
    def validate_bundle(self) -> BoundaryProposalBundle:
        actor_ids = {item.item_id for item in self.proposed_actors}
        action_by_id = {item.item_id: item for item in self.proposed_actions}
        snapshot_ids = {item.candidate_id for item in self.source_snapshot.candidates}
        for item in (*self.proposed_actors, *self.proposed_actions):
            if any(source_id not in snapshot_ids for source_id in item.source_candidate_ids):
                raise ValueError("proposal source reference is outside the source snapshot")
        for item in self.proposed_permissions:
            action = action_by_id.get(item.business_action_item_id)
            if (
                item.subject_actor_item_id not in actor_ids
                or item.resource_owner_actor_item_id not in actor_ids
                or action is None
            ):
                raise ValueError("proposal permission local references are invalid")
            effect_ids = {effect.item_id for effect in action.effect_catalog}
            if any(effect_id not in effect_ids for effect_id in item.protected_effect_item_ids):
                raise ValueError("proposal permission effect reference is invalid")
        if self.proposal_fingerprint != boundary_sha256(self.fingerprint_payload()):
            raise ValueError("boundary proposal fingerprint is inconsistent")
        return self


class BoundaryProposalDecision(BoundaryModel):
    decision_id: str = Field(pattern=DECISION_ID_PATTERN)
    proposal_id: str = Field(pattern=PROPOSAL_ID_PATTERN)
    proposal_fingerprint: str = Field(pattern=SHA256_PATTERN)
    decision: BoundaryDecisionKind
    decided_by: str = Field(min_length=1, max_length=128)
    decided_at_us: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=512)

    @field_validator("decided_by", "reason")
    @classmethod
    def validate_text(cls, value: str, info) -> str:
        return _text(value, info.field_name)

    @model_validator(mode="after")
    def validate_decider(self) -> BoundaryProposalDecision:
        if self.decided_by != "本机界鉴用户":
            raise ValueError("boundary decision identity is server controlled")
        return self


__all__ = [
    "BoundaryDecisionKind", "BoundaryProposalBundle", "BoundaryProposalDecision",
    "BoundarySourceSnapshot", "CandidateSourceSnapshot", "ProposalCandidateKind",
    "ProposalWriteMode", "ProposedActionItem", "ProposedActorItem",
    "ProposedEffectItem", "ProposedPermissionItem",
]
