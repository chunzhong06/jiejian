"""阶段 7.2 回归基线与确定性门禁结果。"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0010_stage7_gate"
down_revision: str | None = "0009_stage7_findings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "regression_baselines",
        sa.Column("baseline_id", sa.String(length=41), nullable=False),
        sa.Column("schema_version", sa.String(length=8), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("accepted_run_id", sa.String(length=36), nullable=False),
        sa.Column("finding_refs_json", sa.Text(), nullable=False),
        sa.Column("coverage_ids_json", sa.Text(), nullable=False),
        sa.Column("coverage_digest", sa.String(length=64), nullable=False),
        sa.Column("request_snapshot_sha256", sa.String(length=64), nullable=False),
        sa.Column("engine_version", sa.String(length=64), nullable=False),
        sa.Column("protocol_versions_json", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=1024), nullable=False),
        sa.Column("accepted_at_us", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("baseline_id", name="pk_regression_baselines"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["accepted_run_id"], ["runs.run_id"], ondelete="RESTRICT"),
        sa.CheckConstraint("schema_version = '1'", name="baseline_schema_version_value"),
        sa.CheckConstraint("length(baseline_id) = 41 AND substr(baseline_id, 1, 9) = 'baseline_' AND substr(baseline_id, 10) NOT GLOB '*[^0-9a-f]*'", name="baseline_id_format"),
        sa.CheckConstraint("length(finding_refs_json) BETWEEN 2 AND 524288", name="baseline_finding_refs_length"),
        sa.CheckConstraint("length(coverage_ids_json) BETWEEN 2 AND 524288", name="baseline_coverage_ids_length"),
        sa.CheckConstraint("length(protocol_versions_json) BETWEEN 3 AND 4096", name="baseline_protocol_versions_length"),
        sa.CheckConstraint("length(actor) BETWEEN 1 AND 128", name="baseline_actor_length"),
        sa.CheckConstraint("length(reason) BETWEEN 1 AND 1024", name="baseline_reason_length"),
        sa.CheckConstraint("accepted_at_us >= 0", name="baseline_accepted_nonnegative"),
        sa.CheckConstraint("length(coverage_digest) = 64 AND coverage_digest NOT GLOB '*[^0-9a-f]*'", name="baseline_coverage_digest_format"),
        sa.CheckConstraint("length(request_snapshot_sha256) = 64 AND request_snapshot_sha256 NOT GLOB '*[^0-9a-f]*'", name="baseline_snapshot_hash_format"),
    )
    op.create_index("ix_regression_baselines_project_accepted", "regression_baselines", ["project_id", "accepted_at_us"])
    op.create_table(
        "gate_results",
        sa.Column("gate_result_id", sa.String(length=37), nullable=False),
        sa.Column("schema_version", sa.String(length=8), nullable=False),
        sa.Column("baseline_id", sa.String(length=41), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("policy_version", sa.String(length=16), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("reasons_json", sa.Text(), nullable=False),
        sa.Column("decision", sa.String(length=8), nullable=False),
        sa.Column("evaluated_at_us", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("gate_result_id", name="pk_gate_results"),
        sa.ForeignKeyConstraint(["baseline_id"], ["regression_baselines.baseline_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.run_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("baseline_id", "run_id", "policy_version", "input_hash", name="uq_gate_result_input"),
        sa.CheckConstraint("schema_version = '1'", name="gate_result_schema_version_value"),
        sa.CheckConstraint("length(gate_result_id) = 37 AND substr(gate_result_id, 1, 5) = 'gate_' AND substr(gate_result_id, 6) NOT GLOB '*[^0-9a-f]*'", name="gate_result_id_format"),
        sa.CheckConstraint("policy_version = 'gate-v1'", name="gate_result_policy_version_value"),
        sa.CheckConstraint("decision IN ('PASS', 'BLOCK', 'ERROR')", name="gate_result_decision_value"),
        sa.CheckConstraint("length(reasons_json) BETWEEN 2 AND 524288", name="gate_result_reasons_length"),
        sa.CheckConstraint("evaluated_at_us >= 0", name="gate_result_evaluated_nonnegative"),
        sa.CheckConstraint("length(input_hash) = 64 AND input_hash NOT GLOB '*[^0-9a-f]*'", name="gate_result_input_hash_format"),
    )
    op.create_index("ix_gate_results_baseline_run", "gate_results", ["baseline_id", "run_id", "evaluated_at_us"])


def downgrade() -> None:
    raise RuntimeError("界鉴数据库迁移只允许向前；请从备份恢复旧版本")
