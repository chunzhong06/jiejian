# 规则覆盖预览仅描述业务要求的匹配，不包含Run、网络请求或检查结论。
from __future__ import annotations

from typing import Annotated, Literal
from pydantic import Field
from product.backend.domain.boundaries.entities import BoundaryModel
from product.backend.domain.boundaries.permissions import PermissionIntentRelation


class ApprovedRuleReference(BoundaryModel):
    intent_id: str = Field(pattern=r"^pin_[0-9a-f]{32}$")
    revision: int = Field(ge=1)


class ApprovedRuleSet(BoundaryModel):
    kind: Literal["APPROVED"]
    rules: tuple[ApprovedRuleReference, ...] = Field(min_length=1, max_length=64)


class ProposalRuleSet(BoundaryModel):
    kind: Literal["PROPOSAL"]
    proposal_id: str = Field(pattern=r"^bpr_[0-9a-f]{32}$")


class CandidateRuleSet(BoundaryModel):
    kind: Literal["CANDIDATE"]
    candidate_id: str = Field(pattern=r"^rcd_[0-9a-f]{32}$")
    revision: int = Field(ge=1)


class RuleSituation(BoundaryModel):
    subject_id: str = Field(pattern=r"^(pactr_[0-9a-f]{16}|bar_[0-9a-f]{32})$")
    owner_id: str = Field(pattern=r"^(pactr_[0-9a-f]{16}|bar_[0-9a-f]{32})$")
    relation: PermissionIntentRelation
    action_id: str = Field(pattern=r"^(pactn_[0-9a-f]{16}|bac_[0-9a-f]{32})$")
    effect_id: str = Field(pattern=r"^(peff_[0-9a-f]{16}|bef_[0-9a-f]{32})$")


class RulePreviewCommand(BoundaryModel):
    reference: Annotated[ApprovedRuleSet | ProposalRuleSet | CandidateRuleSet, Field(discriminator="kind")]
    situation: RuleSituation | None = None
