# 保存不依赖权限替换的人工边界决定；分类不代表能力已支持或证据已经形成。
from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from product.backend.core.boundaries.entities import BoundaryModel, boundary_sha256


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
    from product.backend.core.boundaries.candidate_corrections import review_fingerprint, suggestion_dependency_fingerprint
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
