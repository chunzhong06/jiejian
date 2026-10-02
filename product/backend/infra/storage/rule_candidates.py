# 规则候选追加修订、CAS头指针及操作回执；正式权限仍由原边界仓储保存。
from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, ForeignKeyConstraint, Integer, String, Text, select, update
from sqlalchemy.orm import Mapped, Session, mapped_column

from product.backend.core.boundaries.rule_candidates import RuleCandidateRevision
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage.base import Base, _flush, ensure_storage_payload_safe


class RuleCandidateRow(Base):
    __tablename__ = "rule_candidates"
    __table_args__ = (CheckConstraint("revision >= 1", name="revision_positive"),)
    candidate_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.project_id", ondelete="RESTRICT"))
    revision: Mapped[int] = mapped_column(Integer)
    created_at_us: Mapped[int] = mapped_column(BigInteger)


class RuleCandidateRevisionRow(Base):
    __tablename__ = "rule_candidate_revisions"
    __table_args__ = (CheckConstraint("revision >= 1", name="revision_positive"),)
    candidate_id: Mapped[str] = mapped_column(String(36), ForeignKey("rule_candidates.candidate_id", ondelete="RESTRICT"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload: Mapped[str] = mapped_column(Text)


class RuleCandidateProposalRow(Base):
    __tablename__ = "rule_candidate_proposals"
    __table_args__ = (ForeignKeyConstraint(["candidate_id", "revision"],
        ["rule_candidate_revisions.candidate_id", "rule_candidate_revisions.revision"], ondelete="RESTRICT"),)
    candidate_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposal_id: Mapped[str] = mapped_column(String(36), ForeignKey("boundary_proposals.proposal_id", ondelete="RESTRICT"), unique=True)


class RuleCandidateReceiptRow(Base):
    __tablename__ = "rule_candidate_receipts"
    __table_args__ = (CheckConstraint("operation_kind IN ('SAVE','PROPOSE')", name="operation_kind_value"),
        ForeignKeyConstraint(["candidate_id", "revision"],
            ["rule_candidate_revisions.candidate_id", "rule_candidate_revisions.revision"], ondelete="RESTRICT"))
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.project_id", ondelete="RESTRICT"), primary_key=True)
    operation_kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    operation_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    candidate_id: Mapped[str] = mapped_column(String(36))
    revision: Mapped[int] = mapped_column(Integer)


class RuleCandidateRepository:
    def __init__(self, session: Session, known_secrets=()):
        self._session, self._secrets = session, known_secrets

    def get(self, project_id: str, candidate_id: str, revision: int | None = None):
        head = self._session.get(RuleCandidateRow, candidate_id)
        if head is None or head.project_id != project_id:
            return None
        row = self._session.get(RuleCandidateRevisionRow, (candidate_id, revision or head.revision))
        return None if row is None else RuleCandidateRevision.model_validate_json(row.payload)

    def list(self, project_id: str, *, offset: int = 0, limit: int = 50):
        rows = self._session.scalars(select(RuleCandidateRow).where(RuleCandidateRow.project_id == project_id)
            .order_by(RuleCandidateRow.created_at_us.desc(), RuleCandidateRow.candidate_id).offset(offset).limit(limit)).all()
        return tuple(self.get(project_id, row.candidate_id, row.revision) for row in rows)

    def append(self, value: RuleCandidateRevision, *, expected_revision: int | None):
        ensure_storage_payload_safe(value.model_dump(mode="json"), self._secrets)
        if expected_revision is None:
            self._session.add(RuleCandidateRow(candidate_id=value.candidate_id, project_id=value.project_id,
                revision=1, created_at_us=value.created_at_us))
            _flush(self._session)
        else:
            updated = self._session.execute(update(RuleCandidateRow).where(
                RuleCandidateRow.candidate_id == value.candidate_id, RuleCandidateRow.project_id == value.project_id,
                RuleCandidateRow.revision == expected_revision).values(revision=value.revision))
            if updated.rowcount != 1:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "候选已变化，请重新读取", details={"reason":"CONFLICT"})
        self._session.add(RuleCandidateRevisionRow(candidate_id=value.candidate_id, revision=value.revision,
            payload=value.model_dump_json()))
        _flush(self._session)

    def proposal_id(self, candidate_id: str, revision: int):
        row = self._session.get(RuleCandidateProposalRow, (candidate_id, revision))
        return None if row is None else row.proposal_id

    def link_proposal(self, candidate_id: str, revision: int, proposal_id: str):
        self._session.add(RuleCandidateProposalRow(candidate_id=candidate_id, revision=revision, proposal_id=proposal_id))
        _flush(self._session)

    def receipt(self, project_id: str, kind: str, operation_id: str):
        row = self._session.get(RuleCandidateReceiptRow, (project_id, kind, operation_id))
        return None if row is None else (row.request_fingerprint, row.candidate_id, row.revision)

    def add_receipt(self, project_id: str, kind: str, operation_id: str, fingerprint: str, value: RuleCandidateRevision):
        self._session.add(RuleCandidateReceiptRow(project_id=project_id, operation_kind=kind, operation_id=operation_id,
            request_fingerprint=fingerprint, candidate_id=value.candidate_id, revision=value.revision))
        _flush(self._session)
