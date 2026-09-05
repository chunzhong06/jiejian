# Business Boundary API/GUI 共享的命令与只读投影；不暴露 ORM Row。

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from product.backend.core.boundary_proposal import (
    ACTION_ITEM_ID_PATTERN,
    ACTOR_ITEM_ID_PATTERN,
    EFFECT_ITEM_ID_PATTERN,
    INTENT_ID_PATTERN,
    PERMISSION_ITEM_ID_PATTERN,
    BoundaryProposalBundle,
    BoundaryProposalDecision,
    ProposalCandidateKind,
    ProposedActionItem,
    ProposedActorItem,
    ProposedEffectItem,
    ProposedPermissionItem,
)
from product.backend.core.business_boundary import (
    ACTION_ID_PATTERN,
    ACTOR_ID_PATTERN,
    BusinessActionOperationKind,
    BusinessActionRevision,
    BusinessActorRevision,
    BusinessRevisionState,
)
from product.backend.core.identifiers import PROJECT_ID_PATTERN, SHA256_PATTERN
from product.backend.core.permission_intent import (
    PermissionIntentEffectiveState,
    PermissionIntentRelation,
    PermissionIntentRevision,
)
from product.backend.core.permission_semantics import PermissionExpectation
from product.backend.workflows.business_boundaries.inspection import (
    ActionImplementationInspection,
    ActorImplementationInspection,
)


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


def _normalize_ids(values: tuple[str, ...], prefix: str) -> tuple[str, ...]:
    if len(set(values)) != len(values) or any(not value.startswith(prefix) for value in values):
        raise ValueError("maintenance source candidate IDs are invalid")
    return tuple(sorted(values))


class BoundaryMaintenanceCandidateOption(BoundaryWorkflowModel):
    candidate_kind: ProposalCandidateKind
    candidate_id: str
    display_name: str = Field(min_length=1, max_length=256)
    confidence: str
    evidence_available: bool

    @model_validator(mode="after")
    def validate_candidate_id(self) -> BoundaryMaintenanceCandidateOption:
        prefix = (
            "role_"
            if self.candidate_kind is ProposalCandidateKind.ROLE
            else "action_"
        )
        if not self.candidate_id.startswith(prefix):
            raise ValueError("maintenance candidate kind and ID are inconsistent")
        return self


