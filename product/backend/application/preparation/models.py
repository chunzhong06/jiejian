# 动作级准备读模型；状态现场计算，不持久化 READY，也不代表正式检查或安全结论。

from enum import StrEnum
from typing import Literal

from pydantic import Field

from product.backend.domain.preparation.requirements import ActionAssuranceContract, AllocationMode, IdentityRequirementSlot
from product.backend.domain.boundaries.entities import BoundaryModel
from product.backend.domain.boundaries.permissions import PermissionIntentRevision


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
    business_label: str = ''


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
    permissions: tuple[PermissionIntentRevision, ...] = ()
    next_material: Literal['identity','execution','resource','evidence','recovery'] | None = None


class PreparationView(BoundaryModel):
    project_id: str
    actions: tuple[ActionPreparationView, ...]
    preparation_complete: bool
    recommended_action_id: str | None = None
    basis_fingerprint: str | None = None
    policy_epoch: int = 0
    source_fingerprint: str | None = None
    impacts: tuple['MaterialImpactView', ...] = ()


class MaterialImpactView(BoundaryModel):
    action_id: str
    action_label: str
    kind: Literal['identity','execution','resource','evidence','recovery']
    status: PreparationStatus
    reason_codes: tuple[str, ...]
    permission_ids: tuple[str, ...]
    member_id: str | None = None
    member_label: str = ''


__all__ = [
    "ActionPreparationView", "ActionTechnicalPreparationView",
    "EffectEvidencePreparationView", "IdentityPreparationView",
    "IdentitySlotPreparationView", "PreparationItemView", "PreparationStatus",
    "PreparationView", "ResourcePreparationView",
]
