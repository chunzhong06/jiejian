# Storage 的 SQLAlchemy typed declarative 映射。

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Index,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from product.backend.infrastructure.storage.base import Base

class ProjectRow(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            "length(project_id) BETWEEN 1 AND 64 "
            "AND substr(project_id, 1, 1) GLOB '[a-z]' "
            "AND project_id NOT GLOB '*[^a-z0-9_-]*'",
            name="project_id_format",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'READY', 'ARCHIVED')",
            name="status_value",
        ),
        CheckConstraint("length(name) BETWEEN 1 AND 128", name="name_length"),
        CheckConstraint(
            "created_at_us >= 0 AND updated_at_us >= created_at_us",
            name="time_order",
        ),
        Index("ix_projects_status_updated", "status", "updated_at_us"),
    )

    project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False, default="WEB")
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)

# 本聚合的 Repository 与持久化记录边界。

# =============================================================================
# Project 聚合仓储
#
# 定位
#   Project 自身配置、状态与安全范围的持久化适配器
#
# 职责
#   映射 Project 记录｜保存配置和状态｜提供项目级查询
#
# 调用链
#   ProjectCatalog → ProjectRepository → Project ORM rows
# =============================================================================

import json
import time
from collections.abc import Sequence

from pydantic import Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from product.backend.domain.identifiers import PROJECT_ID_PATTERN
from product.backend.domain.lifecycle import ProjectStatus
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.domain.verification.facts import TargetType
from product.backend.infrastructure.storage.base import StorageRecord, _flush, _scalar, _scalars, ensure_storage_payload_safe

class ProjectRecord(StorageRecord):

    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    name: str = Field(min_length=1, max_length=128)
    status: ProjectStatus
    target_type: TargetType = TargetType.WEB
    created_at_us: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_time_order(self) -> ProjectRecord:
        if self.target_type is not TargetType.WEB:
            raise ValueError("only WEB project targets are supported")
        if self.updated_at_us < self.created_at_us:
            raise ValueError("project update time precedes creation")
        return self
class ProjectRepository:
    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def add(self, record: ProjectRecord) -> None:
        ensure_storage_payload_safe(
            record.model_dump(mode="json"), self._known_secrets
        )
        self._session.add(
            ProjectRow(
                project_id=record.project_id,
                name=record.name,
                status=record.status.value,
                target_type=record.target_type.value,
                created_at_us=record.created_at_us,
                updated_at_us=record.updated_at_us,
            )
        )
        _flush(self._session)

    def get(self, project_id: str) -> ProjectRecord | None:
        row = _scalar(
            self._session,
            select(ProjectRow).where(ProjectRow.project_id == project_id),
        )
        if row is None:
            return None
        return ProjectRecord(
            project_id=row.project_id,
            name=row.name,
            status=ProjectStatus(row.status),
            target_type=TargetType(row.target_type or TargetType.WEB.value),
            created_at_us=row.created_at_us,
            updated_at_us=row.updated_at_us,
        )
    def list_all(self) -> tuple[ProjectRecord, ...]:
        rows = _scalars(
            self._session,
            select(ProjectRow).order_by(ProjectRow.updated_at_us.desc(), ProjectRow.project_id),
        )
        return tuple(self._record(row) for row in rows)

    def replace(self, record: ProjectRecord) -> None:
        ensure_storage_payload_safe(
            record.model_dump(mode="json"), self._known_secrets

        )
        row = _scalar(
            self._session,
            select(ProjectRow).where(ProjectRow.project_id == record.project_id),
        )
        if row is None:
            raise JiejianError(ErrorCode.STORAGE_CONSTRAINT, "项目对象不存在")
        row.name = record.name
        row.status = record.status.value
        row.target_type = record.target_type.value
        row.updated_at_us = record.updated_at_us
        _flush(self._session)

    @staticmethod
    def _record(row: ProjectRow) -> ProjectRecord:
        return ProjectRecord(
            project_id=row.project_id,
            name=row.name,
            status=ProjectStatus(row.status),
            target_type=TargetType(row.target_type or TargetType.WEB.value),
            created_at_us=row.created_at_us,
            updated_at_us=row.updated_at_us,
        )
