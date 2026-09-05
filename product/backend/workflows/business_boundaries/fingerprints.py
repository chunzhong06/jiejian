# 为 Proposal 与 ImplementationBinding 统一计算 Candidate 结构和证据指纹。

from __future__ import annotations

from product.backend.core.application_understanding import ActionCandidate, RoleCandidate
from product.backend.core.boundary_proposal import (
    CandidateSourceSnapshot,
    ProposalCandidateKind,
)
from product.backend.core.business_boundary import (
    ImplementationCandidateSnapshot,
    boundary_sha256,
)


def candidate_source_snapshot(
    kind: ProposalCandidateKind,
    candidate: RoleCandidate | ActionCandidate,
) -> CandidateSourceSnapshot:
    """只冻结实现身份和证据；展示、置信度与 triage 状态不进入指纹。"""

    evidence = _canonical_evidence(candidate)
    return CandidateSourceSnapshot(
        candidate_kind=kind,
        candidate_id=candidate.candidate_id,
        candidate_fingerprint=boundary_sha256(
            {
                "candidate_kind": kind.value,
                "candidate_id": candidate.candidate_id,
                "canonical_key": candidate.canonical_key,
                "origin": candidate.origin.value,
            }
        ),
        evidence_fingerprint=boundary_sha256({"evidence": evidence}),
    )


def legacy_candidate_source_snapshot(
    kind: ProposalCandidateKind,
    candidate: RoleCandidate | ActionCandidate,
) -> CandidateSourceSnapshot:
    """按历史指纹算法重算旧 Proposal 快照，不能用新算法改写历史审批条件。"""

    return CandidateSourceSnapshot(
        candidate_kind=kind,
        candidate_id=candidate.candidate_id,
        candidate_fingerprint=boundary_sha256(candidate.model_dump(mode="json")),
        evidence_fingerprint=boundary_sha256(
            {"evidence": _canonical_evidence(candidate)}
        ),
    )


def implementation_candidate_snapshot(
    source: CandidateSourceSnapshot,
) -> ImplementationCandidateSnapshot:
    return ImplementationCandidateSnapshot(
        candidate_id=source.candidate_id,
        candidate_fingerprint=source.candidate_fingerprint,
        evidence_fingerprint=source.evidence_fingerprint,
    )


def _canonical_evidence(
    candidate: RoleCandidate | ActionCandidate,
) -> list[dict[str, object]]:
    return sorted(
        (item.model_dump(mode="json") for item in candidate.evidence),
        key=lambda item: (
            item["relative_path"],
            item["line_start"],
            item["line_end"],
            item["symbol"] or "",
            item["detector"],
            item["content_sha256"],
        ),
    )


__all__ = [
    "candidate_source_snapshot",
    "implementation_candidate_snapshot",
    "legacy_candidate_source_snapshot",
]
