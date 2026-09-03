# Business Boundary 持久化：追加 revision/Decision，并维护实现绑定。
# Repository 不批准或更新 Proposal，也不计算 policy epoch 或读取 Candidate。

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from product.backend.core.boundary_proposal import (
    BoundaryProposalBundle,
    BoundaryProposalDecision,
    BoundarySourceSnapshot,
    ProposedActionItem,
    ProposedActorItem,
    ProposedPermissionItem,
)
from product.backend.core.business_boundary import (
    ActionImplementationBinding,
    ActorImplementationBinding,
    BusinessAction,
    BusinessActionRevision,
    BusinessActor,
    BusinessActorRevision,
)
from product.backend.infra.storage.base import (
    Base,
    _canonical_json,
    _flush,
    _scalar,
    _scalars,
    ensure_storage_payload_safe,
)


class BusinessActorRevisionRow(Base):
    __tablename__ = "business_actor_revisions"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(
            "effective_state IN ('ACTIVE', 'SUPERSEDED', 'RETIRED')",
            name="effective_state_value",
        ),
        Index("ix_business_actor_revisions_project", "project_id", "created_at_us"),
    )

    actor_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(1024), nullable=False)
    semantic_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_state: Mapped[str] = mapped_column(String(16), nullable=False)
    approval_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class BusinessActorRow(Base):
    __tablename__ = "business_actors"
    __table_args__ = (
        ForeignKeyConstraint(
            ["actor_id", "current_revision"],
            ["business_actor_revisions.actor_id", "business_actor_revisions.revision"],
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("current_revision >= 1", name="current_revision_positive"),
        CheckConstraint(
            "created_at_us >= 0 AND updated_at_us >= created_at_us",
            name="time_order",
        ),
        Index("ix_business_actors_project", "project_id", "updated_at_us"),
    )

    actor_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False
    )
    current_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class BusinessActionRevisionRow(Base):
    __tablename__ = "business_action_revisions"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(
            "effective_state IN ('ACTIVE', 'SUPERSEDED', 'RETIRED')",
            name="effective_state_value",
        ),
        CheckConstraint(
            "operation_kind IN ('READ', 'CHANGE', 'DELETE', 'EXPORT', 'ADMIN', 'CUSTOM')",
            name="operation_kind_value",
        ),
        Index("ix_business_action_revisions_project", "project_id", "created_at_us"),
    )

    action_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(String(1024), nullable=False)
    primary_resource_concept: Mapped[str] = mapped_column(String(128), nullable=False)
    operation_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    state_changing: Mapped[bool] = mapped_column(Boolean, nullable=False)
    effect_catalog_json: Mapped[str] = mapped_column(Text, nullable=False)
    semantic_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_state: Mapped[str] = mapped_column(String(16), nullable=False)
    approval_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class BusinessActionRow(Base):
    __tablename__ = "business_actions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["action_id", "current_revision"],
            ["business_action_revisions.action_id", "business_action_revisions.revision"],
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("current_revision >= 1", name="current_revision_positive"),
        CheckConstraint(
            "created_at_us >= 0 AND updated_at_us >= created_at_us",
            name="time_order",
        ),
        Index("ix_business_actions_project", "project_id", "updated_at_us"),
    )

    action_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False
    )
    current_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class BoundaryProposalRow(Base):
    __tablename__ = "boundary_proposals"
    __table_args__ = (Index("ix_boundary_proposals_project", "project_id", "created_at_us"),)

    proposal_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False
    )
    source_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_actors_json: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_actions_json: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_permissions_json: Mapped[str] = mapped_column(Text, nullable=False)
    unresolved_questions_json: Mapped[str] = mapped_column(Text, nullable=False)
    provenance: Mapped[str] = mapped_column(String(512), nullable=False)
    proposal_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class BoundaryProposalDecisionRow(Base):
    __tablename__ = "boundary_proposal_decisions"
    __table_args__ = (
        UniqueConstraint("proposal_id", name="uq_boundary_decision_proposal"),
        CheckConstraint("decision IN ('APPROVED', 'REJECTED')", name="decision_value"),
    )

    decision_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("boundary_proposals.proposal_id", ondelete="RESTRICT"), nullable=False
    )
    proposal_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    decided_by: Mapped[str] = mapped_column(String(128), nullable=False)
    decided_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str] = mapped_column(String(512), nullable=False)


