"""为阶段 4 项目控制面保存来源与激活契约身份。"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_stage4_control_plane"
down_revision: str | None = "0002_stage3_recording"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("source_path", sa.String(length=1024), nullable=True))
    op.add_column("projects", sa.Column("source_hash", sa.String(length=64), nullable=True))
    op.add_column("projects", sa.Column("active_contract_path", sa.String(length=1024), nullable=True))
    op.add_column("projects", sa.Column("active_contract_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    raise RuntimeError("界鉴数据库迁移只允许向前；请从备份恢复旧版本")
