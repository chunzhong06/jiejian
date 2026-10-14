# 保留要求来源与人的范围决定；发现的接口不能自动成为本轮权限，材料关联不代表验证通过。
from __future__ import annotations

from typing import Annotated, Literal
from pydantic import Field, model_validator
from product.backend.core.boundaries.entities import BoundaryModel, boundary_sha256


class RequirementSource(BoundaryModel):
    requirement_id: str = Field(pattern=r"^req_[0-9a-f]{16}$")
    title: str = Field(min_length=1, max_length=128)
    origin: Literal["USER", "SOURCE", "AGENT"]
    source_excerpt: str = Field(min_length=1, max_length=1024)
    interpretation: str = Field(min_length=1, max_length=1024)
    permission_item_ids: tuple[str, ...] = Field(default=(), max_length=200)

    @model_validator(mode="after")
    def meaningful(self):
        if any(not text.strip() for text in (self.title, self.source_excerpt, self.interpretation)):
            raise ValueError("要求来源及解释不得为空")
        if len(set(self.permission_item_ids)) != len(self.permission_item_ids):
            raise ValueError("要求关联的权限不能重复")
        return self


class ScopeDecisionCommand(BoundaryModel):
    operation_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    expected_basis_id: str = Field(pattern=r"^rb_[0-9a-f]{64}$")
    expected_revision: int = Field(ge=1)
    requirement_id: str = Field(pattern=r"^req_[0-9a-f]{16}$")
    requirement_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    disposition: Literal["IN_SCOPE", "PREPARATION", "OUT_OF_SCOPE", "DEFER"]
    requirement: str = Field(min_length=1, max_length=1024)
    reason: str = Field(min_length=1, max_length=512)
    time_scope: Literal["CHECK_WINDOW", "HISTORY", "NOT_APPLICABLE"]

    @model_validator(mode="after")
    def meaningful(self):
        if not self.requirement.strip() or not self.reason.strip():
            raise ValueError("请保留实际要求并说明范围判断依据")
        return self


class ScopeDecision(ScopeDecisionCommand):
    output_revision: int = Field(ge=2)
    created_at_us: int = Field(ge=0)
    submitted_via: Literal["LOCAL_GUI"] = "LOCAL_GUI"


class ScopeBatchChoice(BoundaryModel):
    requirement_id: str = Field(pattern=r"^req_[0-9a-f]{16}$")
    requirement_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    disposition: Literal["IN_SCOPE", "PREPARATION", "OUT_OF_SCOPE", "DEFER", "SUPPORTING"]
    requirement: str = Field(min_length=1, max_length=1024)
    reason: str = Field(min_length=1, max_length=512)
    time_scope: Literal["CHECK_WINDOW", "HISTORY", "NOT_APPLICABLE"]
    related_requirement_ids: tuple[Annotated[str, Field(pattern=r'^req_[0-9a-f]{16}$')], ...] = Field(default=(), max_length=100)

    @model_validator(mode="after")
    def meaningful(self):
        if not self.requirement.strip() or not self.reason.strip():
            raise ValueError("请保留实际要求并说明判断依据")
        if len(set(self.related_requirement_ids)) != len(self.related_requirement_ids):
            raise ValueError("关联要求不能重复")
        if self.disposition == 'SUPPORTING':
            if not self.related_requirement_ids or self.requirement_id in self.related_requirement_ids or self.time_scope != 'NOT_APPLICABLE':
                raise ValueError("补充依据必须关联其他已确认要求，时间范围沿用所关联要求")
        elif self.related_requirement_ids:
            raise ValueError("只有补充依据可以关联其他要求")
        return self


