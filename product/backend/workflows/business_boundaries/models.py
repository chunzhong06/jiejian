# Business Boundary API/GUI 共享的命令与只读投影；不暴露 ORM Row。

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.boundary_proposal import (
    BoundaryProposalBundle,
    BoundaryProposalDecision,
    ProposedActionItem,
    ProposedActorItem,
    ProposedPermissionItem,
)
from product.backend.core.business_boundary import (
    ActionImplementationBinding,
    ActorImplementationBinding,
    BusinessActionRevision,
    BusinessActorRevision,
)
from product.backend.core.identifiers import PROJECT_ID_PATTERN
from product.backend.core.permission_intent import PermissionIntentRevision


class BoundaryWorkflowModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, hide_input_in_errors=True
    )


class BoundaryProposalCommand(BoundaryWorkflowModel):
    proposed_actors: tuple[ProposedActorItem, ...] = Field(default=(), max_length=256)
    proposed_actions: tuple[ProposedActionItem, ...] = Field(default=(), max_length=512)
    proposed_permissions: tuple[ProposedPermissionItem, ...] = Field(default=(), max_length=1024)
    unresolved_questions: tuple[str, ...] = Field(default=(), max_length=128)
    provenance: str = Field(min_length=1, max_length=512)


class BoundaryDraftCandidate(BoundaryWorkflowModel):
    candidate_kind: str
    candidate_id: str
    display_name: str
    confidence: str


class BoundaryDraftView(BoundaryWorkflowModel):
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    application_understanding_revision: int = Field(ge=0)
    candidates: tuple[BoundaryDraftCandidate, ...]


class BoundaryProposalView(BoundaryWorkflowModel):
    proposal: BoundaryProposalBundle
    decision: BoundaryProposalDecision | None = None


class BoundaryProposalListView(BoundaryWorkflowModel):
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    proposals: tuple[BoundaryProposalView, ...]


class OfficialBoundaryActorSummary(BoundaryWorkflowModel):
    display_name: str
    description: str


class OfficialBoundaryEffectSummary(BoundaryWorkflowModel):
    business_label: str
    effect_kind: str
    resource_concept: str
    protected_projection: tuple[str, ...] = ()


class OfficialBoundaryActionSummary(BoundaryWorkflowModel):
    display_name: str
    effects: tuple[OfficialBoundaryEffectSummary, ...]


class OfficialBoundaryPermissionSummary(BoundaryWorkflowModel):
    subject: str
    action: str
    resource_owner: str
    relation: str
    expectation: str


class OfficialBoundaryRecipe(BoundaryWorkflowModel):
    application_display: str
    project_display: str
    actors: tuple[OfficialBoundaryActorSummary, ...]
    actions: tuple[OfficialBoundaryActionSummary, ...]
    permissions: tuple[OfficialBoundaryPermissionSummary, ...]
    proposal_command: BoundaryProposalCommand


class PermissionBoundaryStatus(BoundaryWorkflowModel):
    action_id: str
    action_revision: int = Field(ge=1)
    permission_semantics_confirmed: bool
    active_permission_count: int = Field(ge=0)
    stale_permission_count: int = Field(ge=0)
    allow_control_available: bool
    validation_contract_complete: bool
    reason_codes: tuple[str, ...] = ()


class BusinessBoundaryView(BoundaryWorkflowModel):
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    policy_epoch: int = Field(ge=0)
    actors: tuple[BusinessActorRevision, ...]
    actions: tuple[BusinessActionRevision, ...]
    actor_bindings: tuple[ActorImplementationBinding, ...]
    action_bindings: tuple[ActionImplementationBinding, ...]
    permission_intents: tuple[PermissionIntentRevision, ...]
    permission_statuses: tuple[PermissionBoundaryStatus, ...]


__all__ = [
    "BoundaryDraftCandidate", "BoundaryDraftView", "BoundaryProposalCommand",
    "BoundaryProposalListView", "BoundaryProposalView", "BusinessBoundaryView",
    "OfficialBoundaryActionSummary", "OfficialBoundaryActorSummary",
    "OfficialBoundaryEffectSummary", "OfficialBoundaryPermissionSummary",
    "OfficialBoundaryRecipe", "PermissionBoundaryStatus",
]
