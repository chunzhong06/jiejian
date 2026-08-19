# 阶段 7.1 Finding 与 Occurrence 的 SQLAlchemy 映射；Evidence 正文仍只在发布工件。

from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class FindingRow(Base):
    __tablename__ = "findings"
    __table_args__ = (
        CheckConstraint("schema_version = '1'", name="finding_schema_version_value"),
        CheckConstraint(
            "length(finding_id) = 40 AND substr(finding_id, 1, 8) = 'finding_' "
            "AND substr(finding_id, 9) NOT GLOB '*[^0-9a-f]*'",
            name="finding_id_format",
        ),
        CheckConstraint("length(project_id) BETWEEN 1 AND 64", name="finding_project_id_length"),
        CheckConstraint("length(identity_json) BETWEEN 1 AND 16384", name="finding_identity_length"),
        CheckConstraint("created_at_us >= 0 AND updated_at_us >= created_at_us", name="finding_time_order"),
        Index("ix_findings_project_updated", "project_id", "updated_at_us"),
    )

    finding_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(8), nullable=False)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False
    )
    identity_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class FindingOccurrenceRow(Base):
    __tablename__ = "finding_occurrences"
    __table_args__ = (
        UniqueConstraint("finding_id", "run_id", name="uq_finding_occurrence_finding_run"),
        CheckConstraint("schema_version = '1'", name="occurrence_schema_version_value"),
        CheckConstraint(
            "length(occurrence_id) = 36 AND substr(occurrence_id, 1, 4) = 'occ_' "
            "AND substr(occurrence_id, 5) NOT GLOB '*[^0-9a-f]*'",
            name="occurrence_id_format",
        ),
        CheckConstraint("length(evidence_refs_json) BETWEEN 1 AND 16384", name="occurrence_evidence_refs_length"),
        CheckConstraint("length(object_context_json) BETWEEN 2 AND 16384", name="occurrence_object_context_length"),
        CheckConstraint("length(coverage_context_json) BETWEEN 2 AND 16384", name="occurrence_coverage_context_length"),
        CheckConstraint(
            "status IN ('APPEARED', 'PRESENT', 'DISAPPEARED', 'REAPPEARED', 'CHANGED')",
            name="occurrence_status_value",
        ),
        CheckConstraint(
            "verdict IN ('SAFE', 'VULNERABLE', 'INCONCLUSIVE')",
            name="occurrence_verdict_value",
        ),
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical', 'unknown')",
            name="occurrence_severity_value",
        ),
        CheckConstraint("created_at_us >= 0", name="occurrence_created_nonnegative"),
        Index("ix_finding_occurrences_run_created", "run_id", "created_at_us"),
        Index("ix_finding_occurrences_finding_created", "finding_id", "created_at_us"),
    )

    occurrence_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(8), nullable=False)
    finding_id: Mapped[str] = mapped_column(
        ForeignKey("findings.finding_id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.run_id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence_refs_json: Mapped[str] = mapped_column(Text, nullable=False)
    object_context_json: Mapped[str] = mapped_column(Text, nullable=False)
    coverage_context_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