class ActorImplementationBindingRow(Base):
    __tablename__ = "actor_implementation_bindings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["actor_id", "actor_revision"],
            ["business_actor_revisions.actor_id", "business_actor_revisions.revision"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('CURRENT', 'STALE', 'MISSING', 'AMBIGUOUS')",
            name="status_value",
        ),
    )

    actor_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    understanding_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    source_fingerprint: Mapped[str | None] = mapped_column(String(64))
    role_candidate_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_codes_json: Mapped[str] = mapped_column(Text, nullable=False)
    binding_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class ActionImplementationBindingRow(Base):
    __tablename__ = "action_implementation_bindings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["action_id", "action_revision"],
            ["business_action_revisions.action_id", "business_action_revisions.revision"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('CURRENT', 'STALE', 'MISSING', 'AMBIGUOUS')",
            name="status_value",
        ),
    )

    action_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    action_revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    understanding_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    source_fingerprint: Mapped[str | None] = mapped_column(String(64))
    action_candidate_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_codes_json: Mapped[str] = mapped_column(Text, nullable=False)
    binding_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class BusinessBoundaryRepository:
    """保存业务边界聚合；全部写入由外层同一个 UoW 提交。"""

    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def add_actor(self, actor: BusinessActor) -> None:
        self._add(BusinessActorRow, actor.model_dump(mode="json"))

    def replace_actor(self, actor: BusinessActor) -> None:
        row = _scalar(self._session, select(BusinessActorRow).where(BusinessActorRow.actor_id == actor.actor_id))
        if row is None:
            raise ValueError("business actor does not exist")
        self._replace(row, actor.model_dump(mode="json"))

    def actor(self, actor_id: str) -> BusinessActor | None:
        row = _scalar(self._session, select(BusinessActorRow).where(BusinessActorRow.actor_id == actor_id))
        return None if row is None else BusinessActor.model_validate(self._columns(row))

    def add_actor_revision(self, revision: BusinessActorRevision) -> None:
        values = revision.model_dump(mode="json", exclude={"approval"})
        values["approval_json"] = _canonical_json(revision.approval.model_dump(mode="json"))
        self._add(BusinessActorRevisionRow, values)

    def actor_revision(self, actor_id: str, revision: int) -> BusinessActorRevision | None:
        row = _scalar(self._session, select(BusinessActorRevisionRow).where(BusinessActorRevisionRow.actor_id == actor_id, BusinessActorRevisionRow.revision == revision))
        return None if row is None else self._actor_revision(row)

    def list_actor_revisions(self, project_id: str) -> tuple[BusinessActorRevision, ...]:
        rows = _scalars(self._session, select(BusinessActorRevisionRow).where(BusinessActorRevisionRow.project_id == project_id).order_by(BusinessActorRevisionRow.actor_id, BusinessActorRevisionRow.revision))
        return tuple(self._actor_revision(row) for row in rows)

    def list_actors(self, project_id: str) -> tuple[BusinessActor, ...]:
        rows = _scalars(self._session, select(BusinessActorRow).where(BusinessActorRow.project_id == project_id).order_by(BusinessActorRow.actor_id))
        return tuple(BusinessActor.model_validate(self._columns(row)) for row in rows)

    def add_action(self, action: BusinessAction) -> None:
        self._add(BusinessActionRow, action.model_dump(mode="json"))

    def replace_action(self, action: BusinessAction) -> None:
        row = _scalar(self._session, select(BusinessActionRow).where(BusinessActionRow.action_id == action.action_id))
        if row is None:
            raise ValueError("business action does not exist")
        self._replace(row, action.model_dump(mode="json"))

    def action(self, action_id: str) -> BusinessAction | None:
        row = _scalar(self._session, select(BusinessActionRow).where(BusinessActionRow.action_id == action_id))
        return None if row is None else BusinessAction.model_validate(self._columns(row))

    def add_action_revision(self, revision: BusinessActionRevision) -> None:
        values = revision.model_dump(mode="json", exclude={"effect_catalog", "approval"})
        values["effect_catalog_json"] = _canonical_json([item.model_dump(mode="json") for item in revision.effect_catalog])
        values["approval_json"] = _canonical_json(revision.approval.model_dump(mode="json"))
        self._add(BusinessActionRevisionRow, values)

    def action_revision(self, action_id: str, revision: int) -> BusinessActionRevision | None:
        row = _scalar(self._session, select(BusinessActionRevisionRow).where(BusinessActionRevisionRow.action_id == action_id, BusinessActionRevisionRow.revision == revision))
        return None if row is None else self._action_revision(row)

    def list_action_revisions(self, project_id: str) -> tuple[BusinessActionRevision, ...]:
        rows = _scalars(self._session, select(BusinessActionRevisionRow).where(BusinessActionRevisionRow.project_id == project_id).order_by(BusinessActionRevisionRow.action_id, BusinessActionRevisionRow.revision))
        return tuple(self._action_revision(row) for row in rows)

    def list_actions(self, project_id: str) -> tuple[BusinessAction, ...]:
        rows = _scalars(self._session, select(BusinessActionRow).where(BusinessActionRow.project_id == project_id).order_by(BusinessActionRow.action_id))
        return tuple(BusinessAction.model_validate(self._columns(row)) for row in rows)

    def add_proposal(self, proposal: BoundaryProposalBundle) -> None:
        values = {
            "proposal_id": proposal.proposal_id,
            "project_id": proposal.project_id,
            "source_snapshot_json": proposal.source_snapshot.model_dump_json(),
            "proposed_actors_json": _canonical_json([item.model_dump(mode="json") for item in proposal.proposed_actors]),
            "proposed_actions_json": _canonical_json([item.model_dump(mode="json") for item in proposal.proposed_actions]),
            "proposed_permissions_json": _canonical_json([item.model_dump(mode="json") for item in proposal.proposed_permissions]),
            "unresolved_questions_json": _canonical_json(list(proposal.unresolved_questions)),
            "provenance": proposal.provenance,
            "proposal_fingerprint": proposal.proposal_fingerprint,
            "created_at_us": proposal.created_at_us,
        }
        self._add(BoundaryProposalRow, values)

    def get_proposal(self, proposal_id: str) -> BoundaryProposalBundle | None:
        row = _scalar(self._session, select(BoundaryProposalRow).where(BoundaryProposalRow.proposal_id == proposal_id))
        return None if row is None else self._proposal(row)

    def list_proposals(self, project_id: str) -> tuple[BoundaryProposalBundle, ...]:
        rows = _scalars(self._session, select(BoundaryProposalRow).where(BoundaryProposalRow.project_id == project_id).order_by(BoundaryProposalRow.created_at_us, BoundaryProposalRow.proposal_id))
        return tuple(self._proposal(row) for row in rows)

    def add_decision(self, decision: BoundaryProposalDecision) -> None:
        values = decision.model_dump(mode="json")
        values["decision"] = decision.decision.value
        self._add(BoundaryProposalDecisionRow, values)

    def decision_for_proposal(self, proposal_id: str) -> BoundaryProposalDecision | None:
        row = _scalar(self._session, select(BoundaryProposalDecisionRow).where(BoundaryProposalDecisionRow.proposal_id == proposal_id))
        return None if row is None else BoundaryProposalDecision.model_validate_json(
            _canonical_json(self._columns(row))
        )

    def replace_actor_binding(self, binding: ActorImplementationBinding) -> None:
        self._upsert_binding(ActorImplementationBindingRow, (ActorImplementationBindingRow.actor_id == binding.actor_id, ActorImplementationBindingRow.actor_revision == binding.actor_revision), binding.model_dump(mode="json"), "role_candidate_ids")

    def actor_binding(self, actor_id: str, revision: int) -> ActorImplementationBinding | None:
        row = _scalar(self._session, select(ActorImplementationBindingRow).where(ActorImplementationBindingRow.actor_id == actor_id, ActorImplementationBindingRow.actor_revision == revision))
        return None if row is None else self._binding(row, ActorImplementationBinding, "role_candidate_ids")

    def replace_action_binding(self, binding: ActionImplementationBinding) -> None:
        self._upsert_binding(ActionImplementationBindingRow, (ActionImplementationBindingRow.action_id == binding.action_id, ActionImplementationBindingRow.action_revision == binding.action_revision), binding.model_dump(mode="json"), "action_candidate_ids")

    def action_binding(self, action_id: str, revision: int) -> ActionImplementationBinding | None:
        row = _scalar(self._session, select(ActionImplementationBindingRow).where(ActionImplementationBindingRow.action_id == action_id, ActionImplementationBindingRow.action_revision == revision))
        return None if row is None else self._binding(row, ActionImplementationBinding, "action_candidate_ids")

    def _add(self, row_type, values: dict[str, object]) -> None:
        ensure_storage_payload_safe(values, self._known_secrets)
        self._session.add(row_type(**values))
        _flush(self._session)

    def _replace(self, row, values: dict[str, object]) -> None:
        ensure_storage_payload_safe(values, self._known_secrets)
        for key, value in values.items():
            setattr(row, key, value)
        _flush(self._session)

    def _upsert_binding(self, row_type, conditions, values: dict[str, object], candidate_field: str) -> None:
        candidates = values.pop(candidate_field)
        reasons = values.pop("reason_codes")
        values[f"{candidate_field}_json"] = _canonical_json(list(candidates))
        values["reason_codes_json"] = _canonical_json(list(reasons))
        row = _scalar(self._session, select(row_type).where(*conditions))
        if row is None:
            self._add(row_type, values)
        else:
            self._replace(row, values)

    @staticmethod
    def _columns(row) -> dict[str, object]:
        return {column.name: getattr(row, column.name) for column in row.__table__.columns}

    @staticmethod
    def _actor_revision(row: BusinessActorRevisionRow) -> BusinessActorRevision:
        import json

        values = BusinessBoundaryRepository._columns(row)
        values["approval"] = json.loads(values.pop("approval_json"))
        return BusinessActorRevision.model_validate_json(_canonical_json(values))

    @staticmethod
    def _action_revision(row: BusinessActionRevisionRow) -> BusinessActionRevision:
        import json

        values = BusinessBoundaryRepository._columns(row)
        values["effect_catalog"] = json.loads(values.pop("effect_catalog_json"))
        values["approval"] = json.loads(values.pop("approval_json"))
        return BusinessActionRevision.model_validate_json(_canonical_json(values))

    @staticmethod
    def _proposal(row: BoundaryProposalRow) -> BoundaryProposalBundle:
        import json

        return BoundaryProposalBundle(
            proposal_id=row.proposal_id,
            project_id=row.project_id,
            source_snapshot=BoundarySourceSnapshot.model_validate_json(row.source_snapshot_json),
            proposed_actors=tuple(ProposedActorItem.model_validate_json(_canonical_json(item)) for item in json.loads(row.proposed_actors_json)),
            proposed_actions=tuple(ProposedActionItem.model_validate_json(_canonical_json(item)) for item in json.loads(row.proposed_actions_json)),
            proposed_permissions=tuple(ProposedPermissionItem.model_validate_json(_canonical_json(item)) for item in json.loads(row.proposed_permissions_json)),
            unresolved_questions=tuple(json.loads(row.unresolved_questions_json)),
            provenance=row.provenance,
            proposal_fingerprint=row.proposal_fingerprint,
            created_at_us=row.created_at_us,
        )

    @staticmethod
    def _binding(row, model_type, candidate_field: str):
        import json

        values = BusinessBoundaryRepository._columns(row)
        values[candidate_field] = json.loads(values.pop(f"{candidate_field}_json"))
        values["reason_codes"] = json.loads(values.pop("reason_codes_json"))
        return model_type.model_validate_json(_canonical_json(values))


__all__ = [
    "ActionImplementationBindingRow", "ActorImplementationBindingRow",
    "BoundaryProposalDecisionRow", "BoundaryProposalRow", "BusinessActionRevisionRow",
    "BusinessActionRow", "BusinessActorRevisionRow", "BusinessActorRow",
    "BusinessBoundaryRepository",
]
