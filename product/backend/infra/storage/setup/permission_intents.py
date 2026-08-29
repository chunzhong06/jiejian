# =============================================================================
# 长期权限意图账本持久化
#
# 定位
#   不可变权限 revision、项目 epoch、实现 binding 与 Agent proposal 的 SQLite 聚合。
#
# 职责
#   追加 revision｜原子保存 epoch｜维护当前 binding｜保存不生效的 proposal。
#
# 边界
#   Repository 不批准权限语义、不计算 Verdict，也不保存秘密或执行请求正文。
#
# 调用链
#   PermissionIntentService → PermissionIntentRepository → SQLAlchemy / SQLite
# =============================================================================

from __future__ import annotations

import json
from collections.abc import Sequence

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from product.backend.core.permission_intent import (
    HumanApproval,
    IntentImplementationBinding,
    IntentImplementationBindingStatus,
    IntentProposal,
    IntentProposalKind,
    IntentProposalStatus,
    PermissionIntentEffectiveState,
    PermissionIntentRelation,
    PermissionIntentRevision,
    PermissionIntentSemantic,
    ProjectPolicyState,
    ProposedImplementationBinding,
    ProtectedEffect,
)
from product.backend.core.verification.permissions import PermissionExpectation
from product.backend.infra.storage.base import (
    Base,
    _canonical_json,
    _flush,
    _scalar,
    _scalars,
    ensure_storage_payload_safe,
)


