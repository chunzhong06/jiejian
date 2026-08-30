# 为既有 Recording 增加目标、观察和恢复补录的父子关系。

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_recording_supplements"
down_revision = "0003_permission_intent_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recordings",
        sa.Column("purpose", sa.String(length=16), nullable=False, server_default="TARGET"),
    )
    op.add_column(
        "recordings",
        sa.Column("parent_recording_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_recordings_parent_purpose",
        "recordings",
        ["parent_recording_id", "purpose"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_recordings_parent_purpose", table_name="recordings")
    op.drop_column("recordings", "parent_recording_id")
    op.drop_column("recordings", "purpose")
