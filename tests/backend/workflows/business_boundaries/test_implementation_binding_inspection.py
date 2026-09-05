# 验证持久 Binding 的 v1/v2 来源在当前应用理解上实时产生可信状态。

from __future__ import annotations

from product.backend.core.application_understanding import (
    ApplicationUnderstanding,
    CandidateConfidence,
    CandidateDecision,
    CandidateEvidence,
    CandidateOrigin,
    RoleCandidate,
)
from product.backend.core.boundary_proposal import ProposalCandidateKind
from product.backend.core.business_boundary import (
    ActorImplementationBinding,
    ImplementationBindingStatus,
    boundary_sha256,
)
from product.backend.workflows.business_boundaries.fingerprints import (
    candidate_source_snapshot,
    implementation_candidate_snapshot,
)
from product.backend.workflows.business_boundaries.inspection import inspect_actor_binding


ACTOR_ID = "bar_" + "1" * 32
CANDIDATE_ID = "role_" + "2" * 32
SOURCE_A = "a" * 64
SOURCE_B = "b" * 64


def _evidence(*, content: str = "c" * 64) -> CandidateEvidence:
    return CandidateEvidence(
        relative_path="app/auth.py",
        line_start=10,
        line_end=14,
        symbol="ProjectOwner",
        detector="python-structure",
        content_sha256=content,
    )


def _candidate(
    *,
    decision: CandidateDecision = CandidateDecision.PROPOSED,
    stale: bool = False,
    evidence: tuple[CandidateEvidence, ...] = (_evidence(),),
    origin: CandidateOrigin = CandidateOrigin.DETECTED,
) -> RoleCandidate:
    return RoleCandidate(
        candidate_id=CANDIDATE_ID,
        canonical_key="project_owner",
        display_name="项目负责人",
        confidence=CandidateConfidence.HIGH,
        decision=decision,
        origin=origin,
        stale=stale,
        evidence=evidence,
    )


def _understanding(
    candidate: RoleCandidate | None,
    *,
    revision: int = 4,
    source_fingerprint: str = SOURCE_B,
) -> ApplicationUnderstanding:
    return ApplicationUnderstanding(
        project_id="inspection-case",
        source_root="D:/inspection-case",
        source_analysis_authorized=True,
        source_analysis_authorized_at_us=2,
        source_fingerprint=source_fingerprint,
        analysis_completed_at_us=3,
        role_candidates=() if candidate is None else (candidate,),
        revision=revision,
        created_at_us=1,
        updated_at_us=4,
    )


def _binding(candidate: RoleCandidate, *, basis_version: int) -> ActorImplementationBinding:
    candidate_ids = (candidate.candidate_id,)
    snapshots = (
        ()
        if basis_version == 1
        else (
            implementation_candidate_snapshot(
                candidate_source_snapshot(ProposalCandidateKind.ROLE, candidate)
            ),
        )
    )
    payload = {
        "actor_id": ACTOR_ID,
        "actor_revision": 1,
        "understanding_revision": 3,
        "source_fingerprint": SOURCE_A,
        "role_candidate_ids": list(candidate_ids),
    }
    if basis_version == 2:
        payload["basis_version"] = 2
        payload["source_proposal_id"] = "bpr_" + "4" * 32
        payload["confirmed_at_us"] = 5
        payload["candidate_snapshots"] = [
            item.model_dump(mode="json") for item in snapshots
        ]
    return ActorImplementationBinding(
        actor_id=ACTOR_ID,
        actor_revision=1,
        understanding_revision=3,
        source_fingerprint=SOURCE_A,
        basis_version=basis_version,
        source_proposal_id=("bpr_" + "4" * 32 if basis_version == 2 else None),
        confirmed_at_us=5 if basis_version == 2 else None,
        role_candidate_ids=candidate_ids,
        candidate_snapshots=snapshots,
        binding_fingerprint=boundary_sha256(payload),
        updated_at_us=5,
    )


def test_v2_ignores_unrelated_source_and_triage_changes() -> None:
    approved = _candidate()
    current = approved.model_copy(
        update={
            "display_name": "项目负责人（当前显示）",
            "confidence": CandidateConfidence.LOW,
            "decision": CandidateDecision.CONFIRMED,
        }
    )

    inspection = inspect_actor_binding(
        ACTOR_ID,
        1,
        _binding(approved, basis_version=2),
        _understanding(current),
    )

    assert inspection.status is ImplementationBindingStatus.CURRENT
    assert inspection.reason_codes == ()
    assert inspection.source_proposal_id == "bpr_" + "4" * 32
    assert inspection.confirmed_at_us == 5


def test_v2_rejected_stale_and_evidence_change_are_not_current() -> None:
    approved = _candidate()
    binding = _binding(approved, basis_version=2)
    cases = (
        (_candidate(decision=CandidateDecision.REJECTED), "CANDIDATE_REJECTED"),
        (_candidate(stale=True), "CANDIDATE_STALE"),
        (_candidate(evidence=(_evidence(content="d" * 64),)), "IMPLEMENTATION_EVIDENCE_CHANGED"),
    )

    for current, reason in cases:
        inspection = inspect_actor_binding(
            ACTOR_ID,
            1,
            binding,
            _understanding(current),
        )
        assert inspection.status is ImplementationBindingStatus.STALE
        assert reason in inspection.reason_codes
        assert inspection.changed_candidate_ids == (CANDIDATE_ID,)


def test_manual_candidate_without_evidence_is_missing() -> None:
    candidate = _candidate(evidence=(), origin=CandidateOrigin.MANUAL)
    inspection = inspect_actor_binding(
        ACTOR_ID,
        1,
        _binding(candidate, basis_version=2),
        _understanding(candidate),
    )

    assert inspection.status is ImplementationBindingStatus.MISSING
    assert inspection.reason_codes == ("IMPLEMENTATION_EVIDENCE_MISSING",)


def test_v1_requires_unchanged_global_source_before_candidate_checks() -> None:
    candidate = _candidate(decision=CandidateDecision.REVIEW_REQUIRED)
    binding = _binding(candidate, basis_version=1)

    changed = inspect_actor_binding(
        ACTOR_ID,
        1,
        binding,
        _understanding(candidate),
    )
    current = inspect_actor_binding(
        ACTOR_ID,
        1,
        binding,
        _understanding(candidate, revision=3, source_fingerprint=SOURCE_A),
    )

    assert changed.status is ImplementationBindingStatus.STALE
    assert changed.reason_codes == ("LEGACY_BINDING_REVIEW_REQUIRED",)
    assert current.status is ImplementationBindingStatus.CURRENT


def test_missing_binding_and_missing_candidate_are_distinct() -> None:
    candidate = _candidate()
    absent = inspect_actor_binding(
        ACTOR_ID,
        1,
        None,
        _understanding(candidate),
    )
    removed = inspect_actor_binding(
        ACTOR_ID,
        1,
        _binding(candidate, basis_version=2),
        _understanding(None),
    )

    assert absent.status is ImplementationBindingStatus.MISSING
    assert absent.reason_codes == ("IMPLEMENTATION_NOT_IDENTIFIED",)
    assert removed.status is ImplementationBindingStatus.STALE
    assert removed.reason_codes == ("CANDIDATE_MISSING",)
