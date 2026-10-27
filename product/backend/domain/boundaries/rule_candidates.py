# 保存待人确认的对话规则；候选、具体例子和来源声明不构成正式权限。
from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_core import PydanticCustomError
from product.protocols.codec import decode_document

from product.backend.domain.boundaries.entities import BoundaryModel
from product.backend.domain.boundaries.proposals import (
    PERMISSION_ITEM_ID_PATTERN, ProposedActionItem, ProposedActorItem, ProposedPermissionItem,
)
from product.backend.domain.identifiers import PROJECT_ID_PATTERN
from product.backend.domain.boundaries.candidate_scenarios import RuleScenario, RuleScenarioInput, freeze_scenario
from product.backend.domain.boundaries.candidate_reviews import BoundaryReviewRecord
from product.backend.domain.boundaries.candidate_reviews import ReviewSuggestion, SavedReviewSuggestion, ReviewContext, SupportingNote, CoverageDependency
from product.backend.domain.boundaries.candidate_scope import RequirementSource, ScopeDecision, ScopeReference, CoverageLink, CoverageSuggestion

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


class CandidateContentFields(BoundaryModel):
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
    def unique_items(self) -> CandidateContentFields:
        for items in (self.actors, self.actions, self.permissions):
            if len({item.item_id for item in items}) != len(items):
                raise ValueError("候选内的局部引用不能重复")
        return self


# 此根由数据库与GUI/MCP独立读取，版本不向内部例子和业务建议传播。


class RuleCandidateContentInput(CandidateContentFields):
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


def freeze_candidate_content(value: RuleCandidateContentInput) -> RuleCandidateContent:
    return RuleCandidateContent(**value.model_dump(exclude={"scenarios"}),
        scenarios=tuple(freeze_scenario(item, value) for item in value.scenarios))


