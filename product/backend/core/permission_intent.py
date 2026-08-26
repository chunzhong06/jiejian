# =============================================================================
# 普通权限意图领域事实
#
# 定位
#   用户对“哪个权限组执行哪个业务动作时应允许或拒绝”的项目级安全需求真源。
#
# 职责
#   绑定双方权限组、动作与资源归属关系｜保存用户确认来源｜提供不含执行细节的稳定指纹。
#
# 边界
#   不包含 HTTP 路径、秘密、Observer、Runner 或生成后的 Contract/Profile 内容。
#
# 调用链
#   PermissionIntentService → PermissionIntent → Repository / SecuritySetupCompiler
# =============================================================================

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from product.backend.core.identifiers import PROJECT_ID_PATTERN, SHA256_PATTERN
from product.backend.core.verification.permissions import PermissionExpectation


_ACTION_ID_PATTERN = r"^action_[0-9a-f]{32}$"
_ROLE_ID_PATTERN = r"^role_[0-9a-f]{32}$"
_INTENT_ID_PATTERN = r"^pin_[0-9a-f]{32}$"


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


def permission_intent_sha256(payload: dict[str, Any]) -> str:
    """只对确认语义做规范化摘要，不让审计时间影响同一输入的身份。"""

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class PermissionIntent(PermissionIntentModel):
    intent_id: str = Field(pattern=_INTENT_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    action_candidate_id: str = Field(pattern=_ACTION_ID_PATTERN)
    subject_role_candidate_id: str = Field(pattern=_ROLE_ID_PATTERN)
    resource_owner_role_candidate_id: str = Field(pattern=_ROLE_ID_PATTERN)
    relation: PermissionIntentRelation
    expectation: PermissionExpectation
    confirmation_source: Literal["USER"] = "USER"
    confirmed_by: str = Field(min_length=1, max_length=128)
    fingerprint: str = Field(pattern=SHA256_PATTERN)
    confirmed_at_us: int = Field(ge=0)
    created_at_us: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_intent(self) -> PermissionIntent:
        if self.updated_at_us < self.created_at_us:
            raise ValueError("permission intent update time precedes creation")
        if self.confirmed_at_us > self.updated_at_us:
            raise ValueError("permission intent confirmation time exceeds update time")
        if self.confirmed_by != self.confirmed_by.strip() or any(
            ord(char) < 32 for char in self.confirmed_by
        ):
            raise ValueError("permission intent actor must be trimmed printable text")
        same_role = self.subject_role_candidate_id == self.resource_owner_role_candidate_id
        if self.relation in {
            PermissionIntentRelation.OWNS,
            PermissionIntentRelation.SAME_ROLE_OTHER_ACCOUNT,
        } and not same_role:
            raise ValueError("same-role permission intent must reference one role group")
        if self.relation is PermissionIntentRelation.OTHER_ROLE and same_role:
            raise ValueError("other-role permission intent must reference different role groups")
        semantic = self.model_dump(
            mode="json",
            exclude={
                "intent_id",
                "fingerprint",
                "confirmed_at_us",
                "created_at_us",
                "updated_at_us",
            },
        )
        if self.fingerprint != permission_intent_sha256(semantic):
            raise ValueError("permission intent fingerprint is inconsistent")
        expected_id = f"pin_{self.fingerprint[:32]}"
        if self.intent_id != expected_id:
            raise ValueError("permission intent ID is inconsistent")
        return self


__all__ = [
    "PermissionIntent",
    "PermissionIntentRelation",
    "permission_intent_sha256",
]