class ScopeBatchCommand(BoundaryModel):
    operation_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    expected_basis_id: str = Field(pattern=r"^rb_[0-9a-f]{64}$")
    expected_revision: int = Field(ge=1)
    choices: tuple[ScopeBatchChoice, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def distinct(self):
        if len({v.requirement_id for v in self.choices}) != len(self.choices):
            raise ValueError("同一要求不能重复提交决定")
        return self


class ScopeReference(ScopeBatchChoice):
    disposition: Literal['SUPPORTING'] = 'SUPPORTING'
    operation_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    expected_basis_id: str = Field(pattern=r"^rb_[0-9a-f]{64}$")
    expected_revision: int = Field(ge=1)
    # 固定被引用的人类决定；目标改义、改时间或撤销后须重新确认，不能成为永久免责。
    related_decision_fingerprints: tuple[Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')], ...] = Field(min_length=1, max_length=100)
    output_revision: int = Field(ge=2)
    created_at_us: int = Field(ge=0)
    submitted_via: Literal['LOCAL_GUI'] = 'LOCAL_GUI'

    @model_validator(mode='after')
    def paired_references(self):
        if len(self.related_requirement_ids) != len(self.related_decision_fingerprints):
            raise ValueError('关联要求与决定指纹必须逐项对应')
        return self


def scope_decision_fingerprint(decision):
    return boundary_sha256(decision.model_dump(mode='json', include={'requirement_id', 'requirement_fingerprint', 'disposition', 'requirement', 'time_scope'}))


def scope_items(value):
    decisions = {item.requirement_id: item for item in getattr(value, "scope_decisions", ())}
    references = {item.requirement_id: item for item in getattr(value, 'scope_references', ())}
    result = []
    for source in getattr(value.content, "requirement_sources", ()):
        # 权限映射由后续提案审阅；补齐映射不改变已经确认的原话和业务解释。
        semantic_source = source.model_dump(mode="json", exclude={"permission_item_ids"})
        fingerprint = boundary_sha256(["REQUIREMENT_MEANING", value.candidate_id, semantic_source])
        decision = references.get(source.requirement_id) or decisions.get(source.requirement_id)
        # 范围决定确认原话与解释，不批准正式规则。规则依据变化仍由候选CAS、提案和批准校验。
        # 旧决定按其保存时的basis复算原指纹，不改写历史，也不把新来源视为已确认。
        accepted = {fingerprint}
        if decision is not None:
            accepted.add(boundary_sha256([value.candidate_id, decision.expected_basis_id, semantic_source]))
        status = "NEEDS_DECISION" if decision is None else "STALE" if decision.requirement_fingerprint not in accepted else "DEFER" if decision.disposition == "DEFER" else "CONFIRMED"
        result.append({"source": source, "fingerprint": fingerprint, "status": status, "decision": decision})
    by_id = {item['source'].requirement_id: item for item in result}
    for item in result:
        reference = references.get(item['source'].requirement_id)
        if reference is None or item['status'] != 'CONFIRMED':
            continue
        for target_id, expected in zip(reference.related_requirement_ids, reference.related_decision_fingerprints):
            target = by_id.get(target_id)
            if target is None or target['status'] != 'CONFIRMED' or target['decision'].disposition != 'IN_SCOPE' or scope_decision_fingerprint(target['decision']) != expected:
                item['status'] = 'STALE'
                break
    return result


def scope_issues(value):
    if value.schema_version not in {"4", "5", "6"}:
        return []
    items = scope_items(value)
    if not items:
        return [{"code": "SCOPE_REQUIRED", "message": "先整理本轮目标与要求来源，再由你确认范围。源码发现不能直接当作业务要求。"}]
    issues, covered, pending_mapping = [], set(), set()
    active = {item.item_id for item in value.content.permissions if item.effective_state.value == "ACTIVE"}
    for item in items:
        source, decision = item["source"], item["decision"]
        linked = set(source.permission_item_ids) & active
        if item["status"] != "CONFIRMED":
            issues.append({"code": "SCOPE_DECISION_REQUIRED", "message": f"请确认本轮是否检查：{source.title}", "requirement_id": source.requirement_id})
            pending_mapping.update(linked)
            continue
        if decision.disposition == 'SUPPORTING':
            linked_targets = {key for target in items if target['source'].requirement_id in decision.related_requirement_ids and target['status'] == 'CONFIRMED' and target['decision'].disposition == 'IN_SCOPE' for key in target['source'].permission_item_ids}
            if not linked <= linked_targets:
                issues.append({'code':'REFERENCE_RULE_MISMATCH', 'message':f'补充依据关联的权限尚未由对应业务要求承接：{source.title}', 'requirement_id':source.requirement_id})
                pending_mapping.update(linked - linked_targets)
        elif decision.disposition == "IN_SCOPE":
            covered.update(linked)
            if not linked:
                issues.append({"code": "REQUIREMENT_RULE_REQUIRED", "message": f"已纳入的要求还没有对应权限：{source.title}", "requirement_id": source.requirement_id})
            if decision.time_scope == "HISTORY":
                issues.append({"code": "HISTORY_CAPABILITY_REQUIRED", "message": f"要求涉及历史范围，当前完整检查不能证明全部历史：{source.title}"})
        elif linked:
            issues.append({"code": "OUTSIDE_SCOPE_RULE", "message": f"这项已确认为准备步骤或不属本轮，仍被写成权限：{source.title}", "permission_item_ids": sorted(linked)})
            pending_mapping.update(linked)
    # 已由范围待定或关联冲突阻塞的权限不重复报下游缺口；没有任何来源的权限仍独立阻塞。
    missing = active - covered - pending_mapping
    if missing:
        issues.append({"code": "PERMISSION_SOURCE_REQUIRED", "message": "以下权限尚未关联已确认的本轮要求；必要的正常使用对照也应说明其对应要求。", "permission_item_ids": sorted(missing)})
    return issues


def only_auxiliary_scope(value):
    items = scope_items(value)
    return bool(items) and not value.content.permissions and all(item['status'] == 'CONFIRMED' and item['decision'].disposition in {'PREPARATION', 'OUT_OF_SCOPE'} for item in items)


class CoverageTarget(BoundaryModel):
    permission_item_id: str = Field(pattern=r"^pperm_[0-9a-f]{16}$")
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
    path: str = Field(pattern=r"^/[A-Za-z0-9_./{}-]{1,255}$")
    proof: Literal["EFFECT", "PROCESS_RECORD"]

    @model_validator(mode="after")
    def safe_path(self):
        import re
        # 只接受完整资源段占位，不把任意表达式、查询参数或绝对地址当入口。
        if ".." in self.path.split("/") or any(("{" in part or "}" in part) and not re.fullmatch(r"\{[A-Za-z_][A-Za-z0-9_]*\}", part) for part in self.path.split("/")):
            raise ValueError("检查入口必须是相对路径，资源占位须独占路径段")
        return self


class CoverageLinkCommand(BoundaryModel):
    operation_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    expected_basis_id: str = Field(pattern=r"^rb_[0-9a-f]{64}$")
    expected_revision: int = Field(ge=1)
    issue_id: str = Field(pattern=r"^bri_[0-9a-f]{64}$")
    issue_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_revision: int = Field(ge=2)
    time_scope: Literal["CHECK_WINDOW", "HISTORY"]
    targets: tuple[CoverageTarget, ...] = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=512)
    complete: bool = False

    @model_validator(mode="after")
    def meaningful(self):
        if not self.reason.strip() or len({(v.permission_item_id, v.method, v.path) for v in self.targets}) != len(self.targets):
            raise ValueError("请说明覆盖依据，且不要重复关联同一权限和入口")
        return self


class CoverageLink(CoverageLinkCommand):
    output_revision: int = Field(ge=2)
    created_at_us: int = Field(ge=0)
    submitted_via: Literal["LOCAL_GUI"] = "LOCAL_GUI"


class CoverageSuggestion(BoundaryModel):
    issue_id: str = Field(pattern=r'^bri_[0-9a-f]{64}$')
    targets: tuple[CoverageTarget, ...] = Field(min_length=1, max_length=100)
    time_scope: Literal['CHECK_WINDOW', 'HISTORY']
    explanation: str = Field(min_length=1, max_length=512)
