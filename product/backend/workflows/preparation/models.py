# 动作级准备读模型；状态现场计算，不持久化 READY，也不代表正式检查或安全结论。

from enum import StrEnum

from pydantic import Field

from product.backend.core.assurance import (
    ActionAssuranceContract,
    AllocationMode,
    IdentityRequirementSlot,
)
from product.backend.core.business_boundary import BoundaryModel


class PreparationStatus(StrEnum):
    SATISFIED = "SATISFIED"
    NEEDS_USER = "NEEDS_USER"
    STALE = "STALE"
    BLOCKED = "BLOCKED"
    NOT_REQUIRED = "NOT_REQUIRED"


class PreparationItemView(BoundaryModel):
    status: PreparationStatus
    reason_codes: tuple[str, ...] = ()
    binding_fingerprint: str | None = None


class IdentitySlotPreparationView(PreparationItemView):
    requirement: IdentityRequirementSlot
    actor_display_name: str
    test_identity_id: str | None = None


class IdentityPreparationView(PreparationItemView):
    allocation_mode: AllocationMode
    slots: tuple[IdentitySlotPreparationView, ...]


class ResourcePreparationView(PreparationItemView):
    owner_slot_id: str
    owner_test_identity_id: str | None


class EffectEvidencePreparationView(PreparationItemView):
    effect_id: str


class ActionTechnicalPreparationView(BoundaryModel):
    execution: PreparationItemView
    resources: tuple[ResourcePreparationView, ...]
    effect_evidence: tuple[EffectEvidencePreparationView, ...]
    recovery: PreparationItemView


class ActionPreparationView(ActionTechnicalPreparationView):
    action_id: str
    action_revision: int = Field(ge=1)
    display_name: str
    assurance_contract_fingerprint: str
    assurance_contract: ActionAssuranceContract
    identity_requirements: IdentityPreparationView
    preparation_complete: bool
    reason_codes: tuple[str, ...]


class PreparationView(BoundaryModel):
    project_id: str
    actions: tuple[ActionPreparationView, ...]
    preparation_complete: bool


__all__ = [
    "ActionPreparationView", "ActionTechnicalPreparationView",
    "EffectEvidencePreparationView", "IdentityPreparationView",
    "IdentitySlotPreparationView", "PreparationItemView", "PreparationStatus",
    "PreparationView", "ResourcePreparationView",
]
