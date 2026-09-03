# =============================================================================
# PermissionIntent v2 长期权限语义
#
# 职责
#   冻结稳定 Actor/Action revision 引用、受保护 Effect identity 与项目 policy epoch。
#
# 边界
#   不复制显示名、Effect 正文、Candidate、Binding、TestIdentity、HTTP 或 Observer 事实。
# =============================================================================

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from product.backend.core.approval import HumanApproval, HumanApprovalChannel
from product.backend.core.business_boundary import (
    ACTION_ID_PATTERN,
    ACTOR_ID_PATTERN,
    EFFECT_ID_PATTERN,
)
from product.backend.core.identifiers import PROJECT_ID_PATTERN, SHA256_PATTERN
from product.backend.core.verification.permissions import PermissionExpectation


_INTENT_ID_PATTERN = r"^pin_[0-9a-f]{32}$"


class PermissionIntentModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, hide_input_in_errors=True
    )


class PermissionIntentRelation(StrEnum):
    OWNS = "OWNS"
    SAME_ROLE_OTHER_ACCOUNT = "SAME_ROLE_OTHER_ACCOUNT"
    OTHER_ROLE = "OTHER_ROLE"


class PermissionIntentEffectiveState(StrEnum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


def permission_intent_sha256(payload: dict[str, Any]) -> str:
    """只对稳定业务权限语义计算 canonical SHA-256。"""

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class PermissionIntentSemantic(PermissionIntentModel):
    effective_state: PermissionIntentEffectiveState
    subject_actor_id: str = Field(pattern=ACTOR_ID_PATTERN)
    subject_actor_revision: int = Field(ge=1)
    business_action_id: str = Field(pattern=ACTION_ID_PATTERN)
    action_revision: int = Field(ge=1)
    resource_owner_actor_id: str = Field(pattern=ACTOR_ID_PATTERN)
    resource_owner_actor_revision: int = Field(ge=1)
    relation: PermissionIntentRelation
    expectation: PermissionExpectation
    protected_effect_ids: tuple[str, ...] = Field(min_length=1, max_length=16)

    @field_validator("protected_effect_ids")
    @classmethod
    def normalize_effect_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values) or any(
            re.fullmatch(EFFECT_ID_PATTERN, value) is None for value in values
        ):
            raise ValueError("protected effect IDs must be unique business effect IDs")
        return tuple(sorted(values))

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
            subject_actor_id=self.subject_actor_id,
            subject_actor_revision=self.subject_actor_revision,
            business_action_id=self.business_action_id,
            action_revision=self.action_revision,
            resource_owner_actor_id=self.resource_owner_actor_id,
            resource_owner_actor_revision=self.resource_owner_actor_revision,
            relation=self.relation,
            expectation=self.expectation,
            protected_effect_ids=self.protected_effect_ids,
        )
        if self.intent_hash != permission_intent_sha256(semantic.canonical_payload()):
            raise ValueError("permission intent hash is inconsistent")
        if self.approval.approved_at_us != self.created_at_us:
            raise ValueError("permission intent creation time must match approval")
        return self


class ProjectPolicyState(PermissionIntentModel):
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    policy_epoch: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)


__all__ = [
    "HumanApproval", "HumanApprovalChannel", "PermissionIntentEffectiveState",
    "PermissionIntentRelation", "PermissionIntentRevision", "PermissionIntentSemantic",
    "ProjectPolicyState", "permission_intent_sha256",
]
