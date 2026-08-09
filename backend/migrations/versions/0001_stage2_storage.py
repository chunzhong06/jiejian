"""创建阶段 2.1 持久化表。"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_stage2_storage"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at_us", sa.BigInteger(), nullable=False),
        sa.Column("updated_at_us", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "length(project_id) BETWEEN 1 AND 64 "
            "AND substr(project_id, 1, 1) GLOB '[a-z]' "
            "AND project_id NOT GLOB '*[^a-z0-9_-]*'",
            name="project_id_format",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'READY', 'ARCHIVED')",
            name="status_value",
        ),
        sa.CheckConstraint(
            "length(name) BETWEEN 1 AND 128",
            name="name_length",
        ),
        sa.CheckConstraint(
            "created_at_us >= 0 AND updated_at_us >= created_at_us",
            name="time_order",
        ),
        sa.PrimaryKeyConstraint("project_id", name="pk_projects"),
    )
    op.create_index(
        "ix_projects_status_updated",
        "projects",
        ["status", "updated_at_us"],
        unique=False,
    )

    op.create_table(
        "runs",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("contract_id", sa.String(length=128), nullable=False),
        sa.Column("contract_version", sa.Integer(), nullable=False),
        sa.Column("engine_version", sa.String(length=64), nullable=False),
        sa.Column("lifecycle", sa.String(length=24), nullable=False),
        sa.Column("verdict", sa.String(length=16), nullable=True),
        sa.Column("created_at_us", sa.BigInteger(), nullable=False),
        sa.Column("updated_at_us", sa.BigInteger(), nullable=False),
        sa.Column("finished_at_us", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "length(run_id) = 36 AND substr(run_id, 1, 4) = 'run_' "
            "AND substr(run_id, 5) NOT GLOB '*[^0-9a-f]*'",
            name="run_id_format",
        ),
        sa.CheckConstraint(
            "lifecycle IN ('QUEUED', 'PREFLIGHT', 'PLANNING', 'EXECUTING', "
            "'VERIFYING', 'REPORTING', 'COMPLETED', 'FAILED', 'CANCELLED', "
            "'SAFETY_STOPPED')",
            name="lifecycle_value",
        ),
        sa.CheckConstraint(
            "verdict IS NULL OR verdict IN ('PASS', 'BLOCK', 'INCONCLUSIVE')",
            name="verdict_value",
        ),
        sa.CheckConstraint(
            "(lifecycle = 'COMPLETED' AND verdict IS NOT NULL) OR "
            "(lifecycle <> 'COMPLETED' AND verdict IS NULL)",
            name="lifecycle_verdict_matrix",
        ),
        sa.CheckConstraint(
            "contract_version >= 1",
            name="contract_version_positive",
        ),
        sa.CheckConstraint(
            "created_at_us >= 0 AND updated_at_us >= created_at_us "
            "AND (finished_at_us IS NULL OR finished_at_us >= created_at_us)",
            name="time_order",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_runs_project_id_projects",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("run_id", name="pk_runs"),
    )
    op.create_index(
        "ix_runs_project_created",
        "runs",
        ["project_id", "created_at_us"],
        unique=False,
    )
    op.create_index(
        "ix_runs_lifecycle_updated",
        "runs",
        ["lifecycle", "updated_at_us"],
        unique=False,
    )

    op.create_table(
        "jobs",
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("operation_type", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at_us", sa.BigInteger(), nullable=False),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("fencing_token", sa.BigInteger(), nullable=False),
        sa.Column("lease_expires_at_us", sa.BigInteger(), nullable=True),
        sa.Column("cancel_requested_at_us", sa.BigInteger(), nullable=True),
        sa.Column("created_at_us", sa.BigInteger(), nullable=False),
        sa.Column("updated_at_us", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "length(job_id) = 36 AND substr(job_id, 1, 4) = 'job_' "
            "AND substr(job_id, 5) NOT GLOB '*[^0-9a-f]*'",
            name="job_id_format",
        ),
        sa.CheckConstraint(
            "length(operation_type) BETWEEN 1 AND 64 "
            "AND operation_type NOT GLOB '*[^A-Z0-9_]*'",
            name="operation_type_format",
        ),
        sa.CheckConstraint(
            "state IN ('PENDING', 'RUNNING', 'RETRY_WAIT', 'SUCCEEDED', "
            "'FAILED', 'CANCELLED')",
            name="state_value",
        ),
        sa.CheckConstraint(
            "length(idempotency_key) BETWEEN 1 AND 128",
            name="idempotency_key_length",
        ),
        sa.CheckConstraint(
            "length(request_hash) = 64 "
            "AND request_hash NOT GLOB '*[^0-9a-f]*'",
            name="request_hash_format",
        ),
        sa.CheckConstraint(
            "attempt >= 0 AND max_attempts >= 1 AND attempt <= max_attempts",
            name="attempt_bounds",
        ),
        sa.CheckConstraint(
            "fencing_token >= 0",
            name="fencing_nonnegative",
        ),
        sa.CheckConstraint(
            "(attempt = 0 AND fencing_token = 0 AND lease_owner IS NULL "
            "AND lease_expires_at_us IS NULL) OR "
            "(attempt > 0 AND fencing_token > 0)",
            name="attempt_fencing_relation",
        ),
        sa.CheckConstraint(
            "(lease_owner IS NULL AND lease_expires_at_us IS NULL) OR "
            "(lease_owner IS NOT NULL AND lease_expires_at_us IS NOT NULL)",
            name="lease_pair",
        ),
        sa.CheckConstraint(
            "state <> 'RUNNING' OR (lease_owner IS NOT NULL "
            "AND fencing_token > 0 AND lease_expires_at_us IS NOT NULL)",
            name="running_lease_required",
        ),
        sa.CheckConstraint(
            "lease_owner IS NULL OR (length(lease_owner) BETWEEN 1 AND 128 "
            "AND lease_owner NOT GLOB '*[^A-Za-z0-9._:-]*')",
            name="lease_owner_format",
        ),
        sa.CheckConstraint(
            "created_at_us >= 0 AND updated_at_us >= created_at_us "
            "AND available_at_us >= 0 "
            "AND (lease_expires_at_us IS NULL OR lease_expires_at_us >= 0) "
            "AND (cancel_requested_at_us IS NULL "
            "OR cancel_requested_at_us >= created_at_us)",
            name="time_bounds",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_jobs_project_id_projects",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.run_id"],
            name="fk_jobs_run_id_runs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("job_id", name="pk_jobs"),
        sa.UniqueConstraint("run_id", name="uq_jobs_run_id"),
        sa.UniqueConstraint(
            "project_id",
            "operation_type",
            "idempotency_key",
            name="uq_jobs_idempotency_scope",
        ),
    )
    op.create_index(
        "ix_jobs_state_available",
        "jobs",
        ["state", "available_at_us"],
        unique=False,
    )
    op.create_index(
        "ix_jobs_state_lease_expires",
        "jobs",
        ["state", "lease_expires_at_us"],
        unique=False,
    )

    op.create_table(
        "job_events",
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("source_state", sa.String(length=16), nullable=True),
        sa.Column("target_state", sa.String(length=16), nullable=True),
        sa.Column("occurred_at_us", sa.BigInteger(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "sequence >= 1",
            name="sequence_positive",
        ),
        sa.CheckConstraint(
            "length(event_type) BETWEEN 1 AND 64 "
            "AND event_type NOT GLOB '*[^A-Z0-9_]*'",
            name="event_type_format",
        ),
        sa.CheckConstraint(
            "source_state IS NULL OR source_state IN ('PENDING', 'RUNNING', "
            "'RETRY_WAIT', 'SUCCEEDED', 'FAILED', 'CANCELLED')",
            name="source_state_value",
        ),
        sa.CheckConstraint(
            "target_state IS NULL OR target_state IN ('PENDING', 'RUNNING', "
            "'RETRY_WAIT', 'SUCCEEDED', 'FAILED', 'CANCELLED')",
            name="target_state_value",
        ),
        sa.CheckConstraint(
            "occurred_at_us >= 0",
            name="occurred_nonnegative",
        ),
        sa.CheckConstraint(
            "length(metadata_json) BETWEEN 2 AND 4096",
            name="metadata_length",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.job_id"],
            name="fk_job_events_job_id_jobs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "job_id",
            "sequence",
            name="pk_job_events",
        ),
    )
    op.create_index(
        "ix_job_events_job_occurred",
        "job_events",
        ["job_id", "occurred_at_us"],
        unique=False,
    )

    op.create_table(
        "evidence_index",
        sa.Column("evidence_id", sa.String(length=67), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=128), nullable=False),
        sa.Column(
            "artifact_path",
            sa.String(length=512, collation="NOCASE"),
            nullable=False,
        ),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_count", sa.BigInteger(), nullable=False),
        sa.Column("created_at_us", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "length(evidence_id) BETWEEN 23 AND 67 "
            "AND substr(evidence_id, 1, 3) = 'ev_' "
            "AND substr(evidence_id, 4) NOT GLOB '*[^0-9a-f]*'",
            name="evidence_id_format",
        ),
        sa.CheckConstraint(
            "length(case_id) BETWEEN 1 AND 128",
            name="case_id_length",
        ),
        sa.CheckConstraint(
            "length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'",
            name="sha256_format",
        ),
        sa.CheckConstraint(
            "substr(sha256, 1, length(evidence_id) - 3) = "
            "substr(evidence_id, 4)",
            name="content_address_match",
        ),
        sa.CheckConstraint(
            "length(artifact_path) BETWEEN 1 AND 512 "
            "AND substr(artifact_path, 1, 1) <> '/' "
            "AND instr(artifact_path, '\\') = 0 "
            "AND instr(artifact_path, ':') = 0 "
            "AND instr(artifact_path, char(0)) = 0 "
            "AND artifact_path NOT LIKE '%//%'",
            name="artifact_path_basic",
        ),
        sa.CheckConstraint(
            "byte_count BETWEEN 0 AND 1073741824",
            name="byte_count_bounds",
        ),
        sa.CheckConstraint(
            "created_at_us >= 0",
            name="created_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.run_id"],
            name="fk_evidence_index_run_id_runs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("evidence_id", name="pk_evidence_index"),
        sa.UniqueConstraint(
            "run_id",
            "case_id",
            name="uq_evidence_run_case",
        ),
        sa.UniqueConstraint(
            "run_id",
            "artifact_path",
            name="uq_evidence_run_artifact_path",
        ),
    )
    op.create_index(
        "ix_evidence_run_created",
        "evidence_index",
        ["run_id", "created_at_us"],
        unique=False,
    )


def downgrade() -> None:
    raise RuntimeError("界鉴数据库迁移只允许向前；请从备份恢复旧版本")
