# 保存待人确认的对话规则；候选、具体例子和来源声明不构成正式权限。
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, field_validator, model_validator
from pydantic_core import PydanticCustomError

from product.backend.core.boundaries.entities import BoundaryModel
from product.backend.core.boundaries.proposals import (
    PERMISSION_ITEM_ID_PATTERN, ProposedActionItem, ProposedActorItem, ProposedPermissionItem,
)
from product.backend.core.identifiers import PROJECT_ID_PATTERN
from product.backend.core.boundaries.candidate_scenarios import RuleScenario, RuleScenarioInput, freeze_scenario

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


class LegacyRuleCandidateContent(BoundaryModel):
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
    def unique_items(self) -> LegacyRuleCandidateContent:
        for items in (self.actors, self.actions, self.permissions):
            if len({item.item_id for item in items}) != len(items):
                raise ValueError("候选内的局部引用不能重复")
        return self


# 此根由数据库与GUI/MCP独立读取，版本不向内部例子和业务建议传播。
class LegacyRuleCandidateRevision(BoundaryModel):
    schema_version: Literal["1"] = "1"
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    candidate_id: str = Field(pattern=CANDIDATE_ID_PATTERN)
    revision: int = Field(ge=1)
    basis_id: str = Field(pattern=BASIS_ID_PATTERN)
    content: LegacyRuleCandidateContent
    submitted_via: Literal["MCP", "LOCAL_GUI"]
    created_at_us: int = Field(ge=0)


class RuleCandidateContentInput(LegacyRuleCandidateContent):
    scenarios: tuple[RuleScenarioInput, ...] = Field(default=(), max_length=10)

    @model_validator(mode="after")
    def scenario_references(self):
        if len({item.scenario_id for item in self.scenarios}) != len(self.scenarios):
            raise PydanticCustomError("scenario_id_duplicate", "情境标识不能重复")
        permission_ids = {item.item_id for item in self.permissions}
        for scenario_index, scenario in enumerate(self.scenarios):
            try:
                freeze_scenario(scenario, self)
            except PydanticCustomError as exc:
                # 公开错误只补有限位置，原话及替换正文不进入异常上下文。
                raise PydanticCustomError(exc.type, exc.message_template, {"scenario_index": scenario_index}) from None
            for option_index, option in enumerate(scenario.options):
                if not {item.item_id for item in option.replacements} <= permission_ids:
                    raise PydanticCustomError("scenario_replacement_outside", "选项只能替换当前候选内的权限项",
                        {"scenario_index": scenario_index, "option_index": option_index})
        return self


class RuleCandidateContent(RuleCandidateContentInput):
    scenarios: tuple[RuleScenario, ...] = Field(default=(), max_length=10)

    @model_validator(mode="after")
    def verify_fingerprints(self):
        if any(freeze_scenario(item, self) != item for item in self.scenarios):
            raise ValueError("情境指纹与原话或候选内容不一致")
        return self


class RuleCandidateRevision(LegacyRuleCandidateRevision):
    schema_version: Literal["2"] = "2"
    content: RuleCandidateContent

    @model_validator(mode="after")
    def bounded_root(self):
        if len(self.model_dump_json().encode("utf-8")) > 1024 * 1024:
            raise ValueError("候选根不得超过1MiB")
        return self


def freeze_candidate_content(value: RuleCandidateContentInput) -> RuleCandidateContent:
    return RuleCandidateContent(**value.model_dump(exclude={"scenarios"}),
        scenarios=tuple(freeze_scenario(item, value) for item in value.scenarios))


_reader = TypeAdapter(Annotated[LegacyRuleCandidateRevision | RuleCandidateRevision, Field(discriminator="schema_version")])


def read_candidate_revision(payload: str):
    if len(payload.encode("utf-8")) > 1024 * 1024:
        raise ValueError("候选根不得超过1MiB")
    return _reader.validate_json(payload)


def rule_candidate_revision_schema():
    return _reader.json_schema()


class RuleCandidateSave(BoundaryModel):
    operation_id: str = Field(pattern=OPERATION_ID_PATTERN)
    expected_basis_id: str = Field(pattern=BASIS_ID_PATTERN)
    candidate_id: str | None = Field(default=None, pattern=CANDIDATE_ID_PATTERN)
    expected_revision: int | None = Field(default=None, ge=1)
    content: RuleCandidateContentInput

    @model_validator(mode="after")
    def paired_revision(self) -> RuleCandidateSave:
        if (self.candidate_id is None) != (self.expected_revision is None):
            raise ValueError("修改候选必须同时携带候选ID和预期修订")
        return self
