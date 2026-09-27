# 核对候选来源、绑定与来源快照，不自行激活权限。
from __future__ import annotations
from product.backend.core.applications.models import ApplicationUnderstanding, CandidateDecision
from product.backend.core.boundaries.proposals import BoundarySourceSnapshot, CandidateSourceSnapshot, ProposalCandidateKind, ProposedActionItem, ProposedActorItem, ProposedEffectItem
from product.backend.core.boundaries.entities import ActionImplementationBinding, ActorImplementationBinding, BusinessActionRevision, BusinessActorRevision, BusinessEffectDefinition, ImplementationCandidateSnapshot, boundary_sha256
from product.backend.core.errors import ErrorCode
from product.backend.workflows.business_boundaries.fingerprints import (
    candidate_source_snapshot,
    implementation_candidate_snapshot,
    legacy_candidate_source_snapshot,
)
from product.backend.workflows.business_boundaries.models import BoundaryProposalCommand
from . import validation as boundary_validation

def _actor_binding(item: ProposedActorItem,
    revision: BusinessActorRevision,
    source_proposal_id: str,
    understanding: ApplicationUnderstanding,
    now_us: int,
) -> ActorImplementationBinding:
    snapshots = _implementation_snapshots(
        ProposalCandidateKind.ROLE,
        item.source_candidate_ids,
        understanding,
    )
    payload = {
        "actor_id": revision.actor_id,
        "actor_revision": revision.revision,
        "understanding_revision": understanding.revision,
        "source_fingerprint": understanding.source_fingerprint,
        "role_candidate_ids": list(item.source_candidate_ids),
        "basis_version": 2,
        "source_proposal_id": source_proposal_id,
        "confirmed_at_us": now_us,
        "candidate_snapshots": [
            item.model_dump(mode="json") for item in snapshots
        ],
    }
    return ActorImplementationBinding(
        actor_id=revision.actor_id,
        actor_revision=revision.revision,
        understanding_revision=understanding.revision,
        source_fingerprint=understanding.source_fingerprint,
        basis_version=2,
        source_proposal_id=source_proposal_id,
        confirmed_at_us=now_us,
        role_candidate_ids=item.source_candidate_ids,
        candidate_snapshots=snapshots,
        binding_fingerprint=boundary_sha256(payload),
        updated_at_us=now_us,
    )


def _action_binding(item: ProposedActionItem,
    revision: BusinessActionRevision,
    source_proposal_id: str,
    understanding: ApplicationUnderstanding,
    now_us: int,
) -> ActionImplementationBinding:
    snapshots = _implementation_snapshots(
        ProposalCandidateKind.ACTION,
        item.source_candidate_ids,
        understanding,
    )
    payload = {
        "action_id": revision.action_id,
        "action_revision": revision.revision,
        "understanding_revision": understanding.revision,
        "source_fingerprint": understanding.source_fingerprint,
        "action_candidate_ids": list(item.source_candidate_ids),
        "basis_version": 2,
        "source_proposal_id": source_proposal_id,
        "confirmed_at_us": now_us,
        "candidate_snapshots": [
            item.model_dump(mode="json") for item in snapshots
        ],
    }
    return ActionImplementationBinding(
        action_id=revision.action_id,
        action_revision=revision.revision,
        understanding_revision=understanding.revision,
        source_fingerprint=understanding.source_fingerprint,
        basis_version=2,
        source_proposal_id=source_proposal_id,
        confirmed_at_us=now_us,
        action_candidate_ids=item.source_candidate_ids,
        candidate_snapshots=snapshots,
        binding_fingerprint=boundary_sha256(payload),
        updated_at_us=now_us,
    )


def _implementation_snapshots(
    kind: ProposalCandidateKind,
    candidate_ids: tuple[str, ...],
    understanding: ApplicationUnderstanding,
) -> tuple[ImplementationCandidateSnapshot, ...]:
    candidates = (
        understanding.role_candidates
        if kind is ProposalCandidateKind.ROLE
        else understanding.action_candidates
    )
    by_id = {item.candidate_id: item for item in candidates}
    return tuple(
        implementation_candidate_snapshot(
            candidate_source_snapshot(kind, by_id[candidate_id])
        )
        for candidate_id in candidate_ids
    )


