# 规则候选追加修订、CAS头指针及操作回执；正式权限仍由原边界仓储保存。
from __future__ import annotations

import json
from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, select, update
from sqlalchemy.orm import Mapped, Session, mapped_column

from product.backend.core.boundaries.rule_candidates import RuleCandidateRevision, read_candidate_revision
from product.backend.core.boundaries.candidate_scenarios import RuleCandidateDecision, CandidateApprovalEntities
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
        ["rule_candidate_revisions.candidate_id", "rule_candidate_revisions.revision"], ondelete="RESTRICT"),
        CheckConstraint("(candidate_content_hash IS NULL) = (decision_set_digest IS NULL)", name="source_hashes_paired"))
    candidate_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposal_id: Mapped[str] = mapped_column(String(36), ForeignKey("boundary_proposals.proposal_id", ondelete="RESTRICT"), unique=True)
    candidate_content_hash: Mapped[str | None] = mapped_column(String(64))
    decision_set_digest: Mapped[str | None] = mapped_column(String(64))


class RuleCandidateReceiptRow(Base):
    __tablename__ = "rule_candidate_receipts"
    __table_args__ = (CheckConstraint("operation_kind IN ('SAVE','PROPOSE','DECIDE')", name="operation_kind_value"),
        ForeignKeyConstraint(["candidate_id", "revision"],
            ["rule_candidate_revisions.candidate_id", "rule_candidate_revisions.revision"], ondelete="RESTRICT"))
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.project_id", ondelete="RESTRICT"), primary_key=True)
    operation_kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    operation_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    candidate_id: Mapped[str] = mapped_column(String(36))
    revision: Mapped[int] = mapped_column(Integer)


