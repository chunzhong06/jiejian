# 保存人工边界决定、纠正建议与依赖范围；建议不代替批准或既成证据。
from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from product.backend.domain.boundaries.entities import BoundaryModel, boundary_sha256


ReviewOutcome = Literal["NOT_SEPARATE_ACTION", "AGENT_OVERINTERPRETATION", "REPRESENTED_BY_RULES", "BUSINESS_RULE", "PREPARATION_DEPENDENCY", "EVIDENCE_GAP", "COVERAGE_GAP", "DEFER"]
RESOLVED_OUTCOMES = {"NOT_SEPARATE_ACTION", "AGENT_OVERINTERPRETATION", "REPRESENTED_BY_RULES"}


class BoundaryReviewCommand(BoundaryModel):
    operation_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    expected_basis_id: str = Field(pattern=r"^rb_[0-9a-f]{64}$")
    expected_revision: int = Field(ge=1)
    issue_id: str = Field(pattern=r"^bri_[0-9a-f]{64}$")
    issue_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    outcome: ReviewOutcome
    reason: str = Field(min_length=1, max_length=512)
    retained_requirement: str = Field(min_length=1, max_length=1024)
    permission_item_ids: tuple[str, ...] = Field(default=(), max_length=10)

    @model_validator(mode="after")
    def require_rules(self):
        if bool(self.permission_item_ids) != (self.outcome == "REPRESENTED_BY_RULES"):
            raise ValueError("确认已表达时必须引用候选内的权限项；其他分类不填写权限引用")
        if len(set(self.permission_item_ids)) != len(self.permission_item_ids):
            raise ValueError("权限引用不能重复")
        return self

    @field_validator("reason", "retained_requirement")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("请填写判断依据及仍保留的业务要求")
        return value.strip()


class BoundaryReviewRecord(BoundaryReviewCommand):
    decision_id: str = Field(pattern=r"^brd_[0-9a-f]{32}$")
    source: Literal["unresolved_questions", "unsupported_constraints"]
    text: str = Field(min_length=1, max_length=512)
    output_revision: int = Field(ge=2)
    submitted_via: Literal["LOCAL_GUI"] = "LOCAL_GUI"
    created_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def successor(self):
        if self.output_revision != self.expected_revision + 1:
            raise ValueError("人工决定必须生成紧邻的新修订")
        if self.source == "unsupported_constraints" and self.outcome in {"NOT_SEPARATE_ACTION", "REPRESENTED_BY_RULES"}:
            raise ValueError("不能用不单独建模消除能力限制")
        return self


def boundary_review_items(value):
    """沿用人确认的依赖范围；旧记录没有范围时仍保守失效，建议不能解除阻塞。"""
    records = {record.issue_id: record for record in getattr(value, "boundary_reviews", ())}
    contexts = {item.issue_id: item for item in getattr(value, 'review_contexts', ())}
    suggestions = {item.issue_id: item for item in getattr(value, 'review_suggestions', ())}
    content = value.content
    scene_questions = {item.question for item in getattr(content, "scenarios", ())}
    result = []
    for source in ("unresolved_questions", "unsupported_constraints"):
        occurrences = {}
        for index, text in enumerate(getattr(content, source)):
            occurrence = occurrences.get(text, 0)
            occurrences[text] = occurrence + 1
            issue_id = "bri_" + boundary_sha256([value.candidate_id, source, text, occurrence])
            context = contexts.get(issue_id)
            try:
                fingerprint = review_fingerprint(value, issue_id, None if context is None else context.dependencies)
            except ValueError:
                # 依赖被删除时必须失效；确定性标识支持回读，不能沿用旧决定。
                fingerprint = boundary_sha256([issue_id, 'MISSING_DEPENDENCY', value.revision])
            record = records.get(issue_id)
            # 已有情境继续走原含义选择，不能同时用新入口规避权限选项。
            if source == "unresolved_questions" and text in scene_questions:
                continue
            current = record is not None and record.issue_fingerprint == fingerprint
            status = "NEEDS_DECISION" if record is None else "STALE" if not current else "RESOLVED" if record.outcome in RESOLVED_OUTCOMES else "OPEN"
            suggestion = suggestions.get(issue_id)
            try:
                suggested = suggestion is not None and suggestion.issue_fingerprint == fingerprint and suggestion.dependency_fingerprint == suggestion_dependency_fingerprint(value, suggestion)
            except ValueError:
                suggested = False
            result.append({"issue_id": issue_id, "issue_fingerprint": fingerprint, "source": source,
                "text": text, "path": f'candidate.content.{source}[{index}]', "status": status, "blocking": status != "RESOLVED", "decision": record,
                'dependencies': None if context is None else context.dependencies,
                'suggestion': suggestion.model_dump(mode='json', exclude={'dependency_fingerprint'}) if suggested else None,
                'invalidation_reason': None if status != 'STALE' else '相关要求、规则或确认范围已变化' if context else '旧记录未保存关联范围，需要核对一次并保存关联要求'})
    return result