class PermissionIntentRevisionRow(Base):
    __tablename__ = "permission_intent_revisions"
    __table_args__ = (
        CheckConstraint(
            "length(intent_id) = 36 AND intent_id GLOB 'pin_[0-9a-f]*'",
            name="intent_id_format",
        ),
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(
            "effective_state IN ('ACTIVE', 'RETIRED')",
            name="effective_state_value",
        ),
        CheckConstraint(
            "relation IN ('OWNS', 'SAME_ROLE_OTHER_ACCOUNT', 'OTHER_ROLE')",
            name="relation_value",
        ),
        CheckConstraint("expectation IN ('ALLOW', 'DENY')", name="expectation_value"),
        CheckConstraint("policy_epoch >= 1", name="policy_epoch_positive"),
        CheckConstraint("created_at_us >= 0", name="created_nonnegative"),
        Index("ix_permission_intent_revisions_project", "project_id", "created_at_us"),
    )

    intent_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False
    )
    effective_state: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    action_display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    resource_owner_display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    relation: Mapped[str] = mapped_column(String(32), nullable=False)
    expectation: Mapped[str] = mapped_column(String(8), nullable=False)
    protected_effects_json: Mapped[str] = mapped_column(Text, nullable=False)
    intent_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    approval_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class ProjectPolicyStateRow(Base):
    __tablename__ = "project_policy_states"
    __table_args__ = (
        CheckConstraint("policy_epoch >= 0", name="policy_epoch_nonnegative"),
        CheckConstraint("updated_at_us >= 0", name="updated_nonnegative"),
    )

    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.project_id", ondelete="CASCADE"), primary_key=True
    )
    policy_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class IntentImplementationBindingRow(Base):
    __tablename__ = "intent_implementation_bindings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["intent_id", "intent_revision"],
            ["permission_intent_revisions.intent_id", "permission_intent_revisions.revision"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('CURRENT', 'NEEDS_REVIEW', 'UNRESOLVED')",
            name="status_value",
        ),
        CheckConstraint("understanding_revision >= 0", name="understanding_revision_nonnegative"),
        CheckConstraint("updated_at_us >= 0", name="updated_nonnegative"),
        Index("ix_intent_bindings_action", "action_candidate_id"),
    )

    intent_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    intent_revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    action_candidate_id: Mapped[str] = mapped_column(String(39), nullable=False)
    subject_role_candidate_id: Mapped[str] = mapped_column(String(37), nullable=False)
    resource_owner_role_candidate_id: Mapped[str] = mapped_column(String(37), nullable=False)
    understanding_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    action_safety_setup_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    binding_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_codes_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class IntentProposalRow(Base):
    __tablename__ = "intent_proposals"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('SEMANTIC_CHANGE', 'IMPLEMENTATION_REBIND')",
            name="kind_value",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="status_value",
        ),
        CheckConstraint(
            "created_at_us >= 0 AND (decided_at_us IS NULL OR decided_at_us >= created_at_us)",
            name="time_order",
        ),
        Index("ix_intent_proposals_project_status", "project_id", "status", "created_at_us"),
    )

    proposal_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    intent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    semantic_change_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    implementation_rebind_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_by: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    decided_at_us: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class PermissionIntentRepository:
    """把一个项目的长期权限账本作为同一事务聚合读写。"""

    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def policy_state(self, project_id: str) -> ProjectPolicyState | None:
        row = _scalar(
            self._session,
            select(ProjectPolicyStateRow).where(ProjectPolicyStateRow.project_id == project_id),
        )
        return None if row is None else ProjectPolicyState(
            project_id=row.project_id,
            policy_epoch=row.policy_epoch,
            updated_at_us=row.updated_at_us,
        )

    def replace_policy_state(self, state: ProjectPolicyState) -> None:
        ensure_storage_payload_safe(state.model_dump(mode="json"), self._known_secrets)
        row = _scalar(
            self._session,
            select(ProjectPolicyStateRow).where(ProjectPolicyStateRow.project_id == state.project_id),
        )
        if row is None:
            self._session.add(ProjectPolicyStateRow(**state.model_dump(mode="json")))
        else:
            row.policy_epoch = state.policy_epoch
            row.updated_at_us = state.updated_at_us
        _flush(self._session)

    def add_revision(self, revision: PermissionIntentRevision) -> None:
        values = revision.model_dump(mode="json", exclude={"protected_effects", "approval"})
        values["protected_effects_json"] = _canonical_json(
            [item.model_dump(mode="json") for item in revision.protected_effects]
        )
        values["approval_json"] = _canonical_json(revision.approval.model_dump(mode="json"))
        ensure_storage_payload_safe(values, self._known_secrets)
        self._session.add(PermissionIntentRevisionRow(**values))
        _flush(self._session)

    def get_revision(self, intent_id: str, revision: int) -> PermissionIntentRevision | None:
        row = _scalar(
            self._session,
            select(PermissionIntentRevisionRow).where(
                PermissionIntentRevisionRow.intent_id == intent_id,
                PermissionIntentRevisionRow.revision == revision,
            ),
        )
        return None if row is None else self._revision(row)

    def latest(self, intent_id: str) -> PermissionIntentRevision | None:
        row = _scalar(
            self._session,
            select(PermissionIntentRevisionRow)
            .where(PermissionIntentRevisionRow.intent_id == intent_id)
            .order_by(PermissionIntentRevisionRow.revision.desc())
            .limit(1),
        )
        return None if row is None else self._revision(row)

    def list_revisions(self, project_id: str) -> tuple[PermissionIntentRevision, ...]:
        rows = _scalars(
            self._session,
            select(PermissionIntentRevisionRow)
            .where(PermissionIntentRevisionRow.project_id == project_id)
            .order_by(PermissionIntentRevisionRow.intent_id, PermissionIntentRevisionRow.revision),
        )
        return tuple(self._revision(row) for row in rows)

    def list_latest(self, project_id: str) -> tuple[PermissionIntentRevision, ...]:
        latest: dict[str, PermissionIntentRevision] = {}
        for revision in self.list_revisions(project_id):
            latest[revision.intent_id] = revision
        return tuple(sorted(latest.values(), key=lambda item: item.intent_id))

    def add_binding(self, binding: IntentImplementationBinding) -> None:
        values = binding.model_dump(mode="json", exclude={"reason_codes"})
        values["reason_codes_json"] = _canonical_json(list(binding.reason_codes))
        ensure_storage_payload_safe(values, self._known_secrets)
        self._session.add(IntentImplementationBindingRow(**values))
        _flush(self._session)

    def replace_binding(self, binding: IntentImplementationBinding) -> None:
        values = binding.model_dump(mode="json", exclude={"reason_codes"})
        values["reason_codes_json"] = _canonical_json(list(binding.reason_codes))
        ensure_storage_payload_safe(values, self._known_secrets)
        row = _scalar(
            self._session,
            select(IntentImplementationBindingRow).where(
                IntentImplementationBindingRow.intent_id == binding.intent_id,
                IntentImplementationBindingRow.intent_revision == binding.intent_revision,
            ),
        )
        if row is None:
            self._session.add(IntentImplementationBindingRow(**values))
        else:
            for key, value in values.items():
                setattr(row, key, value)
        _flush(self._session)

    def binding(self, intent_id: str, revision: int) -> IntentImplementationBinding | None:
        row = _scalar(
            self._session,
            select(IntentImplementationBindingRow).where(
                IntentImplementationBindingRow.intent_id == intent_id,
                IntentImplementationBindingRow.intent_revision == revision,
            ),
        )
        return None if row is None else self._binding(row)

    def list_bindings(self, project_id: str) -> tuple[IntentImplementationBinding, ...]:
        rows = _scalars(
            self._session,
            select(IntentImplementationBindingRow)
            .join(
                PermissionIntentRevisionRow,
                (PermissionIntentRevisionRow.intent_id == IntentImplementationBindingRow.intent_id)
                & (
                    PermissionIntentRevisionRow.revision
                    == IntentImplementationBindingRow.intent_revision
                ),
            )
            .where(PermissionIntentRevisionRow.project_id == project_id)
            .order_by(
                IntentImplementationBindingRow.intent_id,
                IntentImplementationBindingRow.intent_revision,
            ),
        )
        return tuple(self._binding(row) for row in rows)

    def add_proposal(self, proposal: IntentProposal) -> None:
        values = proposal.model_dump(
            mode="json",
            exclude={"semantic_change", "implementation_rebind"},
        )
        values["semantic_change_json"] = (
            None
            if proposal.semantic_change is None
            else _canonical_json(proposal.semantic_change.model_dump(mode="json"))
        )
        values["implementation_rebind_json"] = (
            None
            if proposal.implementation_rebind is None
            else _canonical_json(proposal.implementation_rebind.model_dump(mode="json"))
        )
        ensure_storage_payload_safe(values, self._known_secrets)
        self._session.add(IntentProposalRow(**values))
        _flush(self._session)

    def replace_proposal(self, proposal: IntentProposal) -> None:
        row = _scalar(
            self._session,
            select(IntentProposalRow).where(IntentProposalRow.proposal_id == proposal.proposal_id),
        )
        if row is None:
            raise ValueError("intent proposal does not exist")
        values = proposal.model_dump(
            mode="json",
            exclude={"semantic_change", "implementation_rebind", "proposal_id"},
        )
        values["semantic_change_json"] = (
            None
            if proposal.semantic_change is None
            else _canonical_json(proposal.semantic_change.model_dump(mode="json"))
        )
        values["implementation_rebind_json"] = (
            None
            if proposal.implementation_rebind is None
            else _canonical_json(proposal.implementation_rebind.model_dump(mode="json"))
        )
        ensure_storage_payload_safe(values, self._known_secrets)
        for key, value in values.items():
            setattr(row, key, value)
        _flush(self._session)

    def proposal(self, proposal_id: str) -> IntentProposal | None:
        row = _scalar(
            self._session,
            select(IntentProposalRow).where(IntentProposalRow.proposal_id == proposal_id),
        )
        return None if row is None else self._proposal(row)

    def list_proposals(self, project_id: str) -> tuple[IntentProposal, ...]:
        rows = _scalars(
            self._session,
            select(IntentProposalRow)
            .where(IntentProposalRow.project_id == project_id)
            .order_by(IntentProposalRow.created_at_us, IntentProposalRow.proposal_id),
        )
        return tuple(self._proposal(row) for row in rows)

    @staticmethod
    def _revision(row: PermissionIntentRevisionRow) -> PermissionIntentRevision:
        return PermissionIntentRevision(
            intent_id=row.intent_id,
            project_id=row.project_id,
            revision=row.revision,
            effective_state=PermissionIntentEffectiveState(row.effective_state),
            subject_display_name=row.subject_display_name,
            action_display_name=row.action_display_name,
            resource_owner_display_name=row.resource_owner_display_name,
            relation=PermissionIntentRelation(row.relation),
            expectation=PermissionExpectation(row.expectation),
            protected_effects=tuple(
                ProtectedEffect.model_validate_json(_canonical_json(item))
                for item in json.loads(row.protected_effects_json)
            ),
            intent_hash=row.intent_hash,
            policy_epoch=row.policy_epoch,
            approval=HumanApproval.model_validate_json(row.approval_json),
            created_at_us=row.created_at_us,
        )

    @staticmethod
    def _binding(row: IntentImplementationBindingRow) -> IntentImplementationBinding:
        return IntentImplementationBinding(
            intent_id=row.intent_id,
            intent_revision=row.intent_revision,
            action_candidate_id=row.action_candidate_id,
            subject_role_candidate_id=row.subject_role_candidate_id,
            resource_owner_role_candidate_id=row.resource_owner_role_candidate_id,
            understanding_revision=row.understanding_revision,
            action_safety_setup_fingerprint=row.action_safety_setup_fingerprint,
            binding_fingerprint=row.binding_fingerprint,
            status=IntentImplementationBindingStatus(row.status),
            reason_codes=tuple(json.loads(row.reason_codes_json)),
            updated_at_us=row.updated_at_us,
        )

    @staticmethod
    def _proposal(row: IntentProposalRow) -> IntentProposal:
        return IntentProposal(
            proposal_id=row.proposal_id,
            project_id=row.project_id,
            kind=IntentProposalKind(row.kind),
            status=IntentProposalStatus(row.status),
            intent_id=row.intent_id,
            semantic_change=(
                None
                if row.semantic_change_json is None
                else PermissionIntentSemantic.model_validate_json(row.semantic_change_json)
            ),
            implementation_rebind=(
                None
                if row.implementation_rebind_json is None
                else ProposedImplementationBinding.model_validate_json(
                    row.implementation_rebind_json
                )
            ),
            proposed_by=row.proposed_by,
            reason=row.reason,
            created_at_us=row.created_at_us,
            decided_at_us=row.decided_at_us,
        )


__all__ = [
    "IntentImplementationBindingRow",
    "IntentProposalRow",
    "PermissionIntentRepository",
    "PermissionIntentRevisionRow",
    "ProjectPolicyStateRow",
]
