# 保存待人确认的对话规则；候选、具体例子和来源声明不构成正式权限。
from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from product.backend.core.boundaries.entities import BoundaryModel
from product.backend.core.boundaries.proposals import (
    PERMISSION_ITEM_ID_PATTERN, ProposedActionItem, ProposedActorItem, ProposedPermissionItem,
)
from product.backend.core.identifiers import PROJECT_ID_PATTERN

CANDIDATE_ID_PATTERN = r"^rcd_[0-9a-f]{32}$"
BASIS_ID_PATTERN = r"^rb_[0-9a-f]{64}$"
OPERATION_ID_PATTERN = r"^[0-9a-f]{32}$"


class RuleExample(BoundaryModel):
    description: str = Field(min_length=1, max_length=512)
    permission_item_id: str | None = Field(default=None, pattern=PERMISSION_ITEM_ID_PATTERN)
    uncovered_reason: str | None = Field(default=None, min_length=1, max_length=512)

    @model_validator(mode="after")
    def require_mapping_or_limitation(self) -> RuleExample:
        if (self.permission_item_id is None) == (self.uncovered_reason is None):
            raise ValueError("例子必须引用权限场景，或明确说明尚不能覆盖的原因")
        return self


class RuleCandidateContent(BoundaryModel):
    original_text: str = Field(min_length=1, max_length=4096)
    actors: tuple[ProposedActorItem, ...] = Field(default=(), max_length=20)
    actions: tuple[ProposedActionItem, ...] = Field(default=(), max_length=10)
    permissions: tuple[ProposedPermissionItem, ...] = Field(default=(), max_length=10)
    examples: tuple[RuleExample, ...] = Field(default=(), max_length=20)
    unresolved_questions: tuple[str, ...] = Field(default=(), max_length=10)
    unsupported_constraints: tuple[str, ...] = Field(default=(), max_length=10)

    @field_validator("original_text")
    @classmethod
    def bounded_original(cls, value: str) -> str:
        if not value.strip() or len(value.encode("utf-8")) > 4096:
            raise ValueError("规则原文必须非空且不超过4096字节")
        return value.strip()

    @field_validator("unresolved_questions", "unsupported_constraints")
    @classmethod
    def bounded_questions(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value.strip() or len(value) > 512 for value in values):
            raise ValueError("问题或限制必须是有界非空文本")
        return values

    @model_validator(mode="after")
    def unique_items(self) -> RuleCandidateContent:
        for items in (self.actors, self.actions, self.permissions):
            if len({item.item_id for item in items}) != len(items):
                raise ValueError("候选内的局部引用不能重复")
        return self


# 此根由数据库与GUI/MCP独立读取，版本不向内部例子和业务建议传播。
class RuleCandidateRevision(BoundaryModel):
    schema_version: Literal["1"] = "1"
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    candidate_id: str = Field(pattern=CANDIDATE_ID_PATTERN)
    revision: int = Field(ge=1)
    basis_id: str = Field(pattern=BASIS_ID_PATTERN)
    content: RuleCandidateContent
    submitted_via: Literal["MCP", "LOCAL_GUI"]
    created_at_us: int = Field(ge=0)


class RuleCandidateSave(BoundaryModel):
    operation_id: str = Field(pattern=OPERATION_ID_PATTERN)
    expected_basis_id: str = Field(pattern=BASIS_ID_PATTERN)
    candidate_id: str | None = Field(default=None, pattern=CANDIDATE_ID_PATTERN)
    expected_revision: int | None = Field(default=None, ge=1)
    content: RuleCandidateContent

    @model_validator(mode="after")
    def paired_revision(self) -> RuleCandidateSave:
        if (self.candidate_id is None) != (self.expected_revision is None):
            raise ValueError("修改候选必须同时携带候选ID和预期修订")
        return self
