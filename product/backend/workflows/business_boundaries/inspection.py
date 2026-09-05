# 实时检查持久实现来源是否仍由当前 ApplicationUnderstanding 精确支撑。

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.application_understanding import (
    ActionCandidate,
    ApplicationUnderstanding,
    CandidateDecision,
    RoleCandidate,
)
from product.backend.core.boundary_proposal import ProposalCandidateKind
from product.backend.core.business_boundary import (
    ACTION_ID_PATTERN,
    ACTOR_ID_PATTERN,
    ActionImplementationBinding,
    ActorImplementationBinding,
    ImplementationBindingStatus,
    ImplementationCandidateSnapshot,
    SOURCE_PROPOSAL_ID_PATTERN,
)
from product.backend.core.identifiers import SHA256_PATTERN
from product.backend.workflows.business_boundaries.fingerprints import (
    candidate_source_snapshot,
)


class _InspectionModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, hide_input_in_errors=True
    )


class _ImplementationInspection(_InspectionModel):
    binding_exists: bool
    basis_version: int | None = Field(default=None, ge=1, le=2)
    source_candidate_ids: tuple[str, ...] = ()
    status: ImplementationBindingStatus
    reason_codes: tuple[str, ...] = ()
    binding_fingerprint: str | None = Field(default=None, pattern=SHA256_PATTERN)
    source_proposal_id: str | None = Field(
        default=None, pattern=SOURCE_PROPOSAL_ID_PATTERN
    )
    confirmed_at_us: int | None = Field(default=None, ge=0)
    bound_understanding_revision: int | None = Field(default=None, ge=0)
    current_understanding_revision: int = Field(ge=0)
    changed_candidate_ids: tuple[str, ...] = ()


class ActorImplementationInspection(_ImplementationInspection):
    actor_id: str = Field(pattern=ACTOR_ID_PATTERN)
    actor_revision: int = Field(ge=1)


class ActionImplementationInspection(_ImplementationInspection):
    action_id: str = Field(pattern=ACTION_ID_PATTERN)
    action_revision: int = Field(ge=1)


def inspect_actor_binding(
    actor_id: str,
    actor_revision: int,
    binding: ActorImplementationBinding | None,
    understanding: ApplicationUnderstanding,
) -> ActorImplementationInspection:
    values = _inspect_binding(
        binding,
        understanding,
        ProposalCandidateKind.ROLE,
        () if binding is None else binding.role_candidate_ids,
    )
    return ActorImplementationInspection(
        actor_id=actor_id,
        actor_revision=actor_revision,
        **values,
    )


def inspect_action_binding(
    action_id: str,
    action_revision: int,
    binding: ActionImplementationBinding | None,
    understanding: ApplicationUnderstanding,
) -> ActionImplementationInspection:
    values = _inspect_binding(
        binding,
        understanding,
        ProposalCandidateKind.ACTION,
        () if binding is None else binding.action_candidate_ids,
    )
    return ActionImplementationInspection(
        action_id=action_id,
        action_revision=action_revision,
        **values,
    )


def _inspect_binding(
    binding: ActorImplementationBinding | ActionImplementationBinding | None,
    understanding: ApplicationUnderstanding,
    kind: ProposalCandidateKind,
    candidate_ids: tuple[str, ...],
) -> dict[str, Any]:
    common = {
        "binding_exists": binding is not None,
        "basis_version": None if binding is None else binding.basis_version,
        "source_candidate_ids": candidate_ids,
        "binding_fingerprint": None if binding is None else binding.binding_fingerprint,
        "source_proposal_id": None if binding is None else binding.source_proposal_id,
        "confirmed_at_us": None if binding is None else binding.confirmed_at_us,
        "bound_understanding_revision": (
            None if binding is None else binding.understanding_revision
        ),
        "current_understanding_revision": understanding.revision,
    }
    if binding is None or not candidate_ids:
        return {
            **common,
            "status": ImplementationBindingStatus.MISSING,
            "reason_codes": ("IMPLEMENTATION_NOT_IDENTIFIED",),
            "changed_candidate_ids": (),
        }
    if binding.basis_version == 1 and (
        binding.understanding_revision != understanding.revision
        or binding.source_fingerprint != understanding.source_fingerprint
    ):
        return {
            **common,
            "status": ImplementationBindingStatus.STALE,
            "reason_codes": ("LEGACY_BINDING_REVIEW_REQUIRED",),
            "changed_candidate_ids": (),
        }

    current_candidates = _candidate_map(understanding, kind)
    snapshots = {item.candidate_id: item for item in binding.candidate_snapshots}
    reasons: set[str] = set()
    changed: set[str] = set()
    for candidate_id in candidate_ids:
        candidate = current_candidates.get(candidate_id)
        if candidate is None:
            reasons.add("CANDIDATE_MISSING")
            changed.add(candidate_id)
            continue
        if candidate.stale:
            reasons.add("CANDIDATE_STALE")
            changed.add(candidate_id)
        if candidate.decision is CandidateDecision.REJECTED:
            reasons.add("CANDIDATE_REJECTED")
            changed.add(candidate_id)
        if not candidate.evidence:
            reasons.add("IMPLEMENTATION_EVIDENCE_MISSING")
            changed.add(candidate_id)
        if binding.basis_version == 2:
            stored = snapshots[candidate_id]
            current = candidate_source_snapshot(kind, candidate)
            if current.candidate_fingerprint != stored.candidate_fingerprint:
                reasons.add("CANDIDATE_CHANGED")
                changed.add(candidate_id)
            if current.evidence_fingerprint != stored.evidence_fingerprint:
                reasons.add("IMPLEMENTATION_EVIDENCE_CHANGED")
                changed.add(candidate_id)

    reason_codes = _ordered_reasons(reasons)
    stale_reasons = {
        "CANDIDATE_MISSING",
        "CANDIDATE_STALE",
        "CANDIDATE_REJECTED",
        "CANDIDATE_CHANGED",
        "IMPLEMENTATION_EVIDENCE_CHANGED",
    }
    if reasons & stale_reasons:
        status = ImplementationBindingStatus.STALE
    elif "IMPLEMENTATION_EVIDENCE_MISSING" in reasons:
        status = ImplementationBindingStatus.MISSING
    else:
        status = ImplementationBindingStatus.CURRENT
    return {
        **common,
        "status": status,
        "reason_codes": reason_codes,
        "changed_candidate_ids": tuple(sorted(changed)),
    }


def _candidate_map(
    understanding: ApplicationUnderstanding,
    kind: ProposalCandidateKind,
) -> dict[str, RoleCandidate | ActionCandidate]:
    candidates = (
        understanding.role_candidates
        if kind is ProposalCandidateKind.ROLE
        else understanding.action_candidates
    )
    return {item.candidate_id: item for item in candidates}


def _ordered_reasons(reasons: set[str]) -> tuple[str, ...]:
    order = (
        "CANDIDATE_MISSING",
        "CANDIDATE_STALE",
        "CANDIDATE_REJECTED",
        "IMPLEMENTATION_EVIDENCE_MISSING",
        "CANDIDATE_CHANGED",
        "IMPLEMENTATION_EVIDENCE_CHANGED",
    )
    return tuple(value for value in order if value in reasons)


__all__ = [
    "ActionImplementationInspection",
    "ActorImplementationInspection",
    "inspect_action_binding",
    "inspect_actor_binding",
]
