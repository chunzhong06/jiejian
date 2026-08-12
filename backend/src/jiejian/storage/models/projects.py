# 阶段 2.1 的 SQLAlchemy typed declarative 映射。

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

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
    source_path: Mapped[str | None] = mapped_column(String(1024))
    source_hash: Mapped[str | None] = mapped_column(String(64))
    active_contract_path: Mapped[str | None] = mapped_column(String(1024))
    active_contract_hash: Mapped[str | None] = mapped_column(String(64))
    governed_contract_id: Mapped[str | None] = mapped_column(String(128))
    governed_contract_version: Mapped[int | None] = mapped_column(Integer)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
