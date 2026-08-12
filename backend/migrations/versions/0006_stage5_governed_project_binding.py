"""为项目增加治理 ACTIVE Contract 绑定。"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_stage5_governed_project_binding"
down_revision: str | None = "0005_stage5_llm_candidate_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("governed_contract_id", sa.String(length=128), nullable=True))
    op.add_column("projects", sa.Column("governed_contract_version", sa.Integer(), nullable=True))
    op.execute(
        "CREATE TRIGGER projects_governed_binding_insert "
        "BEFORE INSERT ON projects BEGIN "
        "SELECT RAISE(ABORT, 'governed contract binding must be paired') "
        "WHERE (NEW.governed_contract_id IS NULL) != (NEW.governed_contract_version IS NULL) "
        "OR (NEW.governed_contract_version IS NOT NULL AND NEW.governed_contract_version < 1); END"
    )
    op.execute(
        "CREATE TRIGGER projects_governed_binding_update "
        "BEFORE UPDATE OF governed_contract_id, governed_contract_version ON projects BEGIN "
        "SELECT RAISE(ABORT, 'governed contract binding must be paired') "
        "WHERE (NEW.governed_contract_id IS NULL) != (NEW.governed_contract_version IS NULL) "
        "OR (NEW.governed_contract_version IS NOT NULL AND NEW.governed_contract_version < 1); END"
    )


def downgrade() -> None:
    raise RuntimeError("界鉴数据库迁移只允许向前；请从备份恢复旧版本")
