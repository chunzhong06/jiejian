"""阶段 7.1 稳定 Finding 与 Run 级 Occurrence 索引。"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0009_stage7_findings"
down_revision: str | None = "0008_permission_execution_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "findings",
        sa.Column("finding_id", sa.String(length=40), nullable=False),
        sa.Column("schema_version", sa.String(length=8), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("identity_json", sa.Text(), nullable=False),
        sa.Column("created_at_us", sa.BigInteger(), nullable=False),
        sa.Column("updated_at_us", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("finding_id", name="pk_findings"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="RESTRICT"),
        sa.CheckConstraint("schema_version = '1'", name="finding_schema_version_value"),
        sa.CheckConstraint(
            "length(finding_id) = 40 AND substr(finding_id, 1, 8) = 'finding_' "
            "AND substr(finding_id, 9) NOT GLOB '*[^0-9a-f]*'",
            name="finding_id_format",
        ),
        sa.CheckConstraint("length(project_id) BETWEEN 1 AND 64", name="finding_project_id_length"),
        sa.CheckConstraint("length(identity_json) BETWEEN 1 AND 16384", name="finding_identity_length"),
        sa.CheckConstraint("created_at_us >= 0 AND updated_at_us >= created_at_us", name="finding_time_order"),
    )
    op.create_index("ix_findings_project_updated", "findings", ["project_id", "updated_at_us"])

    op.create_table(
        "finding_occurrences",
        sa.Column("occurrence_id", sa.String(length=36), nullable=False),
        sa.Column("schema_version", sa.String(length=8), nullable=False),
        sa.Column("finding_id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("evidence_refs_json", sa.Text(), nullable=False),
        sa.Column("object_context_json", sa.Text(), nullable=False),
        sa.Column("coverage_context_json", sa.Text(), nullable=False),
        sa.Column("created_at_us", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("occurrence_id", name="pk_finding_occurrences"),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.finding_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.run_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("finding_id", "run_id", name="uq_finding_occurrence_finding_run"),
        sa.CheckConstraint("schema_version = '1'", name="occurrence_schema_version_value"),
        sa.CheckConstraint(
            "length(occurrence_id) = 36 AND substr(occurrence_id, 1, 4) = 'occ_' "
            "AND substr(occurrence_id, 5) NOT GLOB '*[^0-9a-f]*'",
            name="occurrence_id_format",
        ),
        sa.CheckConstraint("length(evidence_refs_json) BETWEEN 1 AND 16384", name="occurrence_evidence_refs_length"),
        sa.CheckConstraint("length(object_context_json) BETWEEN 2 AND 16384", name="occurrence_object_context_length"),
        sa.CheckConstraint("length(coverage_context_json) BETWEEN 2 AND 16384", name="occurrence_coverage_context_length"),
        sa.CheckConstraint(
            "status IN ('APPEARED', 'PRESENT', 'DISAPPEARED', 'REAPPEARED', 'CHANGED')",
            name="occurrence_status_value",
        ),
        sa.CheckConstraint("verdict IN ('SAFE', 'VULNERABLE', 'INCONCLUSIVE')", name="occurrence_verdict_value"),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical', 'unknown')",
            name="occurrence_severity_value",
        ),
        sa.CheckConstraint("created_at_us >= 0", name="occurrence_created_nonnegative"),
    )
    op.create_index("ix_finding_occurrences_run_created", "finding_occurrences", ["run_id", "created_at_us"])
    op.create_index("ix_finding_occurrences_finding_created", "finding_occurrences", ["finding_id", "created_at_us"])


def downgrade() -> None:
    raise RuntimeError("界鉴数据库迁移只允许向前；请从备份恢复旧版本")
