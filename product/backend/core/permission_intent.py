# =============================================================================
# 长期权限意图账本领域事实
#
# 定位
#   人类批准权限语义、实现绑定与 Agent 提案之间的唯一项目级安全真源。
#
# 职责
#   冻结不可变权限 revision｜规范化语义 hash｜记录项目 epoch、实现绑定和提案状态。
#
# 边界
#   Revision 不保存 candidate、HTTP、账号、秘密、Observer、Runner 或审批入口参数。
#
# 调用链
#   PermissionIntentService → Ledger models → Repository / Compiler / Run snapshot
# =============================================================================

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from product.backend.core.identifiers import PROJECT_ID_PATTERN, SHA256_PATTERN
from product.backend.core.verification.permissions import (
    PermissionExpectation,
    SecurityEffectKind,
)


_ACTION_ID_PATTERN = r"^action_[0-9a-f]{32}$"
_ROLE_ID_PATTERN = r"^role_[0-9a-f]{32}$"
_INTENT_ID_PATTERN = r"^pin_[0-9a-f]{32}$"
_PROPOSAL_ID_PATTERN = r"^prp_[0-9a-f]{32}$"
_PROJECTION_PATH = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")


class PermissionIntentModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class PermissionIntentRelation(StrEnum):
    OWNS = "OWNS"
    SAME_ROLE_OTHER_ACCOUNT = "SAME_ROLE_OTHER_ACCOUNT"
    OTHER_ROLE = "OTHER_ROLE"


class PermissionIntentEffectiveState(StrEnum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class HumanApprovalChannel(StrEnum):
    LOCAL_GUI = "LOCAL_GUI"
    MIGRATED_USER_CONFIRMATION = "MIGRATED_USER_CONFIRMATION"


class IntentImplementationBindingStatus(StrEnum):
    CURRENT = "CURRENT"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    UNRESOLVED = "UNRESOLVED"


class IntentProposalKind(StrEnum):
    SEMANTIC_CHANGE = "SEMANTIC_CHANGE"
    IMPLEMENTATION_REBIND = "IMPLEMENTATION_REBIND"


class IntentProposalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


def permission_intent_sha256(payload: dict[str, Any]) -> str:
    """对有界语义做 canonical hash，不纳入身份、审批人或运行事实。"""

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_text(value: str, field_name: str) -> str:
    if value != value.strip() or not value or any(ord(char) < 32 for char in value):
        raise ValueError(f"{field_name} must be trimmed printable text")
    return value


class ProtectedEffect(PermissionIntentModel):
    kind: SecurityEffectKind
    resource_type: str = Field(min_length=1, max_length=128)
    business_label: str = Field(min_length=1, max_length=256)
    protected_fields: tuple[str, ...] = Field(default=(), max_length=64)

    @field_validator("resource_type", "business_label")
    @classmethod
    def validate_display_text(cls, value: str, info) -> str:
        return _safe_text(value, info.field_name)

    @field_validator("protected_fields")
    @classmethod
    def validate_protected_fields(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values) or any(
            _PROJECTION_PATH.fullmatch(value) is None for value in values
        ):
            raise ValueError("protected fields must be unique bounded projections")
        return values

    @model_validator(mode="after")
    def validate_kind_fields(self) -> ProtectedEffect:
        if self.kind is SecurityEffectKind.DATA_DISCLOSURE:
            if not self.protected_fields:
                raise ValueError("data disclosure effect requires protected fields")
        elif self.protected_fields:
            raise ValueError("protected fields apply only to data disclosure")
        return self


class HumanApproval(PermissionIntentModel):
    channel: HumanApprovalChannel
    approved_by: str = Field(min_length=1, max_length=128)
    approved_at_us: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=512)

    @field_validator("approved_by", "reason")
    @classmethod
    def validate_text(cls, value: str, info) -> str:
        return _safe_text(value, info.field_name)


class PermissionIntentSemantic(PermissionIntentModel):
    effective_state: PermissionIntentEffectiveState
    subject_display_name: str = Field(min_length=1, max_length=128)
    action_display_name: str = Field(min_length=1, max_length=256)
    resource_owner_display_name: str = Field(min_length=1, max_length=128)
    relation: PermissionIntentRelation
    expectation: PermissionExpectation
    protected_effects: tuple[ProtectedEffect, ...] = Field(default=(), max_length=16)

    @field_validator(
        "subject_display_name",
        "action_display_name",
        "resource_owner_display_name",
    )
    @classmethod
    def validate_names(cls, value: str, info) -> str:
        return _safe_text(value, info.field_name)

    @field_validator("protected_effects")
    @classmethod
    def validate_effects(cls, values: tuple[ProtectedEffect, ...]) -> tuple[ProtectedEffect, ...]:
        identities = tuple(
            (item.kind.value, item.resource_type, item.business_label, item.protected_fields)
            for item in values
        )
        if len(set(identities)) != len(identities):
            raise ValueError("protected effects must be unique")
        return values

    def canonical_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class PermissionIntentRevision(PermissionIntentSemantic):
    intent_id: str = Field(pattern=_INTENT_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    revision: int = Field(ge=1)
    intent_hash: str = Field(pattern=SHA256_PATTERN)
    policy_epoch: int = Field(ge=1)
    approval: HumanApproval
    created_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_revision(self) -> PermissionIntentRevision:
        semantic = PermissionIntentSemantic(
            effective_state=self.effective_state,
            subject_display_name=self.subject_display_name,
            action_display_name=self.action_display_name,
            resource_owner_display_name=self.resource_owner_display_name,
            relation=self.relation,
            expectation=self.expectation,
            protected_effects=self.protected_effects,
        )
        if self.intent_hash != permission_intent_sha256(semantic.canonical_payload()):
            raise ValueError("permission intent hash is inconsistent")
        if self.approval.approved_at_us != self.created_at_us:
            raise ValueError("permission intent creation time must match approval time")
        return self


class ProjectPolicyState(PermissionIntentModel):
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    policy_epoch: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)


