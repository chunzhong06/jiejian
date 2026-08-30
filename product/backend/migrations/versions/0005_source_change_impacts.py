# 为受控源码版本、真实变化与权限实现影响增加有界聚合存储。

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005_source_change_impacts"
down_revision = "0004_recording_supplements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_revision_snapshots",
        sa.Column("snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("understanding_revision", sa.Integer(), nullable=False),
        sa.Column("files_json", sa.Text(), nullable=False),
        sa.Column("created_at_us", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "length(snapshot_id) = 36",
            name=op.f("ck_source_revision_snapshots_snapshot_id_length"),
        ),
        sa.CheckConstraint(
            "length(source_fingerprint) = 64",
            name=op.f("ck_source_revision_snapshots_fingerprint_length"),
        ),
        sa.CheckConstraint(
            "understanding_revision BETWEEN 0 AND 1000000",
            name=op.f("ck_source_revision_snapshots_understanding_revision_range"),
        ),
        sa.CheckConstraint(
            "length(files_json) BETWEEN 2 AND 1048576",
            name=op.f("ck_source_revision_snapshots_files_json_length"),
        ),
        sa.CheckConstraint(
            "created_at_us >= 0",
            name=op.f("ck_source_revision_snapshots_created_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name=op.f("fk_source_revision_snapshots_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "snapshot_id",
            name=op.f("pk_source_revision_snapshots"),
        ),
        sa.UniqueConstraint(
            "project_id",
            "source_fingerprint",
            name="uq_source_revision_project_fingerprint",
        ),
    )
    op.create_index(
        "ix_source_revision_project_created",
        "source_revision_snapshots",
        ["project_id", "created_at_us"],
        unique=False,
    )

    op.create_table(
        "change_manifests",
        sa.Column("change_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=512), nullable=False),
        sa.Column("claimed_paths_json", sa.Text(), nullable=False),
        sa.Column("submitted_by", sa.String(length=128), nullable=False),
        sa.Column("created_at_us", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "length(change_id) = 36",
            name=op.f("ck_change_manifests_change_id_length"),
        ),
        sa.CheckConstraint(
            "length(reason) BETWEEN 1 AND 512",
            name=op.f("ck_change_manifests_reason_length"),
        ),
        sa.CheckConstraint(
            "length(claimed_paths_json) BETWEEN 2 AND 131072",
            name=op.f("ck_change_manifests_claimed_paths_json_length"),
        ),
        sa.CheckConstraint(
            "length(submitted_by) BETWEEN 1 AND 128",
            name=op.f("ck_change_manifests_submitted_by_length"),
        ),
        sa.CheckConstraint(
            "created_at_us >= 0",
            name=op.f("ck_change_manifests_created_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name=op.f("fk_change_manifests_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("change_id", name=op.f("pk_change_manifests")),
    )
    op.create_index(
        "ix_change_manifests_project_created",
        "change_manifests",
        ["project_id", "created_at_us"],
        unique=False,
    )

    op.create_table(
        "source_change_sets",
        sa.Column("change_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("previous_snapshot_id", sa.String(length=36), nullable=True),
        sa.Column("current_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("added_paths_json", sa.Text(), nullable=False),
        sa.Column("modified_paths_json", sa.Text(), nullable=False),
        sa.Column("removed_paths_json", sa.Text(), nullable=False),
        sa.Column("change_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at_us", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "status IN ('COMPARABLE', 'NO_BASELINE')",
            name=op.f("ck_source_change_sets_status_value"),
        ),
        sa.CheckConstraint(
            "length(change_fingerprint) = 64",
            name=op.f("ck_source_change_sets_fingerprint_length"),
        ),
        sa.CheckConstraint(
            "length(added_paths_json) BETWEEN 2 AND 524288",
            name=op.f("ck_source_change_sets_added_json_length"),
        ),
        sa.CheckConstraint(
            "length(modified_paths_json) BETWEEN 2 AND 524288",
            name=op.f("ck_source_change_sets_modified_json_length"),
        ),
        sa.CheckConstraint(
            "length(removed_paths_json) BETWEEN 2 AND 524288",
            name=op.f("ck_source_change_sets_removed_json_length"),
        ),
        sa.CheckConstraint(
            "created_at_us >= 0",
            name=op.f("ck_source_change_sets_created_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["change_id"],
            ["change_manifests.change_id"],
            name=op.f("fk_source_change_sets_change_id_change_manifests"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name=op.f("fk_source_change_sets_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["previous_snapshot_id"],
            ["source_revision_snapshots.snapshot_id"],
            name=op.f("fk_source_change_sets_previous_snapshot_id_source_revision_snapshots"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["current_snapshot_id"],
            ["source_revision_snapshots.snapshot_id"],
            name=op.f("fk_source_change_sets_current_snapshot_id_source_revision_snapshots"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("change_id", name=op.f("pk_source_change_sets")),
    )

    op.create_table(
        "change_impact_assessments",
        sa.Column("change_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("change_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column("reason_codes_json", sa.Text(), nullable=False),
        sa.Column("impacts_json", sa.Text(), nullable=False),
        sa.Column("impact_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at_us", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "length(change_fingerprint) = 64",
            name=op.f("ck_change_impact_assessments_change_fingerprint_length"),
        ),
        sa.CheckConstraint(
            "length(reason_codes_json) BETWEEN 2 AND 8192",
            name=op.f("ck_change_impact_assessments_reasons_json_length"),
        ),
        sa.CheckConstraint(
            "length(impacts_json) BETWEEN 2 AND 2097152",
            name=op.f("ck_change_impact_assessments_impacts_json_length"),
        ),
        sa.CheckConstraint(
            "length(impact_fingerprint) = 64",
            name=op.f("ck_change_impact_assessments_impact_fingerprint_length"),
        ),
        sa.CheckConstraint(
            "created_at_us >= 0",
            name=op.f("ck_change_impact_assessments_created_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["change_id"],
            ["change_manifests.change_id"],
            name=op.f("fk_change_impact_assessments_change_id_change_manifests"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name=op.f("fk_change_impact_assessments_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "change_id",
            name=op.f("pk_change_impact_assessments"),
        ),
    )
    op.create_index(
        "ix_change_impacts_project_created",
        "change_impact_assessments",
        ["project_id", "created_at_us"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_change_impacts_project_created", table_name="change_impact_assessments")
    op.drop_table("change_impact_assessments")
    op.drop_table("source_change_sets")
    op.drop_index("ix_change_manifests_project_created", table_name="change_manifests")
    op.drop_table("change_manifests")
    op.drop_index("ix_source_revision_project_created", table_name="source_revision_snapshots")
    op.drop_table("source_revision_snapshots")
