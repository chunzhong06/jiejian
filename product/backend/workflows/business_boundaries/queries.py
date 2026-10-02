# 读取既有事务中的边界事实与审阅投影；不写正式权限。
from __future__ import annotations
from product.backend.core.preparation.requirements import compile_action_assurance
from dataclasses import dataclass
from product.backend.core.applications.models import ApplicationUnderstanding, CandidateDecision
from product.backend.core.boundaries.proposals import BoundaryProposalBundle
from product.backend.core.boundaries.entities import ActionImplementationBinding, ActorImplementationBinding, BusinessAction, BusinessActionRevision, BusinessActor, BusinessActorRevision
from product.backend.core.errors import ErrorCode
from product.backend.core.boundaries.permissions import PermissionIntentEffectiveState, PermissionIntentRevision
from product.backend.infra.storage import StorageUnitOfWork
from product.backend.workflows.business_boundaries.inspection import (
    ActionImplementationInspection,
    ActorImplementationInspection,
    inspect_action_binding,
    inspect_actor_binding,
)
from product.backend.workflows.business_boundaries.maintenance import proposal_change_summary
from product.backend.workflows.business_boundaries.models import BoundaryDraftCandidate, BoundaryDraftView, BoundaryProposalView, PermissionBoundaryStatus
from product.backend.workflows.business_boundaries.review import proposal_review
from . import validation as boundary_validation

@dataclass(frozen=True)
class _MaintenanceFacts:
    actor_roots: tuple[BusinessActor, ...]
    action_roots: tuple[BusinessAction, ...]
    actors: tuple[BusinessActorRevision, ...]
    actions: tuple[BusinessActionRevision, ...]
    permissions: tuple[PermissionIntentRevision, ...]
    actor_bindings: tuple[ActorImplementationBinding, ...]
    action_bindings: tuple[ActionImplementationBinding, ...]
    actor_inspections: tuple[ActorImplementationInspection, ...]
    action_inspections: tuple[ActionImplementationInspection, ...]
    understanding: ApplicationUnderstanding
    policy_epoch: int


def _discovery_preview(project_id: str, understanding: ApplicationUnderstanding) -> BoundaryDraftView:
    candidates = tuple(
        sorted(
            (
                *(
                    BoundaryDraftCandidate(
                        candidate_kind="ROLE",
                        candidate_id=item.candidate_id,
                        display_name=item.display_name,
                        confidence=item.confidence.value,
                    )
                    for item in understanding.role_candidates
                    if not item.stale and item.decision is not CandidateDecision.REJECTED
                ),
                *(
                    BoundaryDraftCandidate(
                        candidate_kind="ACTION",
                        candidate_id=item.candidate_id,
                        display_name=item.display_name,
                        confidence=item.confidence.value,
                    )
                    for item in understanding.action_candidates
                    if not item.stale and item.decision is not CandidateDecision.REJECTED
                ),
            ),
            key=lambda item: (item.candidate_kind, item.candidate_id),
        )
    )
    return BoundaryDraftView(
        project_id=project_id,
        application_understanding_revision=understanding.revision,
        candidates=candidates,
    )


def _maintenance_facts(work: StorageUnitOfWork,
    project_id: str,
    *, allow_empty: bool = False,
) -> _MaintenanceFacts:
    actor_roots = work.business_boundaries.list_actors(project_id)
    action_roots = work.business_boundaries.list_actions(project_id)
    if not allow_empty and not actor_roots and not action_roots:
        boundary_validation._raise(
            ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID,
            "项目尚未建立正式业务边界",
        )
    actors = tuple(
        work.business_boundaries.actor_revision(
            root.actor_id,
            root.current_revision,
        )
        for root in actor_roots
    )
    actions = tuple(
        work.business_boundaries.action_revision(
            root.action_id,
            root.current_revision,
        )
        for root in action_roots
    )
    if any(item is None for item in (*actors, *actions)):
        boundary_validation._raise(
            ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID,
            "业务边界 root 指向不存在的 revision",
        )
    current_actors = tuple(item for item in actors if item is not None)
    current_actions = tuple(item for item in actions if item is not None)
    permissions = work.permission_intents.list_latest(project_id)
    state = work.permission_intents.policy_state(project_id)
    understanding = boundary_validation._understanding(work, project_id)
    actor_bindings = tuple(
        binding
        for item in current_actors
        if (
            binding := work.business_boundaries.actor_binding(
                item.actor_id,
                item.revision,
            )
        )
        is not None
    )
    action_bindings = tuple(
        binding
        for item in current_actions
        if (
            binding := work.business_boundaries.action_binding(
                item.action_id,
                item.revision,
            )
        )
        is not None
    )
    actor_binding_by_key = {
        (item.actor_id, item.actor_revision): item for item in actor_bindings
    }
    action_binding_by_key = {
        (item.action_id, item.action_revision): item for item in action_bindings
    }
    actor_inspections = tuple(
        inspect_actor_binding(
            item.actor_id,
            item.revision,
            actor_binding_by_key.get((item.actor_id, item.revision)),
            understanding,
        )
        for item in current_actors
    )
    action_inspections = tuple(
        inspect_action_binding(
            item.action_id,
            item.revision,
            action_binding_by_key.get((item.action_id, item.revision)),
            understanding,
        )
        for item in current_actions
    )
    return _MaintenanceFacts(
        actor_roots=actor_roots,
        action_roots=action_roots,
        actors=current_actors,
        actions=current_actions,
        permissions=permissions,
        actor_bindings=actor_bindings,
        action_bindings=action_bindings,
        actor_inspections=actor_inspections,
        action_inspections=action_inspections,
        understanding=understanding,
        policy_epoch=0 if state is None else state.policy_epoch,
    )


