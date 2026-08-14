"""阶段 6 权限执行 Profile 的非秘密治理元数据。"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0008_permission_execution_profiles"
down_revision: str | None = "0007_stage5_llm_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "permission_execution_profiles",
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=8), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("source_path", sa.String(length=2048), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("contract_id", sa.String(length=128), nullable=False),
        sa.Column("contract_version", sa.Integer(), nullable=False),
        sa.Column("contract_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("plan_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("engine_version", sa.String(length=128), nullable=False),
        sa.Column("created_at_us", sa.BigInteger(), nullable=False),
        sa.Column("updated_at_us", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("profile_id", name="pk_permission_execution_profiles"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"]),
        sa.CheckConstraint("schema_version = '2'", name="profile_schema_version_value"),
        sa.CheckConstraint(
            "length(profile_id) BETWEEN 1 AND 64 AND "
            "substr(profile_id, 1, 1) GLOB '[a-z]' AND "
            "profile_id NOT GLOB '*[^a-z0-9_-]*'",
            name="profile_id_format",
        ),
        sa.CheckConstraint("contract_version >= 1", name="profile_contract_version"),
        sa.CheckConstraint(
            "length(source_hash) = 64 AND length(contract_fingerprint) = 64 "
            "AND length(plan_fingerprint) = 64",
            name="profile_hash_lengths",
        ),
        sa.CheckConstraint(
            "created_at_us >= 0 AND updated_at_us >= created_at_us",
            name="profile_time_order",
        ),
    )
    op.create_index(
        "ix_permission_profiles_project_updated",
        "permission_execution_profiles",
        ["project_id", "updated_at_us"],
    )


def downgrade() -> None:
    raise RuntimeError("界鉴数据库迁移只允许向前；请从备份恢复旧版本")