class BoundaryReviewGap(BoundaryModel):
    candidate_id: str = Field(pattern=r"^rcd_[0-9a-f]{32}$")
    revision: int = Field(ge=1)
    issue_id: str = Field(pattern=r"^bri_[0-9a-f]{64}$")
    message: str
    status: str
    review_url: str
    next_url: str | None = None
    next_label: str | None = None


class ReviewDependencies(BoundaryModel):
    requirement_ids: tuple[str, ...] = Field(min_length=1, max_length=100)
    permission_item_ids: tuple[str, ...] = Field(default=(), max_length=200)

    @model_validator(mode='after')
    def distinct(self):
        if any(len(set(items)) != len(items) for items in (self.requirement_ids, self.permission_item_ids)):
            raise ValueError('依赖引用不能重复')
        return self


class ReviewSuggestion(BoundaryModel):
    issue_id: str = Field(pattern=r'^bri_[0-9a-f]{64}$')
    issue_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    outcome: ReviewOutcome
    reason: str = Field(min_length=1, max_length=512)
    retained_requirement: str = Field(min_length=1, max_length=1024)
    permission_item_ids: tuple[str, ...] = Field(default=(), max_length=10)
    dependencies: ReviewDependencies | None = None

    @model_validator(mode='after')
    def meaningful(self):
        if not self.reason.strip() or not self.retained_requirement.strip():
            raise ValueError('纠正建议必须说明原因与承接的实际要求')
        if bool(self.permission_item_ids) != (self.outcome == 'REPRESENTED_BY_RULES'):
            raise ValueError('只有已被规则表达的建议填写承接权限')
        return self


class ContextualBoundaryReviewCommand(BoundaryReviewCommand):
    dependencies: ReviewDependencies | None = None


class SavedReviewSuggestion(ReviewSuggestion):
    dependency_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')


class ReviewContext(BoundaryModel):
    issue_id: str = Field(pattern=r'^bri_[0-9a-f]{64}$')
    decision_id: str = Field(pattern=r'^brd_[0-9a-f]{32}$')
    dependencies: ReviewDependencies
    # 保存人的确认范围；后续只能由GUI替换，不能从Agent的建议自动缩小。
    output_revision: int = Field(ge=2)


class SupportingNote(BoundaryModel):
    note_id: str = Field(pattern=r'^note_[0-9a-f]{16}$')
    kind: Literal['SOURCE_CLUE', 'TECHNICAL_PRECONDITION', 'CAPABILITY_INFORMATION']
    text: str = Field(min_length=1, max_length=1024)
    related_requirement_ids: tuple[str, ...] = Field(default=(), max_length=100)
    state: Literal['ACTIVE', 'WITHDRAWN'] = 'ACTIVE'
    withdrawal_reason: str | None = Field(default=None, min_length=1, max_length=512)

    @model_validator(mode='after')
    def withdrawal(self):
        if (self.state == 'WITHDRAWN') != (self.withdrawal_reason is not None):
            raise ValueError('撤回辅助说明必须记录原因；业务要求与旧问题仍须保留')
        if not self.text.strip() or self.withdrawal_reason is not None and not self.withdrawal_reason.strip():
            raise ValueError('辅助说明及撤回原因不得为空')
        return self


