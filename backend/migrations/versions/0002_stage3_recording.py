"""增加阶段 3.3 Recording、FlowDraft revision 与 Job 目标关联。"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_stage3_recording"
down_revision: str | None = "0001_stage2_storage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recordings",
        sa.Column("recording_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("flow_id", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("created_at_us", sa.BigInteger(), nullable=False),
        sa.Column("updated_at_us", sa.BigInteger(), nullable=False),
        sa.Column("started_at_us", sa.BigInteger(), nullable=True),
        sa.Column("capture_finished_at_us", sa.BigInteger(), nullable=True),
        sa.Column("finished_at_us", sa.BigInteger(), nullable=True),
        sa.Column("pending_terminal_state", sa.String(length=24), nullable=True),
        sa.Column("reason_codes_json", sa.Text(), nullable=False),
        sa.Column("state_events_json", sa.Text(), nullable=False),
        sa.Column("browser_events_json", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "length(recording_id) = 36 AND substr(recording_id, 1, 4) = 'rec_' "
            "AND substr(recording_id, 5) NOT GLOB '*[^0-9a-f]*'",
            name="recording_id_format",
        ),
        sa.CheckConstraint(
            "state IN ('CREATED', 'STARTING', 'RECORDING', 'CLEANING', "
            "'PROCESSING', 'PENDING_REVIEW', 'COMPLETED', 'FAILED', "
            "'CANCELLED', 'SAFETY_STOPPED')",
            name="state_value",
        ),
        sa.CheckConstraint(
            "length(flow_id) BETWEEN 1 AND 64 "
            "AND substr(flow_id, 1, 1) GLOB '[a-z]' "
            "AND flow_id NOT GLOB '*[^a-z0-9_-]*'",
            name="flow_id_format",
        ),
        sa.CheckConstraint(
            "pending_terminal_state IS NULL OR pending_terminal_state IN "
            "('FAILED', 'CANCELLED', 'SAFETY_STOPPED')",
            name="pending_terminal_state_value",
        ),
        sa.CheckConstraint(
            "created_at_us >= 0 AND updated_at_us >= created_at_us "
            "AND (started_at_us IS NULL OR started_at_us >= created_at_us) "
            "AND (capture_finished_at_us IS NULL OR "
            "capture_finished_at_us >= started_at_us) "
            "AND (finished_at_us IS NULL OR finished_at_us >= updated_at_us)",
            name="time_order",
        ),
        sa.CheckConstraint(
            "(state IN ('COMPLETED', 'FAILED', 'CANCELLED', 'SAFETY_STOPPED') "
            "AND finished_at_us IS NOT NULL) OR "
            "(state NOT IN ('COMPLETED', 'FAILED', 'CANCELLED', "
            "'SAFETY_STOPPED') AND finished_at_us IS NULL)",
            name="terminal_finish_matrix",
        ),
        sa.CheckConstraint(
            "length(reason_codes_json) BETWEEN 2 AND 8192 "
            "AND length(state_events_json) BETWEEN 2 AND 131072 "
            "AND length(browser_events_json) BETWEEN 2 AND 4194304",
            name="json_size_bounds",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_recordings_project_id_projects",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("recording_id", name="pk_recordings"),
    )
    op.create_index(
        "ix_recordings_project_created",
        "recordings",
        ["project_id", "created_at_us"],
        unique=False,
    )
    op.create_index(
        "ix_recordings_state_updated",
        "recordings",
        ["state", "updated_at_us"],
        unique=False,
    )

    op.create_table(
        "flow_draft_revisions",
        sa.Column("recording_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("flow_id", sa.String(length=64), nullable=False),
        sa.Column("draft_json", sa.Text(), nullable=False),
        sa.Column("draft_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at_us", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
        sa.CheckConstraint(
            "length(flow_id) BETWEEN 1 AND 64 "
            "AND substr(flow_id, 1, 1) GLOB '[a-z]' "
            "AND flow_id NOT GLOB '*[^a-z0-9_-]*'",
            name="flow_id_format",
        ),
        sa.CheckConstraint(
            "length(draft_sha256) = 64 "
            "AND draft_sha256 NOT GLOB '*[^0-9a-f]*'",
            name="draft_sha256_format",
        ),
        sa.CheckConstraint(
            "length(draft_json) BETWEEN 2 AND 4194304",
            name="draft_json_size",
        ),
        sa.CheckConstraint("created_at_us >= 0", name="created_nonnegative"),
        sa.ForeignKeyConstraint(
            ["recording_id"],
            ["recordings.recording_id"],
            name="fk_flow_draft_revisions_recording_id_recordings",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "recording_id",
            "revision",
            name="pk_flow_draft_revisions",
        ),
    )
    op.create_index(
        "ix_flow_drafts_flow_created",
        "flow_draft_revisions",
        ["flow_id", "created_at_us"],
        unique=False,
    )

    _rebuild_jobs_with_recording_target()


def _rebuild_jobs_with_recording_target() -> None:
    op.execute(
        "CREATE TABLE _stage3_job_events_backup AS SELECT * FROM job_events"
    )
    op.drop_index("ix_job_events_job_occurred", table_name="job_events")
    op.drop_table("job_events")
    with op.batch_alter_table("jobs", recreate="always") as batch:
        batch.alter_column(
            "run_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )
        batch.add_column(sa.Column("recording_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            "fk_jobs_recording_id_recordings",
            "recordings",
            ["recording_id"],
            ["recording_id"],
            ondelete="RESTRICT",
        )
        batch.create_unique_constraint("uq_jobs_recording_id", ["recording_id"])
        batch.create_check_constraint(
            "exactly_one_target",
            "(run_id IS NOT NULL AND recording_id IS NULL) OR "
            "(run_id IS NULL AND recording_id IS NOT NULL)",
        )
    _create_job_events()
    op.execute(
        "INSERT INTO job_events "
        "(job_id, sequence, event_type, source_state, target_state, "
        "occurred_at_us, metadata_json) "
        "SELECT job_id, sequence, event_type, source_state, target_state, "
        "occurred_at_us, metadata_json FROM _stage3_job_events_backup"
    )
    op.drop_table("_stage3_job_events_backup")


def _create_job_events() -> None:
    op.create_table(
        "job_events",
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("source_state", sa.String(length=16), nullable=True),
        sa.Column("target_state", sa.String(length=16), nullable=True),
        sa.Column("occurred_at_us", sa.BigInteger(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.CheckConstraint("sequence >= 1", name="sequence_positive"),
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
        sa.CheckConstraint("occurred_at_us >= 0", name="occurred_nonnegative"),
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
        sa.PrimaryKeyConstraint("job_id", "sequence", name="pk_job_events"),
    )
    op.create_index(
        "ix_job_events_job_occurred",
        "job_events",
        ["job_id", "occurred_at_us"],
        unique=False,
    )


def downgrade() -> None:
    raise RuntimeError("界鉴数据库迁移只允许向前；请从备份恢复旧版本")
