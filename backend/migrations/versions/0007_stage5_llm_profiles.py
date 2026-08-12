"""新增非秘密 LLM profile 配置表。"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0007_stage5_llm_profiles"
down_revision: str | None = "0006_stage5_governed_project_binding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_profiles",
        sa.Column("profile_name", sa.String(length=128), nullable=False),
        sa.Column("schema_version", sa.String(length=8), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=256), nullable=False),
        sa.Column("base_url", sa.String(length=2048), nullable=True),
        sa.Column("timeout_ms", sa.Integer(), nullable=False),
        sa.Column("max_input_bytes", sa.Integer(), nullable=False),
        sa.Column("max_output_bytes", sa.Integer(), nullable=False),
        sa.Column("max_budget_microusd", sa.BigInteger(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("secret_ref", sa.String(length=256), nullable=True),
        sa.Column("allow_local_http", sa.Boolean(), nullable=False),
        sa.Column("created_at_us", sa.BigInteger(), nullable=False),
        sa.Column("updated_at_us", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("profile_name", name="pk_llm_profiles"),
        sa.CheckConstraint("schema_version = '1'", name="schema_version_value"),
        sa.CheckConstraint(
            "provider IN ('openai', 'deepseek', 'gemini', 'openai_compatible')",
            name="provider_value",
        ),
        sa.CheckConstraint(
            "length(profile_name) BETWEEN 1 AND 128 AND "
            "substr(profile_name, 1, 1) GLOB '[a-z]' AND "
            "profile_name NOT GLOB '*[^a-z0-9_-]*'",
            name="profile_name_format",
        ),
        sa.CheckConstraint("length(model) BETWEEN 1 AND 256", name="model_length"),
        sa.CheckConstraint(
            "base_url IS NULL OR length(base_url) BETWEEN 1 AND 2048",
            name="base_url_length",
        ),
        sa.CheckConstraint("timeout_ms BETWEEN 100 AND 300000", name="timeout_range"),
        sa.CheckConstraint("max_input_bytes BETWEEN 1 AND 1048576", name="input_bytes_range"),
        sa.CheckConstraint("max_output_bytes BETWEEN 1 AND 1048576", name="output_bytes_range"),
        sa.CheckConstraint(
            "max_budget_microusd BETWEEN 0 AND 1000000000",
            name="budget_range",
        ),
        sa.CheckConstraint(
            "secret_ref IS NULL OR length(secret_ref) BETWEEN 1 AND 256",
            name="secret_ref_length",
        ),
        sa.CheckConstraint(
            "created_at_us >= 0 AND updated_at_us >= created_at_us",
            name="time_order",
        ),
    )


def downgrade() -> None:
    raise RuntimeError("界鉴数据库迁移只允许向前；请从备份恢复旧版本")