def implementation_binding_sha256(payload: dict[str, Any]) -> str:
    return permission_intent_sha256(payload)


class IntentImplementationBinding(PermissionIntentModel):
    intent_id: str = Field(pattern=_INTENT_ID_PATTERN)
    intent_revision: int = Field(ge=1)
    action_candidate_id: str = Field(pattern=_ACTION_ID_PATTERN)
    subject_role_candidate_id: str = Field(pattern=_ROLE_ID_PATTERN)
    resource_owner_role_candidate_id: str = Field(pattern=_ROLE_ID_PATTERN)
    understanding_revision: int = Field(ge=0, le=1_000_000)
    action_safety_setup_fingerprint: str | None = Field(default=None, pattern=SHA256_PATTERN)
    binding_fingerprint: str = Field(pattern=SHA256_PATTERN)
    status: IntentImplementationBindingStatus
    reason_codes: tuple[str, ...] = Field(default=(), max_length=32)
    updated_at_us: int = Field(ge=0)

    @field_validator("reason_codes")
    @classmethod
    def validate_reasons(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values) or any(
            not value or len(value) > 128 or not value.replace("_", "").isalnum()
            for value in values
        ):
            raise ValueError("binding reason codes must be unique bounded tokens")
        return values

    @model_validator(mode="after")
    def validate_binding(self) -> IntentImplementationBinding:
        semantic = {
            "intent_id": self.intent_id,
            "intent_revision": self.intent_revision,
            "action_candidate_id": self.action_candidate_id,
            "subject_role_candidate_id": self.subject_role_candidate_id,
            "resource_owner_role_candidate_id": self.resource_owner_role_candidate_id,
            "understanding_revision": self.understanding_revision,
            "action_safety_setup_fingerprint": self.action_safety_setup_fingerprint,
        }
        if self.binding_fingerprint != implementation_binding_sha256(semantic):
            raise ValueError("implementation binding fingerprint is inconsistent")
        if self.status is IntentImplementationBindingStatus.CURRENT:
            if self.action_safety_setup_fingerprint is None or self.reason_codes:
                raise ValueError("current binding requires safety fingerprint without reasons")
        elif not self.reason_codes:
            raise ValueError("non-current binding requires reason codes")
        return self


class ProposedImplementationBinding(PermissionIntentModel):
    action_candidate_id: str = Field(pattern=_ACTION_ID_PATTERN)
    subject_role_candidate_id: str = Field(pattern=_ROLE_ID_PATTERN)
    resource_owner_role_candidate_id: str = Field(pattern=_ROLE_ID_PATTERN)
    understanding_revision: int = Field(ge=0, le=1_000_000)
    action_safety_setup_fingerprint: str = Field(pattern=SHA256_PATTERN)


class IntentProposal(PermissionIntentModel):
    proposal_id: str = Field(pattern=_PROPOSAL_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    kind: IntentProposalKind
    status: IntentProposalStatus = IntentProposalStatus.PENDING
    intent_id: str | None = Field(default=None, pattern=_INTENT_ID_PATTERN)
    semantic_change: PermissionIntentSemantic | None = None
    implementation_rebind: ProposedImplementationBinding | None = None
    proposed_by: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=512)
    created_at_us: int = Field(ge=0)
    decided_at_us: int | None = Field(default=None, ge=0)

    @field_validator("proposed_by", "reason")
    @classmethod
    def validate_text(cls, value: str, info) -> str:
        return _safe_text(value, info.field_name)

    @model_validator(mode="after")
    def validate_proposal(self) -> IntentProposal:
        if self.kind is IntentProposalKind.SEMANTIC_CHANGE:
            valid_payload = self.semantic_change is not None and self.implementation_rebind is None
        else:
            valid_payload = self.semantic_change is None and self.implementation_rebind is not None
        if not valid_payload:
            raise ValueError("proposal kind and payload are inconsistent")
        if self.status is IntentProposalStatus.PENDING:
            if self.decided_at_us is not None:
                raise ValueError("pending proposal cannot have decision time")
        elif self.decided_at_us is None or self.decided_at_us < self.created_at_us:
            raise ValueError("decided proposal requires ordered decision time")
        return self


__all__ = [
    "HumanApproval",
    "HumanApprovalChannel",
    "IntentImplementationBinding",
    "IntentImplementationBindingStatus",
    "IntentProposal",
    "IntentProposalKind",
    "IntentProposalStatus",
    "PermissionIntentEffectiveState",
    "PermissionIntentRelation",
    "PermissionIntentRevision",
    "PermissionIntentSemantic",
    "ProjectPolicyState",
    "ProposedImplementationBinding",
    "ProtectedEffect",
    "implementation_binding_sha256",
    "permission_intent_sha256",
]