class ScopedCandidateContentInput(RuleCandidateContentInput):
    actions: tuple[ProposedActionItem, ...] = Field(default=(), max_length=100)
    permissions: tuple[ProposedPermissionItem, ...] = Field(default=(), max_length=200)
    examples: tuple[RuleExample, ...] = Field(default=(), max_length=400)
    requirement_sources: tuple[RequirementSource, ...] = Field(default=(), max_length=100)
    coverage_suggestions: tuple[CoverageSuggestion, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def distinct_sources(self):
        if len({item.requirement_id for item in self.requirement_sources}) != len(self.requirement_sources):
            raise ValueError("要求标识不能重复")
        if len({item.issue_id for item in self.coverage_suggestions}) != len(self.coverage_suggestions):
            raise ValueError("同一缺口的检查建议不能重复")
        return self


class ScopedCandidateContent(ScopedCandidateContentInput):
    scenarios: tuple[RuleScenario, ...] = Field(default=(), max_length=10)

    @model_validator(mode="after")
    def verified_scenarios(self):
        if any(freeze_scenario(item, self) != item for item in self.scenarios):
            raise ValueError("情境指纹与内容不一致")
        ids = {item.item_id for item in self.permissions}
        for index, item in enumerate(self.requirement_sources):
            if not set(item.permission_item_ids) <= ids:
                raise PydanticCustomError('requirement_permission_outside', '要求只能关联这份候选已有的权限项', {'source_index': index})
        for index, item in enumerate(self.coverage_suggestions):
            if not {target.permission_item_id for target in item.targets} <= ids:
                raise PydanticCustomError('coverage_permission_outside', '检查建议只能关联这份候选已有的权限项', {'source_index': index})
        return self


class RuleCandidateRevision(BoundaryModel):
    schema_version: Literal["1"] = "1"
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    candidate_id: str = Field(pattern=CANDIDATE_ID_PATTERN)
    revision: int = Field(ge=1)
    basis_id: str = Field(pattern=BASIS_ID_PATTERN)
    content: ScopedCandidateContent
    submitted_via: Literal["MCP", "LOCAL_GUI"]
    created_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def bounded_root(self):
        if len(self.model_dump_json().encode("utf-8")) > 1024 * 1024:
            raise ValueError("候选根不得超过1MiB")
        return self

    boundary_reviews: tuple[BoundaryReviewRecord, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def review_identity(self):
        if len({item.issue_id for item in self.boundary_reviews}) != len(self.boundary_reviews):
            raise ValueError("同一问题只保存最新决定，历史由候选修订保留")
        if any(item.output_revision > self.revision for item in self.boundary_reviews):
            raise ValueError("决定不能引用候选的未来修订")
        return self

    scope_decisions: tuple[ScopeDecision, ...] = Field(default=(), max_length=100)
    coverage_links: tuple[CoverageLink, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def scoped_identity(self):
        for records, key in ((self.scope_decisions, "requirement_id"), (self.coverage_links, "issue_id")):
            if len({getattr(item, key) for item in records}) != len(records) or any(item.output_revision > self.revision for item in records):
                raise ValueError("范围决定和覆盖关联必须属于当前或历史修订且不重复")
        return self

    scope_references: tuple[ScopeReference, ...] = Field(default=(), max_length=100)

    @model_validator(mode='after')
    def distinct_references(self):
        ids = {item.requirement_id for item in self.scope_references}
        if len(ids) != len(self.scope_references) or ids & {item.requirement_id for item in self.scope_decisions} or any(item.output_revision > self.revision for item in self.scope_references):
            raise ValueError('补充依据不得重复、覆盖另一决定或引用未来修订')
        return self

    review_suggestions: tuple[SavedReviewSuggestion, ...] = Field(default=(), max_length=20)
    review_contexts: tuple[ReviewContext, ...] = Field(default=(), max_length=20)
    supporting_notes: tuple[SupportingNote, ...] = Field(default=(), max_length=100)
    coverage_dependencies: tuple[CoverageDependency, ...] = Field(default=(), max_length=20)

    @model_validator(mode='after')
    def assisted_identity(self):
        for records, key in ((self.review_suggestions, 'issue_id'), (self.review_contexts, 'issue_id'),
                             (self.supporting_notes, 'note_id'), (self.coverage_dependencies, 'issue_id')):
            if len({getattr(item, key) for item in records}) != len(records):
                raise ValueError('辅助记录不能重复')
            if any(getattr(item, 'output_revision', 0) > self.revision for item in records):
                raise ValueError('辅助记录不能引用未来修订')
        records = {item.issue_id: item for item in self.boundary_reviews}
        if any(item.issue_id not in records or records[item.issue_id].decision_id != item.decision_id for item in self.review_contexts):
            raise ValueError('局部依赖必须对应同一次人工决定')
        return self

    document_type: Literal["jiejian.rule-candidate"] = "jiejian.rule-candidate"


def scoped_content(value):
    data = value.model_dump(exclude={"scenarios"})
    return ScopedCandidateContent(**data, scenarios=tuple(freeze_scenario(item, value) for item in getattr(value, "scenarios", ())))


def revised_candidate(current, **changes):
    values = current.model_dump(exclude={"content"})
    values["content"] = scoped_content(current.content)
    values.update(changes)
    return RuleCandidateRevision(**values)


def read_candidate_revision(payload: str):
    decode_document(payload.encode("utf-8"), document_type="jiejian.rule-candidate",
        version="1", limit=1024 * 1024)
    return RuleCandidateRevision.model_validate_json(payload, strict=True)


def rule_candidate_revision_schema():
    return RuleCandidateRevision.model_json_schema()


class RuleCandidateSave(BoundaryModel):
    operation_id: str = Field(pattern=OPERATION_ID_PATTERN)
    expected_basis_id: str = Field(pattern=BASIS_ID_PATTERN)
    candidate_id: str | None = Field(default=None, pattern=CANDIDATE_ID_PATTERN)
    expected_revision: int | None = Field(default=None, ge=1)
    content: ScopedCandidateContentInput
    merge: bool = False
    # 省略即保留；按稳定标识追加或修订。Agent只能提交建议，不能携带人工决定。
    review_suggestions: tuple[ReviewSuggestion, ...] = Field(default=(), max_length=20)
    supporting_notes: tuple[SupportingNote, ...] = Field(default=(), max_length=100)

    @model_validator(mode="after")
    def paired_revision(self) -> RuleCandidateSave:
        if (self.candidate_id is None) != (self.expected_revision is None):
            raise ValueError("修改候选必须同时携带候选ID和预期修订")
        return self
