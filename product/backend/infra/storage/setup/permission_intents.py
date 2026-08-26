# =============================================================================
# 测试准备：PermissionIntent 关系持久化
#
# 定位
#   用户确认权限意图与 SQLite 记录之间的 Repository。
#
# 职责
#   保存当前权限组/动作矩阵单元｜按项目和动作读取｜删除暂不确认的单元。
#
# 边界
#   只保存非秘密业务事实；生成 Contract/Profile 和 readiness 不进入本表。
#
# 调用链
#   PermissionIntentService → PermissionIntentRepository → SQLite
# =============================================================================

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from product.backend.core.permission_intent import (
    PermissionIntent,
    PermissionIntentRelation,
)
from product.backend.core.verification.permissions import PermissionExpectation
from product.backend.infra.storage.base import (
    Base,
    _flush,
    _scalar,
    _scalars,
    ensure_storage_payload_safe,
)


class PermissionIntentRow(Base):
    __tablename__ = "permission_intents"
    __table_args__ = (
        CheckConstraint(
            "length(intent_id) = 36 AND intent_id GLOB 'pin_[0-9a-f]*'",
            name="permission_intent_id_format",
        ),
        CheckConstraint(
            "relation IN ('OWNS', 'SAME_ROLE_OTHER_ACCOUNT', 'OTHER_ROLE')",
            name="permission_intent_relation_value",
        ),
        CheckConstraint(
            "expectation IN ('ALLOW', 'DENY') AND confirmation_source = 'USER'",
            name="permission_intent_confirmation_value",
        ),
        CheckConstraint(
            "created_at_us >= 0 AND confirmed_at_us >= 0 "
            "AND updated_at_us >= created_at_us "
            "AND confirmed_at_us <= updated_at_us",
            name="permission_intent_time_order",
        ),
        UniqueConstraint(
            "project_id",
            "action_candidate_id",
            "subject_role_candidate_id",
            "resource_owner_role_candidate_id",
            "relation",
            name="uq_permission_intent_group_matrix_cell",
        ),
        Index(
            "ix_permission_intents_project_action",
            "project_id",
            "action_candidate_id",
        ),
    )

    intent_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False
    )
    action_candidate_id: Mapped[str] = mapped_column(String(39), nullable=False)
    subject_role_candidate_id: Mapped[str] = mapped_column(String(37), nullable=False)
    resource_owner_role_candidate_id: Mapped[str] = mapped_column(String(37), nullable=False)
    relation: Mapped[str] = mapped_column(String(32), nullable=False)
    expectation: Mapped[str] = mapped_column(String(8), nullable=False)
    confirmation_source: Mapped[str] = mapped_column(String(8), nullable=False)
    confirmed_by: Mapped[str] = mapped_column(String(128), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmed_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class PermissionIntentRepository:
    """每个项目、动作、主体权限组、所有者权限组和关系只保存一个单元。"""

    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def get_cell(
        self,
        project_id: str,
        action_candidate_id: str,
        subject_role_candidate_id: str,
        resource_owner_role_candidate_id: str,
        relation: PermissionIntentRelation,
    ) -> PermissionIntent | None:
        row = _scalar(
            self._session,
            select(PermissionIntentRow).where(
                PermissionIntentRow.project_id == project_id,
                PermissionIntentRow.action_candidate_id == action_candidate_id,
                PermissionIntentRow.subject_role_candidate_id
                == subject_role_candidate_id,
                PermissionIntentRow.resource_owner_role_candidate_id
                == resource_owner_role_candidate_id,
                PermissionIntentRow.relation == relation.value,
            ),
        )
        return None if row is None else self._record(row)

    def list_for_project(self, project_id: str) -> tuple[PermissionIntent, ...]:
        rows = _scalars(
            self._session,
            select(PermissionIntentRow)
            .where(PermissionIntentRow.project_id == project_id)
            .order_by(
                PermissionIntentRow.action_candidate_id,
                PermissionIntentRow.subject_role_candidate_id,
                PermissionIntentRow.resource_owner_role_candidate_id,
                PermissionIntentRow.relation,
            ),
        )
        return tuple(self._record(row) for row in rows)

    def replace_cell(self, intent: PermissionIntent) -> None:
        values = intent.model_dump(mode="json")
        ensure_storage_payload_safe(values, self._known_secrets)
        existing = _scalar(
            self._session,
            select(PermissionIntentRow).where(
                PermissionIntentRow.project_id == intent.project_id,
                PermissionIntentRow.action_candidate_id == intent.action_candidate_id,
                PermissionIntentRow.subject_role_candidate_id
                == intent.subject_role_candidate_id,
                PermissionIntentRow.resource_owner_role_candidate_id
                == intent.resource_owner_role_candidate_id,
                PermissionIntentRow.relation == intent.relation.value,
            ),
        )
        if existing is not None:
            self._session.delete(existing)
            _flush(self._session)
        self._session.add(PermissionIntentRow(**values))
        _flush(self._session)

    def delete_cell(
        self,
        project_id: str,
        action_candidate_id: str,
        subject_role_candidate_id: str,
        resource_owner_role_candidate_id: str,
        relation: PermissionIntentRelation,
    ) -> None:
        row = _scalar(
            self._session,
            select(PermissionIntentRow).where(
                PermissionIntentRow.project_id == project_id,
                PermissionIntentRow.action_candidate_id == action_candidate_id,
                PermissionIntentRow.subject_role_candidate_id
                == subject_role_candidate_id,
                PermissionIntentRow.resource_owner_role_candidate_id
                == resource_owner_role_candidate_id,
                PermissionIntentRow.relation == relation.value,
            ),
        )
        if row is not None:
            self._session.delete(row)
            _flush(self._session)

    @staticmethod
    def _record(row: PermissionIntentRow) -> PermissionIntent:
        return PermissionIntent(
            intent_id=row.intent_id,
            project_id=row.project_id,
            action_candidate_id=row.action_candidate_id,
            subject_role_candidate_id=row.subject_role_candidate_id,
            resource_owner_role_candidate_id=row.resource_owner_role_candidate_id,
            relation=PermissionIntentRelation(row.relation),
            expectation=PermissionExpectation(row.expectation),
            confirmation_source="USER",
            confirmed_by=row.confirmed_by,
            fingerprint=row.fingerprint,
            confirmed_at_us=row.confirmed_at_us,
            created_at_us=row.created_at_us,
            updated_at_us=row.updated_at_us,
        )


__all__ = ["PermissionIntentRepository", "PermissionIntentRow"]
