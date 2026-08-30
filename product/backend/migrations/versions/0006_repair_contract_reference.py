# 为代码变化声明增加可选的权威修复要求引用，不复制 RepairContract。

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0006_repair_contract_reference"
down_revision = "0005_source_change_impacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("change_manifests") as batch_op:
        batch_op.add_column(sa.Column("repair_reference_json", sa.Text(), nullable=True))
        batch_op.create_check_constraint(
            op.f("ck_change_manifests_repair_reference_json_length"),
            "repair_reference_json IS NULL OR "
            "length(repair_reference_json) BETWEEN 2 AND 1024",
        )


def downgrade() -> None:
    with op.batch_alter_table("change_manifests") as batch_op:
        batch_op.drop_constraint(
            op.f("ck_change_manifests_repair_reference_json_length"),
            type_="check",
        )
        batch_op.drop_column("repair_reference_json")
