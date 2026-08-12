# 阶段 2.1 的 SQLAlchemy typed declarative 映射。

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

class EvidenceIndexRow(Base):
    __tablename__ = "evidence_index"
    __table_args__ = (
        UniqueConstraint("run_id", "case_id", name="uq_evidence_run_case"),
        UniqueConstraint(
            "run_id",
            "artifact_path",
            name="uq_evidence_run_artifact_path",
        ),
        CheckConstraint(
            "length(evidence_id) BETWEEN 23 AND 67 "
            "AND substr(evidence_id, 1, 3) = 'ev_' "

            "AND substr(evidence_id, 4) NOT GLOB '*[^0-9a-f]*'",
            name="evidence_id_format",
        ),
        CheckConstraint(
            "length(case_id) BETWEEN 1 AND 128",
            name="case_id_length",
        ),
        CheckConstraint(
            "length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'",
            name="sha256_format",
        ),
        CheckConstraint(
            "substr(sha256, 1, length(evidence_id) - 3) = substr(evidence_id, 4)",
            name="content_address_match",
        ),
        CheckConstraint(
            "length(artifact_path) BETWEEN 1 AND 512 "
            "AND substr(artifact_path, 1, 1) <> '/' "
            "AND instr(artifact_path, '\\') = 0 "
            "AND instr(artifact_path, ':') = 0 "
            "AND instr(artifact_path, char(0)) = 0 "
            "AND artifact_path NOT LIKE '%//%'",
            name="artifact_path_basic",
        ),
        CheckConstraint(
            "byte_count BETWEEN 0 AND 1073741824",
            name="byte_count_bounds",
        ),
        CheckConstraint("created_at_us >= 0", name="created_nonnegative"),
        Index("ix_evidence_run_created", "run_id", "created_at_us"),
    )

    evidence_id: Mapped[str] = mapped_column(String(67), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.run_id", ondelete="RESTRICT"),
        nullable=False,
    )
    case_id: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_path: Mapped[str] = mapped_column(
        String(512, collation="NOCASE"),
        nullable=False,
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