def dependency_payload(value, dependencies):
    """从要求推导完整权限、动作、角色闭包；不存在的引用和空关联均拒绝。"""
    content = value.content
    sources = {item.requirement_id: item for item in getattr(content, 'requirement_sources', ())}
    permissions = {item.item_id: item for item in content.permissions}
    required = set(dependencies.requirement_ids)
    ids = set(dependencies.permission_item_ids)
    if not required <= sources.keys() or not ids <= permissions.keys():
        raise ValueError('核对范围引用的要求或权限已不存在')
    # 关联同一权限的其他要求也属于依赖，客户端不能漏列后获得虚假的局部沿用。
    while True:
        old = (set(required), set(ids))
        ids.update(p for key in required for p in sources[key].permission_item_ids)
        required.update(key for key, source in sources.items() if ids.intersection(source.permission_item_ids))
        if old == (required, ids):
            break
    if not ids <= permissions.keys():
        raise ValueError('关联权限不完整')
    rules = [permissions[key] for key in sorted(ids)]
    actions = {item.item_id: item for item in content.actions}
    actors = {item.item_id: item for item in content.actors}
    action_ids = {item.business_action_item_id for item in rules}
    actor_ids = {key for item in rules for key in (item.subject_actor_item_id, item.resource_owner_actor_item_id)}
    if not action_ids <= actions.keys() or not actor_ids <= actors.keys():
        raise ValueError('局部核对需要候选携带完整角色、动作与结果定义')
    decisions = {item.requirement_id: item for item in getattr(value, 'scope_decisions', ())}
    references = {item.requirement_id: item for item in getattr(value, 'scope_references', ())}
    return {'sources': [sources[key].model_dump(mode='json') for key in sorted(required)],
        'scope': [{field: getattr(decisions[key], field) for field in ('disposition', 'requirement', 'time_scope')}
                  if key in decisions else references[key].model_dump(mode='json') if key in references else None for key in sorted(required)],
        'permissions': [item.model_dump(mode='json') for item in rules],
        'actors': [actors[key].model_dump(mode='json') for key in sorted(actor_ids)],
        'actions': [actions[key].model_dump(mode='json') for key in sorted(action_ids)]}


def review_fingerprint(value, issue_id, dependencies=None):
    if dependencies is None:
        business = value.content.model_dump(mode='json', include={'original_text', 'actors', 'actions', 'permissions'})
        return boundary_sha256([issue_id, value.basis_id, business])
    return boundary_sha256([issue_id, dependency_payload(value, dependencies)])


def suggestion_dependency_fingerprint(value, suggestion):
    if suggestion.dependencies is None:
        return boundary_sha256(value.content.model_dump(mode='json', include={'original_text','actors','actions','permissions','requirement_sources'}))
    payload = dependency_payload(value, suggestion.dependencies)
    # 建议绑定原文解释和实体；人的范围确认另由scope门禁核对，不使刚准备的建议整批过期。
    payload.pop('scope')
    return boundary_sha256(payload)


def coverage_dependency_fingerprint(value, targets):
    """覆盖关联另锁定目标权限的定义，不因局部边界决定沿用而漏掉权限变化。"""
    ids = {item.permission_item_id for item in targets}
    permissions = [item for item in value.content.permissions if item.item_id in ids]
    actions = {item.business_action_item_id for item in permissions}
    actors = {key for item in permissions for key in (item.subject_actor_item_id, item.resource_owner_actor_item_id)}
    return boundary_sha256([sorted(ids), [item.model_dump(mode='json') for item in permissions],
        [item.model_dump(mode='json') for item in value.content.actions if item.item_id in actions],
        [item.model_dump(mode='json') for item in value.content.actors if item.item_id in actors]])


class CoverageDependency(BoundaryModel):
    issue_id: str = Field(pattern=r'^bri_[0-9a-f]{64}$')
    output_revision: int = Field(ge=2)
    fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
