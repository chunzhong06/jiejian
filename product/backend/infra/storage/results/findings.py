# 历史表与只读记录形状保留用于无损升级；当前产品已退出这组仓储写入。
# Finding Finding 与 Occurrence 的 SQLAlchemy 映射；Evidence 正文仍只在发布工件。

from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from product.backend.infra.storage.base import Base


class FindingRow(Base):
    __tablename__ = "findings"
    __table_args__ = (
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

# 本聚合的 Repository 与持久化记录边界。

# =============================================================================
# Finding/Occurrence 仓储
#
# 定位
#   保存跨 Run 稳定问题和已发布 Evidence 引用，不保存 Evidence 正文
#
# 职责
#   幂等写入 Finding｜按 Run 读取 Occurrence｜提供状态转换所需历史
#
# 调用链
#   FindingMaterializer / FindingQueries → FindingRepository → SQLAlchemy rows
# =============================================================================

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from product.backend.core.errors import ErrorCode, JiejianError

from product.backend.infra.storage.base import StorageRecord, _flush, _scalar, _scalars, ensure_storage_payload_safe


class FindingRecord(StorageRecord):
    finding_id: str
    project_id: str
    identity_json: str
    created_at_us: int
    updated_at_us: int


class FindingOccurrenceRecord(StorageRecord):
    occurrence_id: str
    finding_id: str
    project_id: str
    run_id: str
    status: str
    verdict: str
    severity: str
    evidence_refs_json: str
    object_context_json: str
    coverage_context_json: str
    created_at_us: int




def _finding_record(row: FindingRow) -> FindingRecord:
    return FindingRecord(
        finding_id=row.finding_id,
        project_id=row.project_id,
        identity_json=row.identity_json,
        created_at_us=row.created_at_us,
        updated_at_us=row.updated_at_us,
    )


def _occurrence_record(row: FindingOccurrenceRow) -> FindingOccurrenceRecord:
    return FindingOccurrenceRecord(
        occurrence_id=row.occurrence_id,
        finding_id=row.finding_id,
        project_id=row.project_id,
        run_id=row.run_id,
        status=row.status,
        verdict=row.verdict,
        severity=row.severity,
        evidence_refs_json=row.evidence_refs_json,
        object_context_json=row.object_context_json,
        coverage_context_json=row.coverage_context_json,
        created_at_us=row.created_at_us,
    )