class RuleCandidateDecisionRow(Base):
    __tablename__ = "rule_candidate_decisions"
    __table_args__ = (ForeignKeyConstraint(["candidate_id", "output_revision"],
        ["rule_candidate_revisions.candidate_id", "rule_candidate_revisions.revision"], ondelete="RESTRICT"),
        Index("ix_rule_candidate_decisions_revision", "candidate_id", "output_revision"))
    decision_id: Mapped[str] = mapped_column(String(38), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.project_id", ondelete="RESTRICT"))
    candidate_id: Mapped[str] = mapped_column(String(36))
    output_revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[str] = mapped_column(Text)


class RuleCandidateApprovalMappingRow(Base):
    __tablename__ = "rule_candidate_approval_mappings"
    __table_args__ = (ForeignKeyConstraint(["intent_id", "intent_revision"],
        ["permission_intent_revisions.intent_id", "permission_intent_revisions.revision"], ondelete="RESTRICT"),
        Index("ix_rule_candidate_approval_intent", "intent_id", "intent_revision"))
    proposal_id: Mapped[str] = mapped_column(String(36), ForeignKey("rule_candidate_proposals.proposal_id", ondelete="RESTRICT"), primary_key=True)
    permission_item_id: Mapped[str] = mapped_column(String(22), primary_key=True)
    intent_id: Mapped[str] = mapped_column(String(36))
    intent_revision: Mapped[int] = mapped_column(Integer)
    intent_hash: Mapped[str] = mapped_column(String(64))
    boundary_decision_id: Mapped[str] = mapped_column(String(36), ForeignKey("boundary_proposal_decisions.decision_id", ondelete="RESTRICT"))
    reused: Mapped[bool] = mapped_column(Boolean)
    scenario_decision_ids_json: Mapped[str] = mapped_column(Text)
    entity_references_json: Mapped[str | None] = mapped_column(Text)


class RuleCandidateRepository:
    def __init__(self, session: Session, known_secrets=()):
        self._session, self._secrets = session, known_secrets

    def get(self, project_id: str, candidate_id: str, revision: int | None = None):
        head = self._session.get(RuleCandidateRow, candidate_id)
        if head is None or head.project_id != project_id:
            return None
        row = self._session.get(RuleCandidateRevisionRow, (candidate_id, revision or head.revision))
        return None if row is None else read_candidate_revision(row.payload)

    def list(self, project_id: str, *, offset: int = 0, limit: int = 50):
        rows = self._session.scalars(select(RuleCandidateRow).where(RuleCandidateRow.project_id == project_id)
            .order_by(RuleCandidateRow.created_at_us.desc(), RuleCandidateRow.candidate_id).offset(offset).limit(limit)).all()
        return tuple(self.get(project_id, row.candidate_id, row.revision) for row in rows)

    def head_references(self, project_id: str):
        rows = self._session.execute(select(RuleCandidateRow.candidate_id, RuleCandidateRow.revision)
            .where(RuleCandidateRow.project_id == project_id).order_by(RuleCandidateRow.candidate_id)).all()
        return tuple({'candidate_id':row[0],'revision':row[1]} for row in rows)

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

    def link_proposal(self, candidate_id: str, revision: int, proposal_id: str, *, content_hash: str, decision_digest: str):
        self._session.add(RuleCandidateProposalRow(candidate_id=candidate_id, revision=revision, proposal_id=proposal_id,
            candidate_content_hash=content_hash, decision_set_digest=decision_digest))
        _flush(self._session)

    def proposal_source(self, proposal_id: str):
        row = self._session.scalar(select(RuleCandidateProposalRow).where(RuleCandidateProposalRow.proposal_id == proposal_id))
        return None if row is None else (row.candidate_id, row.revision, row.candidate_content_hash, row.decision_set_digest)

    def decisions(self, project_id: str, candidate_id: str, revision: int):
        rows = self._session.scalars(select(RuleCandidateDecisionRow).where(
            RuleCandidateDecisionRow.project_id == project_id, RuleCandidateDecisionRow.candidate_id == candidate_id,
            RuleCandidateDecisionRow.output_revision <= revision).order_by(RuleCandidateDecisionRow.output_revision)).all()
        return tuple(RuleCandidateDecision.model_validate_json(row.payload) for row in rows)

    def add_decision(self, value: RuleCandidateDecision):
        ensure_storage_payload_safe(value.model_dump(mode="json"), self._secrets)
        self._session.add(RuleCandidateDecisionRow(decision_id=value.decision_id, project_id=value.project_id,
            candidate_id=value.candidate_id, output_revision=value.output_revision, payload=value.model_dump_json()))
        _flush(self._session)

    def add_approval_mapping(self, *, proposal_id, permission_item_id, intent_id, intent_revision,
        intent_hash, boundary_decision_id, reused, scenario_decision_ids, entity_references):
        self._session.add(RuleCandidateApprovalMappingRow(proposal_id=proposal_id, permission_item_id=permission_item_id,
            intent_id=intent_id, intent_revision=intent_revision, intent_hash=intent_hash,
            boundary_decision_id=boundary_decision_id, reused=reused,
            scenario_decision_ids_json=json.dumps(scenario_decision_ids), entity_references_json=entity_references.model_dump_json()))
        _flush(self._session)

    def approval_mappings(self, *, proposal_id=None, intent_id=None, revision=None):
        query = select(RuleCandidateApprovalMappingRow)
        if proposal_id is not None:
            query = query.where(RuleCandidateApprovalMappingRow.proposal_id == proposal_id)
        else:
            query = query.where(RuleCandidateApprovalMappingRow.intent_id == intent_id,
                RuleCandidateApprovalMappingRow.intent_revision == revision)
        rows = self._session.scalars(query.order_by(RuleCandidateApprovalMappingRow.proposal_id,
            RuleCandidateApprovalMappingRow.permission_item_id)).all()
        return [{"proposal_id": row.proposal_id, "permission_item_id": row.permission_item_id,
            "intent_id": row.intent_id, "revision": row.intent_revision, "intent_hash": row.intent_hash,
            "boundary_decision_id": row.boundary_decision_id, "reused": row.reused,
            "scenario_decision_ids": json.loads(row.scenario_decision_ids_json),
            "entity_references": None if row.entity_references_json is None else CandidateApprovalEntities.model_validate_json(row.entity_references_json).model_dump(mode='json')} for row in rows]

    def receipt(self, project_id: str, kind: str, operation_id: str):
        row = self._session.get(RuleCandidateReceiptRow, (project_id, kind, operation_id))
        return None if row is None else (row.request_fingerprint, row.candidate_id, row.revision)

    def add_receipt(self, project_id: str, kind: str, operation_id: str, fingerprint: str, value: RuleCandidateRevision):
        self._session.add(RuleCandidateReceiptRow(project_id=project_id, operation_kind=kind, operation_id=operation_id,
            request_fingerprint=fingerprint, candidate_id=value.candidate_id, revision=value.revision))
        _flush(self._session)
