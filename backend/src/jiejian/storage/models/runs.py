# 阶段 2.1 的 SQLAlchemy typed declarative 映射。

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

class RunRow(Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(
            "length(run_id) = 36 AND substr(run_id, 1, 4) = 'run_' "
            "AND substr(run_id, 5) NOT GLOB '*[^0-9a-f]*'",
            name="run_id_format",
        ),
        CheckConstraint(
            "lifecycle IN ('QUEUED', 'PREFLIGHT', 'PLANNING', 'EXECUTING', "
            "'VERIFYING', 'REPORTING', 'COMPLETED', 'FAILED', 'CANCELLED', "
            "'SAFETY_STOPPED')",
            name="lifecycle_value",
        ),
        CheckConstraint(
            "verdict IS NULL OR verdict IN ('PASS', 'BLOCK', 'INCONCLUSIVE')",
            name="verdict_value",
        ),
        CheckConstraint(
            "(lifecycle = 'COMPLETED' AND verdict IS NOT NULL) OR "
            "(lifecycle <> 'COMPLETED' AND verdict IS NULL)",
            name="lifecycle_verdict_matrix",
        ),
        CheckConstraint("contract_version >= 1", name="contract_version_positive"),
        CheckConstraint(
            "created_at_us >= 0 AND updated_at_us >= created_at_us "
            "AND (finished_at_us IS NULL OR finished_at_us >= created_at_us)",
            name="time_order",
        ),
        Index("ix_runs_project_created", "project_id", "created_at_us"),
        Index("ix_runs_lifecycle_updated", "lifecycle", "updated_at_us"),
    )

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(

        ForeignKey("projects.project_id", ondelete="RESTRICT"),
        nullable=False,
    )
    contract_id: Mapped[str] = mapped_column(String(128), nullable=False)
    contract_version: Mapped[int] = mapped_column(Integer, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(24), nullable=False)
    verdict: Mapped[str | None] = mapped_column(String(16))
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    finished_at_us: Mapped[int | None] = mapped_column(BigInteger)
