# 定义有界业务情境和人的含义决定；选择只修改候选，不生成正式批准。
from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Literal

from pydantic import Field, model_validator

from product.backend.core.boundaries.entities import BoundaryModel, boundary_sha256
from product.backend.core.boundaries.proposals import ProposedPermissionItem
from product.backend.core.identifiers import PROJECT_ID_PATTERN, SHA256_PATTERN

SCENARIO_ID_PATTERN = r"^rsc_[0-9a-f]{16}$"
OPTION_ID_PATTERN = r"^rop_[0-9a-f]{16}$"


def normalized_rule_text(value: str) -> str:
    return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n")).strip()


class RuleScenarioOption(BoundaryModel):
    option_id: str = Field(pattern=OPTION_ID_PATTERN)
    label: str = Field(min_length=1, max_length=128)
    explanation: str = Field(min_length=1, max_length=512)
    replacements: tuple[ProposedPermissionItem, ...] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def unique_replacements(self):
        if len({item.item_id for item in self.replacements}) != len(self.replacements):
            raise ValueError("一个选项不能重复替换同一权限项")
        return self


class RuleScenarioInput(BoundaryModel):
    scenario_id: str = Field(pattern=SCENARIO_ID_PATTERN)
    original_excerpt: str = Field(min_length=1, max_length=512)
    occurrence: int = Field(default=1, ge=1, le=4096)
    question: str = Field(min_length=1, max_length=512)
    options: tuple[RuleScenarioOption, ...] = Field(min_length=2, max_length=4)

    @model_validator(mode="after")
    def bounded_options(self):
        if len({item.option_id for item in self.options}) != len(self.options):
            raise ValueError("同一情境的选项标识不能重复")
        item_sets = [{item.item_id for item in option.replacements} for option in self.options]
        if any(items != item_sets[0] for items in item_sets):
            raise ValueError("同一情境的各选项必须替换同一组权限项")
        return self


class RuleScenario(RuleScenarioInput):
    original_text_hash: str = Field(pattern=SHA256_PATTERN)
    scenario_fingerprint: str = Field(pattern=SHA256_PATTERN)


def freeze_scenario(scenario: RuleScenarioInput, content) -> RuleScenario:
    """只从保存的原文、实体及有限选项生成指纹；不接受客户端自述的确认来源。"""
    original = normalized_rule_text(content.original_text)
    excerpt = normalized_rule_text(scenario.original_excerpt)
    if not excerpt or original.count(excerpt) < scenario.occurrence:
        raise ValueError("情境摘录及出现序号必须对应规则原话")
    payload = scenario.model_dump(mode="json", include=set(RuleScenarioInput.model_fields))
    text_hash = hashlib.sha256(original.encode("utf-8")).hexdigest()
    fingerprint = boundary_sha256({"original_text_hash": text_hash, "scenario": payload,
        "actors": [item.model_dump(mode="json") for item in content.actors],
        "actions": [item.model_dump(mode="json") for item in content.actions]})
    return RuleScenario.model_validate_json(json.dumps({**payload,
        "original_text_hash": text_hash, "scenario_fingerprint": fingerprint}))


class RuleCandidateDecide(BoundaryModel):
    operation_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    expected_basis_id: str = Field(pattern=r"^rb_[0-9a-f]{64}$")
    expected_revision: int = Field(ge=1)
    scenario_id: str = Field(pattern=SCENARIO_ID_PATTERN)
    scenario_fingerprint: str = Field(pattern=SHA256_PATTERN)
    action: Literal["SELECT", "CORRECT", "DEFER", "DISMISS"]
    option_id: str | None = Field(default=None, pattern=OPTION_ID_PATTERN)
    correction: str | None = Field(default=None, min_length=1, max_length=2048)

    @model_validator(mode="after")
    def action_payload(self):
        if (self.option_id is not None) != (self.action == "SELECT"):
            raise ValueError("只有选择含义时可以提供选项")
        if (self.correction is not None) != (self.action in {"CORRECT", "DISMISS"}):
            raise ValueError("纠正或结束不适用情境必须说明原因")
        if self.correction is not None and not self.correction.strip():
            raise ValueError("请填写实际含义或不适用原因")
        return self


# 独立持久根由GUI和候选来源查询读取，来源恒为本机用户，MCP不能提交此记录。
class RuleCandidateDecision(RuleCandidateDecide):
    schema_version: Literal["1"] = "1"
    decision_id: str = Field(pattern=r"^rcdcn_[0-9a-f]{32}$")
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    candidate_id: str = Field(pattern=r"^rcd_[0-9a-f]{32}$")
    output_revision: int = Field(ge=2)
    submitted_via: Literal["LOCAL_GUI"] = "LOCAL_GUI"
    request_fingerprint: str = Field(pattern=SHA256_PATTERN)
    created_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def adjacent_revision(self):
        if self.output_revision != self.expected_revision + 1:
            raise ValueError("人的决定必须对应相邻的候选修订")
        return self


class CandidateActorReference(BoundaryModel):
    item_id: str = Field(pattern=r'^pactr_[0-9a-f]{16}$')
    actor_id: str = Field(pattern=r'^bar_[0-9a-f]{32}$')
    revision: int = Field(ge=1)


class CandidateActionReference(BoundaryModel):
    item_id: str = Field(pattern=r'^pactn_[0-9a-f]{16}$')
    action_id: str = Field(pattern=r'^bac_[0-9a-f]{32}$')
    revision: int = Field(ge=1)


class CandidateEffectReference(BoundaryModel):
    item_id: str = Field(pattern=r'^peff_[0-9a-f]{16}$')
    effect_id: str = Field(pattern=r'^bef_[0-9a-f]{32}$')


# 批准映射中的有限子结构；与同一映射行一起读取，不另设根格式版本。
class CandidateApprovalEntities(BoundaryModel):
    actors: tuple[CandidateActorReference, ...] = Field(min_length=1, max_length=2)
    action: CandidateActionReference
    effects: tuple[CandidateEffectReference, ...] = Field(min_length=1, max_length=16)
