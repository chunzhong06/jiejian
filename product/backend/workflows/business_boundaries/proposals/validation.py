# 业务边界的项目、提案、指纹和明确确认校验。
from __future__ import annotations
from product.backend.core.applications.models import ApplicationUnderstanding
from product.backend.core.boundaries.proposals import BoundaryProposalBundle
from product.backend.core.boundaries.entities import boundary_sha256
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage import StorageUnitOfWork


def _pending_proposal(work: StorageUnitOfWork,
    project_id: str,
    proposal_id: str,
    expected_fingerprint: str,
) -> BoundaryProposalBundle:
    proposal = work.business_boundaries.get_proposal(proposal_id)
    if proposal is None or proposal.project_id != project_id:
        _raise(ErrorCode.BOUNDARY_PROPOSAL_NOT_FOUND, "业务边界提案不存在")
    if work.business_boundaries.decision_for_proposal(proposal_id) is not None:
        _raise(ErrorCode.BOUNDARY_PROPOSAL_ALREADY_DECIDED, "业务边界提案已经作出决定")
    actual = boundary_sha256(proposal.fingerprint_payload())
    if actual != proposal.proposal_fingerprint or expected_fingerprint != actual:
        _raise(
            ErrorCode.BOUNDARY_PROPOSAL_FINGERPRINT_MISMATCH,
            "业务边界提案内容已变化，请重新打开后决定",
        )
    return proposal


def _understanding(work: StorageUnitOfWork, project_id: str) -> ApplicationUnderstanding:
    understanding = work.application_understanding.get(project_id)
    if understanding is None:
        raise JiejianError(ErrorCode.APPLICATION_UNDERSTANDING_NOT_FOUND, "应用理解记录不存在")
    return understanding


def _reason(value: str) -> str:
    if not isinstance(value, str):
        raise JiejianError(ErrorCode.INPUT_INVALID, "审批原因无效")
    clean = value.strip()
    if not clean or len(clean) > 512 or any(ord(char) < 32 for char in clean):
        raise JiejianError(ErrorCode.INPUT_INVALID, "审批原因无效")
    return clean


def _raise(code: ErrorCode, message: str) -> None:
    raise JiejianError(code, message)