def _proposal_view(
    work: StorageUnitOfWork,
    proposal: BoundaryProposalBundle,
) -> BoundaryProposalView:
    review = proposal_review(work, proposal)
    # 沿用分类也必须基于这份提案的旧修订，不能被后来的权限写入改变。
    basis_permissions = tuple(value for item in proposal.proposed_permissions
        if item.intent_id is not None and item.expected_current_revision is not None
        and (value := work.permission_intents.get_revision(item.intent_id, item.expected_current_revision)) is not None
        and value.project_id == proposal.project_id)
    actor_bindings = tuple(
        binding
        for item in proposal.proposed_actors
        if item.actor_id is not None
        and item.expected_current_revision is not None
        and (
            binding := work.business_boundaries.actor_binding(
                item.actor_id,
                item.expected_current_revision,
            )
        )
        is not None
    )
    action_bindings = tuple(
        binding
        for item in proposal.proposed_actions
        if item.action_id is not None
        and item.expected_current_revision is not None
        and (
            binding := work.business_boundaries.action_binding(
                item.action_id,
                item.expected_current_revision,
            )
        )
        is not None
    )
    return BoundaryProposalView(
        proposal=proposal,
        decision=work.business_boundaries.decision_for_proposal(
            proposal.proposal_id
        ),
        change_summary=proposal_change_summary(
            proposal,
            basis_permissions,
            actor_bindings,
            action_bindings,
        ) if review.basis_state == "COMPLETE" else None,
        review=review,
    )


def current_permission_intents(
    latest: tuple[PermissionIntentRevision, ...],
    actors: tuple[BusinessActorRevision, ...],
    actions: tuple[BusinessActionRevision, ...],
) -> tuple[
    tuple[PermissionIntentRevision, ...],
    tuple[PermissionIntentRevision, ...],
]:
    """从 latest 历史中投影只精确引用当前 ACTIVE 边界的权限。"""

    actor_revisions = {item.actor_id: item.revision for item in actors}
    action_revisions = {item.action_id: item for item in actions}
    current: list[PermissionIntentRevision] = []
    stale: list[PermissionIntentRevision] = []
    for intent in latest:
        action = action_revisions.get(intent.business_action_id)
        effect_ids = set() if action is None else {
            effect.effect_id for effect in action.effect_catalog
        }
        is_current = (
            intent.effective_state is PermissionIntentEffectiveState.ACTIVE
            and actor_revisions.get(intent.subject_actor_id)
            == intent.subject_actor_revision
            and actor_revisions.get(intent.resource_owner_actor_id)
            == intent.resource_owner_actor_revision
            and action is not None
            and action.revision == intent.action_revision
            and set(intent.protected_effect_ids) <= effect_ids
        )
        (current if is_current else stale).append(intent)
    return tuple(current), tuple(stale)


def _permission_status(
    action: BusinessActionRevision,
    intents: tuple[PermissionIntentRevision, ...],
    stale_intents: tuple[PermissionIntentRevision, ...] = (),
) -> PermissionBoundaryStatus:
    active = tuple(
        item
        for item in intents
        if item.effective_state is PermissionIntentEffectiveState.ACTIVE
        and item.business_action_id == action.action_id
        and item.action_revision == action.revision
    )
    contract = compile_action_assurance(action, active)
    related_stale = tuple(
        item for item in stale_intents if item.business_action_id == action.action_id
    )
    allow_control = "ALLOW_CONTROL_REQUIRED" not in contract.reason_codes
    reasons: list[str] = []
    if not active:
        reasons.append(
            "PERMISSION_REVISION_REVIEW_REQUIRED"
            if related_stale
            else "PERMISSION_SEMANTICS_REQUIRED"
        )
    # 技术选择和身份实验缺口由 Preparation 投影，不把它们变成重新审批权限的要求。
    semantic_reasons = {
        "PERMISSION_SEMANTICS_REQUIRED", "PERMISSION_REVISION_REVIEW_REQUIRED",
        "PERMISSION_RELATION_REVIEW_REQUIRED", "ALLOW_CONTROL_REQUIRED",
    }
    reasons.extend(reason for reason in contract.reason_codes
                   if reason in semantic_reasons
                   and reason != "PERMISSION_SEMANTICS_REQUIRED" and reason not in reasons)
    return PermissionBoundaryStatus(
        action_id=action.action_id,
        action_revision=action.revision,
        permission_semantics_confirmed=bool(active),
        active_permission_count=len(active),
        stale_permission_count=len(related_stale),
        allow_control_available=allow_control,
        reason_codes=tuple(reasons),
    )
