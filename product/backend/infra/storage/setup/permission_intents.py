# PermissionIntent v2 与 ProjectPolicyState 持久化；只追加稳定业务 revision，不保存 Candidate 或旧绑定。

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
    PermissionIntentRevision,
    ProjectPolicyState,
)
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
        ForeignKeyConstraint(
            ["subject_actor_id", "subject_actor_revision"],
            ["business_actor_revisions.actor_id", "business_actor_revisions.revision"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["business_action_id", "action_revision"],
            ["business_action_revisions.action_id", "business_action_revisions.revision"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["resource_owner_actor_id", "resource_owner_actor_revision"],
            ["business_actor_revisions.actor_id", "business_actor_revisions.revision"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint("effective_state IN ('ACTIVE', 'RETIRED')", name="effective_state_value"),
        CheckConstraint("relation IN ('OWNS', 'SAME_ROLE_OTHER_ACCOUNT', 'OTHER_ROLE')", name="relation_value"),
        CheckConstraint("expectation IN ('ALLOW', 'DENY')", name="expectation_value"),
        CheckConstraint("policy_epoch >= 1", name="policy_epoch_positive"),
        Index("ix_permission_intent_revisions_project", "project_id", "created_at_us"),
        Index("ix_permission_intent_revisions_action", "business_action_id", "action_revision"),
    )

    intent_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False
    )
    effective_state: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_actor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    subject_actor_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    business_action_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    resource_owner_actor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    resource_owner_actor_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    relation: Mapped[str] = mapped_column(String(32), nullable=False)
    expectation: Mapped[str] = mapped_column(String(8), nullable=False)
    protected_effect_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
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


class PermissionIntentRepository:
    """追加 Permission revision，并在同一事务内维护唯一 policy epoch。"""

    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def policy_state(self, project_id: str) -> ProjectPolicyState | None:
        row = _scalar(self._session, select(ProjectPolicyStateRow).where(ProjectPolicyStateRow.project_id == project_id))
        return None if row is None else ProjectPolicyState(
            project_id=row.project_id,
            policy_epoch=row.policy_epoch,
            updated_at_us=row.updated_at_us,
        )

    def replace_policy_state(self, state: ProjectPolicyState) -> None:
        values = state.model_dump(mode="json")
        ensure_storage_payload_safe(values, self._known_secrets)
        row = _scalar(self._session, select(ProjectPolicyStateRow).where(ProjectPolicyStateRow.project_id == state.project_id))
        if row is None:
            self._session.add(ProjectPolicyStateRow(**values))
        else:
            row.policy_epoch = state.policy_epoch
            row.updated_at_us = state.updated_at_us
        _flush(self._session)

    def add_revision(self, revision: PermissionIntentRevision) -> None:
        values = revision.model_dump(mode="json", exclude={"protected_effect_ids", "approval"})
        values["protected_effect_ids_json"] = _canonical_json(list(revision.protected_effect_ids))
        values["approval_json"] = _canonical_json(revision.approval.model_dump(mode="json"))
        ensure_storage_payload_safe(values, self._known_secrets)
        self._session.add(PermissionIntentRevisionRow(**values))
        _flush(self._session)

    def get_revision(self, intent_id: str, revision: int) -> PermissionIntentRevision | None:
        row = _scalar(self._session, select(PermissionIntentRevisionRow).where(PermissionIntentRevisionRow.intent_id == intent_id, PermissionIntentRevisionRow.revision == revision))
        return None if row is None else self._revision(row)

    def latest(self, intent_id: str) -> PermissionIntentRevision | None:
        row = _scalar(self._session, select(PermissionIntentRevisionRow).where(PermissionIntentRevisionRow.intent_id == intent_id).order_by(PermissionIntentRevisionRow.revision.desc()).limit(1))
        return None if row is None else self._revision(row)

    def list_history(self, project_id: str) -> tuple[PermissionIntentRevision, ...]:
        rows = _scalars(self._session, select(PermissionIntentRevisionRow).where(PermissionIntentRevisionRow.project_id == project_id).order_by(PermissionIntentRevisionRow.intent_id, PermissionIntentRevisionRow.revision))
        return tuple(self._revision(row) for row in rows)

    def list_revisions(self, project_id: str) -> tuple[PermissionIntentRevision, ...]:
        return self.list_history(project_id)

    def list_latest(self, project_id: str) -> tuple[PermissionIntentRevision, ...]:
        latest: dict[str, PermissionIntentRevision] = {}
        for revision in self.list_history(project_id):
            latest[revision.intent_id] = revision
        return tuple(sorted(latest.values(), key=lambda item: item.intent_id))

    @staticmethod
    def _revision(row: PermissionIntentRevisionRow) -> PermissionIntentRevision:
        return PermissionIntentRevision.model_validate_json(
            _canonical_json(
                {
                "intent_id": row.intent_id,
                "project_id": row.project_id,
                "revision": row.revision,
                "effective_state": row.effective_state,
                "subject_actor_id": row.subject_actor_id,
                "subject_actor_revision": row.subject_actor_revision,
                "business_action_id": row.business_action_id,
                "action_revision": row.action_revision,
                "resource_owner_actor_id": row.resource_owner_actor_id,
                "resource_owner_actor_revision": row.resource_owner_actor_revision,
                "relation": row.relation,
                "expectation": row.expectation,
                "protected_effect_ids": json.loads(row.protected_effect_ids_json),
                "intent_hash": row.intent_hash,
                "policy_epoch": row.policy_epoch,
                "approval": json.loads(row.approval_json),
                "created_at_us": row.created_at_us,
                }
            )
        )


__all__ = ["PermissionIntentRepository", "PermissionIntentRevisionRow", "ProjectPolicyStateRow"]
