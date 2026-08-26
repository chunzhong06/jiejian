# =============================================================================
# 应用理解仓储
#
# 定位
#   ApplicationUnderstanding 核心事实与 SQLite 一对一项目记录之间的持久化适配器
#
# 职责
#   映射连接与授权字段｜规范化候选 JSON｜维护项目级唯一 source root
#
# 边界
#   不提交事务、不读取源码正文、不推断候选或权限；损坏 JSON 以稳定存储错误失败关闭。
#
# 调用链
#   Application Understanding service → Unit of Work / Repository → SQLite row
# =============================================================================

from __future__ import annotations

import json
from collections.abc import Sequence

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from product.backend.core.application_understanding import (
    ActionCandidate,
    ApplicationUnderstanding,
    RoleCandidate,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage.base import (
    Base,
    _canonical_json,
    _flush,
    _scalar,
    ensure_storage_payload_safe,
)


class ApplicationUnderstandingRow(Base):
    __tablename__ = "application_understanding"
    __table_args__ = (
        CheckConstraint("length(source_root) BETWEEN 1 AND 32768", name="source_root_length"),
        CheckConstraint(
            "confirmed_endpoint IS NULL OR length(confirmed_endpoint) BETWEEN 1 AND 2048",
            name="endpoint_length",
        ),
        CheckConstraint(
            "(confirmed_endpoint IS NULL AND endpoint_source_fingerprint IS NULL "
            "AND endpoint_confirmed_at_us IS NULL AND endpoint_last_checked_at_us IS NULL "
            "AND endpoint_reachable IS NULL) OR "
            "(confirmed_endpoint IS NOT NULL AND endpoint_source_fingerprint IS NOT NULL "
            "AND endpoint_confirmed_at_us IS NOT NULL AND endpoint_last_checked_at_us IS NOT NULL "
            "AND endpoint_reachable IS NOT NULL)",
            name="endpoint_state_complete",
        ),
        CheckConstraint(
            "endpoint_source_fingerprint IS NULL OR length(endpoint_source_fingerprint) = 64",
            name="endpoint_fingerprint_length",
        ),
        CheckConstraint(
            "(source_analysis_authorized = 0 AND source_analysis_authorized_at_us IS NULL) OR "
            "(source_analysis_authorized = 1 AND source_analysis_authorized_at_us IS NOT NULL)",
            name="analysis_authorization_state",
        ),
        CheckConstraint(
            "(source_fingerprint IS NULL AND analysis_completed_at_us IS NULL) OR "
            "(source_fingerprint IS NOT NULL AND length(source_fingerprint) = 64 "
            "AND analysis_completed_at_us IS NOT NULL AND source_analysis_authorized = 1)",
            name="analysis_result_state",
        ),
        CheckConstraint("length(role_candidates_json) BETWEEN 2 AND 1048576", name="roles_json_length"),
        CheckConstraint("length(action_candidates_json) BETWEEN 2 AND 2097152", name="actions_json_length"),
        CheckConstraint("revision BETWEEN 0 AND 1000000", name="revision_range"),
        CheckConstraint(
            "created_at_us >= 0 AND updated_at_us >= created_at_us",
            name="time_order",
        ),
        UniqueConstraint(
            "source_root",
            name="uq_application_understanding_source_root",
        ),
        Index("ix_application_understanding_updated", "updated_at_us"),
    )

    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.project_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    source_root: Mapped[str] = mapped_column(String(32_768), nullable=False)
    confirmed_endpoint: Mapped[str | None] = mapped_column(String(2048))
    endpoint_source_fingerprint: Mapped[str | None] = mapped_column(String(64))
    endpoint_confirmed_at_us: Mapped[int | None] = mapped_column(BigInteger)
    endpoint_last_checked_at_us: Mapped[int | None] = mapped_column(BigInteger)
    endpoint_reachable: Mapped[bool | None] = mapped_column(Boolean)
    source_analysis_authorized: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source_analysis_authorized_at_us: Mapped[int | None] = mapped_column(BigInteger)
    source_fingerprint: Mapped[str | None] = mapped_column(String(64))
    analysis_completed_at_us: Mapped[int | None] = mapped_column(BigInteger)
    role_candidates_json: Mapped[str] = mapped_column(Text, nullable=False)
    action_candidates_json: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class ApplicationUnderstandingRepository:
    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def add(self, record: ApplicationUnderstanding) -> None:
        values = self._row_values(record)
        ensure_storage_payload_safe(values, self._known_secrets)
        self._session.add(ApplicationUnderstandingRow(**values))
        _flush(self._session)

    def get(self, project_id: str) -> ApplicationUnderstanding | None:
        row = _scalar(
            self._session,
            select(ApplicationUnderstandingRow).where(
                ApplicationUnderstandingRow.project_id == project_id
            ),
        )
        return None if row is None else self._record(row)

    def get_by_source_root(self, source_root: str) -> ApplicationUnderstanding | None:
        row = _scalar(
            self._session,
            select(ApplicationUnderstandingRow).where(
                ApplicationUnderstandingRow.source_root == source_root
            ),
        )
        return None if row is None else self._record(row)

    def replace(self, record: ApplicationUnderstanding) -> None:
        values = self._row_values(record)
        ensure_storage_payload_safe(values, self._known_secrets)
        row = _scalar(
            self._session,
            select(ApplicationUnderstandingRow).where(
                ApplicationUnderstandingRow.project_id == record.project_id
            ),
        )
        if row is None:
            raise JiejianError(
                ErrorCode.APPLICATION_UNDERSTANDING_NOT_FOUND,
                "应用理解记录不存在",
            )
        for key, value in values.items():
            setattr(row, key, value)
        _flush(self._session)

    @staticmethod
    def _row_values(record: ApplicationUnderstanding) -> dict[str, object]:
        values = record.model_dump(
            mode="json",
            exclude={"role_candidates", "action_candidates"},
        )
        values["role_candidates_json"] = _canonical_json(
            [item.model_dump(mode="json") for item in record.role_candidates]
        )
        values["action_candidates_json"] = _canonical_json(
            [item.model_dump(mode="json") for item in record.action_candidates]
        )
        return values

    @staticmethod
    def _record(row: ApplicationUnderstandingRow) -> ApplicationUnderstanding:
        try:
            roles = json.loads(row.role_candidates_json)
            actions = json.loads(row.action_candidates_json)
        except json.JSONDecodeError:
            raise JiejianError(
                ErrorCode.STORAGE_FAILURE,
                "应用理解候选数据损坏",
            ) from None
        try:
            role_candidates = tuple(
                RoleCandidate.model_validate(item, strict=False) for item in roles
            )
            action_candidates = tuple(
                ActionCandidate.model_validate(item, strict=False) for item in actions
            )
        except (TypeError, ValueError):
            raise JiejianError(
                ErrorCode.STORAGE_FAILURE,
                "应用理解候选数据损坏",
            ) from None
        return ApplicationUnderstanding.model_validate(
            {
                "project_id": row.project_id,
                "source_root": row.source_root,
                "confirmed_endpoint": row.confirmed_endpoint,
                "endpoint_source_fingerprint": row.endpoint_source_fingerprint,
                "endpoint_confirmed_at_us": row.endpoint_confirmed_at_us,
                "endpoint_last_checked_at_us": row.endpoint_last_checked_at_us,
                "endpoint_reachable": row.endpoint_reachable,
                "source_analysis_authorized": row.source_analysis_authorized,
                "source_analysis_authorized_at_us": row.source_analysis_authorized_at_us,
                "source_fingerprint": row.source_fingerprint,
                "analysis_completed_at_us": row.analysis_completed_at_us,
                "role_candidates": role_candidates,
                "action_candidates": action_candidates,
                "revision": row.revision,
                "created_at_us": row.created_at_us,
                "updated_at_us": row.updated_at_us,
            }
        )
