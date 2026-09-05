# 将 1.1.0 业务边界原地升级为可实时检查的持久来源结构。

"""business boundary maintenance

Revision ID: 0002_business_boundary_maintenance
Revises: 0001_business_boundary_v2
Create Date: 2026-09-03 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_business_boundary_maintenance"
down_revision: Union[str, None] = "0001_business_boundary_v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    _reject_current_superseded(bind, "business_actors", "business_actor_revisions", "actor_id")
    _reject_current_superseded(bind, "business_actions", "business_action_revisions", "action_id")
    _normalize_historical_superseded(
        bind, "business_actors", "business_actor_revisions", "actor_id"
    )
    _normalize_historical_superseded(
        bind, "business_actions", "business_action_revisions", "action_id"
    )

    # SQLite batch 必须重建被其他表引用的 revision 表，defer_foreign_keys
    # 仍会在 DROP 阶段失败；只在已完成精确结构预检后临时关闭 FK。
    _set_foreign_keys(bind, enabled=False)
    try:
        _upgrade_revision_states()
        _upgrade_actor_bindings()
        _upgrade_action_bindings()
    finally:
        _set_foreign_keys(bind, enabled=True)
    violation = bind.execute(sa.text("PRAGMA foreign_key_check")).first()
    if violation is not None:
        raise RuntimeError("business boundary maintenance migration broke a foreign key")


def downgrade() -> None:
    bind = op.get_bind()
    _set_foreign_keys(bind, enabled=False)
    try:
        _downgrade_revision_states()
        _downgrade_actor_bindings()
        _downgrade_action_bindings()
    finally:
        _set_foreign_keys(bind, enabled=True)
    violation = bind.execute(sa.text("PRAGMA foreign_key_check")).first()
    if violation is not None:
        raise RuntimeError("business boundary maintenance downgrade broke a foreign key")


def _reject_current_superseded(bind, roots: str, revisions: str, identity: str) -> None:
    row = bind.execute(
        sa.text(
            f"SELECT 1 FROM {roots} AS root "
            f"JOIN {revisions} AS revision "
            f"ON revision.{identity} = root.{identity} "
            "AND revision.revision = root.current_revision "
            "WHERE revision.effective_state = 'SUPERSEDED' LIMIT 1"
        )
    ).first()
    if row is not None:
        raise RuntimeError(
            f"{revisions} contains a current SUPERSEDED revision; manual repair required"
        )


def _normalize_historical_superseded(
    bind, roots: str, revisions: str, identity: str
) -> None:
    bind.execute(
        sa.text(
            f"UPDATE {revisions} AS revision SET effective_state = 'ACTIVE' "
            "WHERE revision.effective_state = 'SUPERSEDED' "
            f"AND NOT EXISTS (SELECT 1 FROM {roots} AS root "
            f"WHERE root.{identity} = revision.{identity} "
            "AND root.current_revision = revision.revision)"
        )
    )


def _set_foreign_keys(bind, *, enabled: bool) -> None:
    value = "ON" if enabled else "OFF"
    with op.get_context().autocommit_block():
        bind.exec_driver_sql(f"PRAGMA foreign_keys={value}")


def _upgrade_revision_states() -> None:
    for table in ("business_actor_revisions", "business_action_revisions"):
        with op.batch_alter_table(table, recreate="always") as batch:
            batch.drop_constraint(
                op.f(f"ck_{table}_effective_state_value"), type_="check"
            )
            batch.create_check_constraint(
                op.f(f"ck_{table}_effective_state_value"),
                "effective_state IN ('ACTIVE', 'RETIRED')",
            )


def _upgrade_actor_bindings() -> None:
    with op.batch_alter_table("actor_implementation_bindings", recreate="always") as batch:
        batch.drop_constraint(
            op.f("ck_actor_implementation_bindings_status_value"), type_="check"
        )
        batch.add_column(
            sa.Column("basis_version", sa.Integer(), nullable=False, server_default="1")
        )
        batch.add_column(
            sa.Column("source_proposal_id", sa.String(length=36), nullable=True)
        )
        batch.add_column(sa.Column("confirmed_at_us", sa.BigInteger(), nullable=True))
        batch.add_column(
            sa.Column(
                "candidate_snapshots_json",
                sa.Text(),
                nullable=False,
                server_default="[]",
            )
        )
        batch.create_check_constraint(
            op.f("ck_actor_implementation_bindings_basis_version_value"),
            "basis_version IN (1, 2)",
        )
        batch.create_foreign_key(
            op.f(
                "fk_actor_implementation_bindings_source_proposal_id_boundary_proposals"
            ),
            "boundary_proposals",
            ["source_proposal_id"],
            ["proposal_id"],
            ondelete="RESTRICT",
        )
        batch.drop_column("status")
        batch.drop_column("reason_codes_json")


def _upgrade_action_bindings() -> None:
    with op.batch_alter_table("action_implementation_bindings", recreate="always") as batch:
        batch.drop_constraint(
            op.f("ck_action_implementation_bindings_status_value"), type_="check"
        )
        batch.add_column(
            sa.Column("basis_version", sa.Integer(), nullable=False, server_default="1")
        )
        batch.add_column(
            sa.Column("source_proposal_id", sa.String(length=36), nullable=True)
        )
        batch.add_column(sa.Column("confirmed_at_us", sa.BigInteger(), nullable=True))
        batch.add_column(
            sa.Column(
                "candidate_snapshots_json",
                sa.Text(),
                nullable=False,
                server_default="[]",
            )
        )
        batch.create_check_constraint(
            op.f("ck_action_implementation_bindings_basis_version_value"),
            "basis_version IN (1, 2)",
        )
        batch.create_foreign_key(
            op.f(
                "fk_action_implementation_bindings_source_proposal_id_boundary_proposals"
            ),
            "boundary_proposals",
            ["source_proposal_id"],
            ["proposal_id"],
            ondelete="RESTRICT",
        )
        batch.drop_column("status")
        batch.drop_column("reason_codes_json")


def _downgrade_revision_states() -> None:
    for table in ("business_actor_revisions", "business_action_revisions"):
        with op.batch_alter_table(table, recreate="always") as batch:
            batch.drop_constraint(
                op.f(f"ck_{table}_effective_state_value"), type_="check"
            )
            batch.create_check_constraint(
                op.f(f"ck_{table}_effective_state_value"),
                "effective_state IN ('ACTIVE', 'SUPERSEDED', 'RETIRED')",
            )


def _downgrade_actor_bindings() -> None:
    with op.batch_alter_table("actor_implementation_bindings", recreate="always") as batch:
        batch.drop_constraint(
            op.f(
                "fk_actor_implementation_bindings_source_proposal_id_boundary_proposals"
            ),
            type_="foreignkey",
        )
        batch.drop_constraint(
            op.f("ck_actor_implementation_bindings_basis_version_value"),
            type_="check",
        )
        batch.add_column(
            sa.Column("status", sa.String(length=16), nullable=False, server_default="MISSING")
        )
        batch.add_column(
            sa.Column(
                "reason_codes_json",
                sa.Text(),
                nullable=False,
                server_default='["MIGRATION_DOWNGRADE_REVIEW_REQUIRED"]',
            )
        )
        batch.create_check_constraint(
            op.f("ck_actor_implementation_bindings_status_value"),
            "status IN ('CURRENT', 'STALE', 'MISSING', 'AMBIGUOUS')",
        )
        batch.drop_column("candidate_snapshots_json")
        batch.drop_column("confirmed_at_us")
        batch.drop_column("source_proposal_id")
        batch.drop_column("basis_version")
    op.execute(
        "UPDATE actor_implementation_bindings SET status = "
        "CASE WHEN role_candidate_ids_json = '[]' THEN 'MISSING' ELSE 'STALE' END"
    )


def _downgrade_action_bindings() -> None:
    with op.batch_alter_table("action_implementation_bindings", recreate="always") as batch:
        batch.drop_constraint(
            op.f(
                "fk_action_implementation_bindings_source_proposal_id_boundary_proposals"
            ),
            type_="foreignkey",
        )
        batch.drop_constraint(
            op.f("ck_action_implementation_bindings_basis_version_value"),
            type_="check",
        )
        batch.add_column(
            sa.Column("status", sa.String(length=16), nullable=False, server_default="MISSING")
        )
        batch.add_column(
            sa.Column(
                "reason_codes_json",
                sa.Text(),
                nullable=False,
                server_default='["MIGRATION_DOWNGRADE_REVIEW_REQUIRED"]',
            )
        )
        batch.create_check_constraint(
            op.f("ck_action_implementation_bindings_status_value"),
            "status IN ('CURRENT', 'STALE', 'MISSING', 'AMBIGUOUS')",
        )
        batch.drop_column("candidate_snapshots_json")
        batch.drop_column("confirmed_at_us")
        batch.drop_column("source_proposal_id")
        batch.drop_column("basis_version")
    op.execute(
        "UPDATE action_implementation_bindings SET status = "
        "CASE WHEN action_candidate_ids_json = '[]' THEN 'MISSING' ELSE 'STALE' END"
    )