class BoundaryMaintenanceActorItem(BoundaryWorkflowModel):
    item_id: str = Field(pattern=ACTOR_ITEM_ID_PATTERN)
    actor_id: str | None = Field(default=None, pattern=ACTOR_ID_PATTERN)
    expected_current_revision: int | None = Field(default=None, ge=1)
    display_name: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=1024)
    effective_state: BusinessRevisionState
    source_candidate_ids: tuple[str, ...] = Field(default=(), max_length=64)

    @field_validator("source_candidate_ids")
    @classmethod
    def normalize_sources(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _normalize_ids(values, "role_")

    @model_validator(mode="after")
    def validate_identity(self) -> BoundaryMaintenanceActorItem:
        if (self.actor_id is None) != (self.expected_current_revision is None):
            raise ValueError("maintenance actor identity and revision must appear together")
        return self


class BoundaryMaintenanceActionItem(BoundaryWorkflowModel):
    item_id: str = Field(pattern=ACTION_ITEM_ID_PATTERN)
    action_id: str | None = Field(default=None, pattern=ACTION_ID_PATTERN)
    expected_current_revision: int | None = Field(default=None, ge=1)
    display_name: str = Field(min_length=1, max_length=256)
    description: str = Field(min_length=1, max_length=1024)
    primary_resource_concept: str = Field(min_length=1, max_length=128)
    operation_kind: BusinessActionOperationKind
    state_changing: bool
    effects: tuple[ProposedEffectItem, ...] = Field(min_length=1, max_length=16)
    effective_state: BusinessRevisionState
    source_candidate_ids: tuple[str, ...] = Field(default=(), max_length=64)

    @field_validator("source_candidate_ids")
    @classmethod
    def normalize_sources(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _normalize_ids(values, "action_")

    @field_validator("effects")
    @classmethod
    def normalize_effects(
        cls, values: tuple[ProposedEffectItem, ...]
    ) -> tuple[ProposedEffectItem, ...]:
        if len({item.item_id for item in values}) != len(values):
            raise ValueError("maintenance effect item IDs must be unique")
        return tuple(sorted(values, key=lambda item: item.item_id))

    @model_validator(mode="after")
    def validate_identity(self) -> BoundaryMaintenanceActionItem:
        if (self.action_id is None) != (self.expected_current_revision is None):
            raise ValueError("maintenance action identity and revision must appear together")
        return self


class BoundaryMaintenancePermissionItem(BoundaryWorkflowModel):
    item_id: str = Field(pattern=PERMISSION_ITEM_ID_PATTERN)
    intent_id: str | None = Field(default=None, pattern=INTENT_ID_PATTERN)
    expected_current_revision: int | None = Field(default=None, ge=1)
    effective_state: PermissionIntentEffectiveState
    subject_actor_item_id: str = Field(pattern=ACTOR_ITEM_ID_PATTERN)
    business_action_item_id: str = Field(pattern=ACTION_ITEM_ID_PATTERN)
    resource_owner_actor_item_id: str = Field(pattern=ACTOR_ITEM_ID_PATTERN)
    relation: PermissionIntentRelation
    expectation: PermissionExpectation
    protected_effect_item_ids: tuple[str, ...] = Field(min_length=1, max_length=16)

    @field_validator("protected_effect_item_ids")
    @classmethod
    def normalize_effect_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values) or any(
            not value.startswith("peff_") for value in values
        ):
            raise ValueError("maintenance permission effect references are invalid")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_identity(self) -> BoundaryMaintenancePermissionItem:
        if (self.intent_id is None) != (self.expected_current_revision is None):
            raise ValueError("maintenance permission identity and revision must appear together")
        return self


class BoundaryMaintenanceCommand(BoundaryWorkflowModel):
    expected_boundary_state_fingerprint: str = Field(pattern=SHA256_PATTERN)
    actors: tuple[BoundaryMaintenanceActorItem, ...] = Field(max_length=256)
    actions: tuple[BoundaryMaintenanceActionItem, ...] = Field(max_length=512)
    permissions: tuple[BoundaryMaintenancePermissionItem, ...] = Field(max_length=1024)
    provenance: str = Field(min_length=1, max_length=512)

    @field_validator("actors", "actions", "permissions")
    @classmethod
    def normalize_items(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        if len({getattr(item, "item_id") for item in values}) != len(values):
            raise ValueError("maintenance local item IDs must be unique")
        return tuple(sorted(values, key=lambda item: getattr(item, "item_id")))


class BoundaryMaintenanceDraftView(BoundaryWorkflowModel):
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    boundary_state_fingerprint: str = Field(pattern=SHA256_PATTERN)
    actors: tuple[BoundaryMaintenanceActorItem, ...]
    actions: tuple[BoundaryMaintenanceActionItem, ...]
    permissions: tuple[BoundaryMaintenancePermissionItem, ...]
    candidate_options: tuple[BoundaryMaintenanceCandidateOption, ...]
    implementation_inspections: tuple[
        ActorImplementationInspection | ActionImplementationInspection, ...
    ]


class BoundaryProposalChangeSummary(BoundaryWorkflowModel):
    new_actor_count: int = Field(ge=0)
    new_action_count: int = Field(ge=0)
    business_revision_updates: tuple[str, ...] = ()
    retirements: tuple[str, ...] = ()
    permission_updates: tuple[str, ...] = ()
    permission_carry_forwards: tuple[str, ...] = ()
    permission_retirements: tuple[str, ...] = ()
    implementation_rebinds: tuple[str, ...] = ()
    unresolved_count: int = Field(ge=0)
    change_codes: tuple[str, ...] = ()


class BoundaryProposalView(BoundaryWorkflowModel):
    proposal: BoundaryProposalBundle
    decision: BoundaryProposalDecision | None = None
    change_summary: BoundaryProposalChangeSummary | None = None


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
    reason_codes: tuple[str, ...] = ()


class BusinessBoundaryView(BoundaryWorkflowModel):
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    policy_epoch: int = Field(ge=0)
    actors: tuple[BusinessActorRevision, ...]
    actions: tuple[BusinessActionRevision, ...]
    actor_bindings: tuple[ActorImplementationInspection, ...]
    action_bindings: tuple[ActionImplementationInspection, ...]
    permission_intents: tuple[PermissionIntentRevision, ...]
    permission_statuses: tuple[PermissionBoundaryStatus, ...]


__all__ = [
    "BoundaryDraftCandidate", "BoundaryDraftView", "BoundaryMaintenanceActionItem",
    "BoundaryMaintenanceActorItem", "BoundaryMaintenanceCandidateOption",
    "BoundaryMaintenanceCommand", "BoundaryMaintenanceDraftView",
    "BoundaryMaintenancePermissionItem", "BoundaryProposalChangeSummary",
    "BoundaryProposalCommand",
    "BoundaryProposalListView", "BoundaryProposalView", "BusinessBoundaryView",
    "OfficialBoundaryActionSummary", "OfficialBoundaryActorSummary",
    "OfficialBoundaryEffectSummary", "OfficialBoundaryPermissionSummary",
    "OfficialBoundaryRecipe", "PermissionBoundaryStatus",
]