def _binding_changed(
    stored: ActorImplementationBinding | ActionImplementationBinding | None,
    replacement: ActorImplementationBinding | ActionImplementationBinding,
) -> bool:
    """只比较批准技术来源；新 Proposal/time 本身不制造 rebind。"""

    if stored is None or stored.basis_version != 2:
        return True
    if isinstance(stored, ActorImplementationBinding) and isinstance(
        replacement,
        ActorImplementationBinding,
    ):
        return (
            stored.role_candidate_ids != replacement.role_candidate_ids
            or stored.candidate_snapshots != replacement.candidate_snapshots
        )
    if isinstance(stored, ActionImplementationBinding) and isinstance(
        replacement,
        ActionImplementationBinding,
    ):
        return (
            stored.action_candidate_ids != replacement.action_candidate_ids
            or stored.candidate_snapshots != replacement.candidate_snapshots
        )
    raise TypeError("implementation binding kind changed")


def _source_snapshot(understanding: ApplicationUnderstanding,
    command: BoundaryProposalCommand,
) -> BoundarySourceSnapshot:
    requested_roles = {
        candidate_id
        for item in command.proposed_actors
        for candidate_id in item.source_candidate_ids
    }
    requested_actions = {
        candidate_id
        for item in command.proposed_actions
        for candidate_id in item.source_candidate_ids
    }
    role_by_id = {item.candidate_id: item for item in understanding.role_candidates}
    action_by_id = {item.candidate_id: item for item in understanding.action_candidates}
    snapshots: list[CandidateSourceSnapshot] = []
    for candidate_id in sorted(requested_roles):
        candidate = role_by_id.get(candidate_id)
        if (
            candidate is None
            or candidate.stale
            or candidate.decision is CandidateDecision.REJECTED
        ):
            boundary_validation._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "角色来源候选不存在或已过期")
        snapshots.append(candidate_source_snapshot(ProposalCandidateKind.ROLE, candidate))
    for candidate_id in sorted(requested_actions):
        candidate = action_by_id.get(candidate_id)
        if (
            candidate is None
            or candidate.stale
            or candidate.decision is CandidateDecision.REJECTED
        ):
            boundary_validation._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "动作来源候选不存在或已过期")
        snapshots.append(candidate_source_snapshot(ProposalCandidateKind.ACTION, candidate))
    return BoundarySourceSnapshot(
        basis_version=2,
        application_understanding_revision=understanding.revision,
        source_fingerprint=_source_fingerprint(understanding),
        candidates=tuple(snapshots),
    )


def _validate_source_snapshot(snapshot: BoundarySourceSnapshot,
    understanding: ApplicationUnderstanding,
) -> None:
    if snapshot.basis_version == 1 and (
        snapshot.application_understanding_revision != understanding.revision
        or snapshot.source_fingerprint != _source_fingerprint(understanding)
    ):
        boundary_validation._raise(ErrorCode.BOUNDARY_PROPOSAL_SOURCE_STALE, "业务边界提案的来源事实已变化")
    roles = {item.candidate_id: item for item in understanding.role_candidates}
    actions = {item.candidate_id: item for item in understanding.action_candidates}
    for expected in snapshot.candidates:
        candidate = (roles if expected.candidate_kind is ProposalCandidateKind.ROLE else actions).get(expected.candidate_id)
        actual = (
            None
            if candidate is None
            else (
                legacy_candidate_source_snapshot(expected.candidate_kind, candidate)
                if snapshot.basis_version == 1
                else candidate_source_snapshot(expected.candidate_kind, candidate)
            )
        )
        if (
            candidate is None
            or candidate.stale
            or candidate.decision is CandidateDecision.REJECTED
            or actual != expected
        ):
            boundary_validation._raise(ErrorCode.BOUNDARY_PROPOSAL_SOURCE_STALE, "业务边界提案的候选来源已变化")


def _source_fingerprint(understanding: ApplicationUnderstanding) -> str:
    return understanding.source_fingerprint or boundary_sha256({"source_fingerprint": None})


def _effect(effect_id: str, proposed: ProposedEffectItem) -> BusinessEffectDefinition:
    return BusinessEffectDefinition(
        effect_id=effect_id,
        business_label=proposed.business_label,
        effect_kind=proposed.effect_kind,
        resource_concept=proposed.resource_concept,
        expected_state=proposed.expected_state,
        protected_projection=proposed.protected_projection,
        description=proposed.description,
    )
