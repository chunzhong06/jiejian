# 增量迁移正式动作录制与技术准备绑定；旧录制准备非空时在全部 DDL 前拒绝。

"""action assurance recording

Revision ID: 0003_action_assurance_recording
Revises: 0002_business_boundary_maintenance
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_action_assurance_recording"
down_revision = "0002_business_boundary_maintenance"
branch_labels = None
depends_on = None

_LEGACY_TABLES = (
    "security_effect_confirmations", "recovery_bindings", "observation_bindings",
    "test_resources", "flow_draft_revisions", "recordings",
)
_BINDING_TABLES = (
    "action_evidence_bindings", "action_recovery_bindings", "action_resource_bindings", "action_execution_bindings",
)


def _preflight(bind, tables):
    for table in tables:
        if bind.execute(sa.text(f'SELECT 1 FROM "{table}" LIMIT 1')).first() is not None:
            raise RuntimeError("recording preparation data requires manual handling; migration made no changes")
    if bind.execute(sa.text("PRAGMA foreign_key_check")).first() is not None:
        raise RuntimeError("recording preparation migration requires valid existing foreign keys")


def upgrade():
    bind = op.get_bind()
    _preflight(bind, _LEGACY_TABLES)
    # 所有非空与关系检查先完成；不根据名称、源码或模型推测旧业务身份。
    for table in _LEGACY_TABLES[:4]:
        op.drop_table(table)
    with op.batch_alter_table("recordings", recreate="always") as batch:
        batch.add_column(sa.Column("business_action_id", sa.String(36), nullable=False))
        batch.add_column(sa.Column("action_revision", sa.Integer(), nullable=False))
        batch.add_column(sa.Column("test_identity_id", sa.String(36), nullable=False))
        batch.add_column(sa.Column("preparation_source_fingerprint", sa.String(64), nullable=False))
        batch.add_column(sa.Column("effect_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_recordings_business_action_id_business_action_revisions", "business_action_revisions",
                                 ["business_action_id", "action_revision"], ["action_id", "revision"], ondelete="RESTRICT")
        batch.create_foreign_key("fk_recordings_parent_recording_id_recordings", "recordings",
                                 ["parent_recording_id"], ["recording_id"], ondelete="RESTRICT")
        batch.create_check_constraint("action_revision_positive", "action_revision >= 1")
        batch.create_check_constraint("purpose_context_matrix",
            "(purpose = 'TARGET' AND parent_recording_id IS NULL AND effect_id IS NULL) OR "
            "(purpose = 'OBSERVATION' AND parent_recording_id IS NOT NULL AND effect_id IS NOT NULL) OR "
            "(purpose = 'RECOVERY' AND parent_recording_id IS NOT NULL AND effect_id IS NULL)")
    _create_bindings()
    if bind.execute(sa.text("PRAGMA foreign_key_check")).first() is not None:
        raise RuntimeError("action assurance migration broke a foreign key")


def _common(table):
    return [
        sa.Column("business_action_id", sa.String(36), primary_key=True),
        sa.Column("action_revision", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("action_semantic_fingerprint", sa.String(64), nullable=False),
        sa.Column("implementation_fingerprint", sa.String(64), nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=True),
        sa.Column("endpoint_fingerprint", sa.String(64), nullable=False),
        sa.Column("test_identity_id", sa.String(36), nullable=False),
        sa.Column("identity_fingerprint", sa.String(64), nullable=False),
        sa.Column("confirmed_at_us", sa.BigInteger(), nullable=False),
        sa.Column("binding_fingerprint", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"],
            name=op.f(f"fk_{table}_project_id_projects"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["business_action_id", "action_revision"],
            ["business_action_revisions.action_id", "business_action_revisions.revision"],
            name=op.f(f"fk_{table}_business_action_id_business_action_revisions"), ondelete="RESTRICT"),
        sa.CheckConstraint("action_revision >= 1 AND confirmed_at_us >= 0", name=op.f(f"ck_{table}_revision_time_bounds")),
        sa.CheckConstraint("length(binding_fingerprint) = 64 AND binding_fingerprint NOT GLOB '*[^0-9a-f]*'",
                           name=op.f(f"ck_{table}_binding_fingerprint_format")),
    ]


def _recorded(table, *, nullable=False):
    return [
        sa.Column("source_recording_id", sa.String(36), nullable=nullable),
        sa.Column("source_draft_revision", sa.Integer(), nullable=nullable),
        sa.Column("source_draft_sha256", sa.String(64), nullable=nullable),
        sa.ForeignKeyConstraint(["source_recording_id", "source_draft_revision"],
            ["flow_draft_revisions.recording_id", "flow_draft_revisions.revision"],
            name=op.f(f"fk_{table}_source_recording_id_flow_draft_revisions"), ondelete="RESTRICT"),
    ]


def _flow():
    return [sa.Column("flow_id", sa.String(64), nullable=False),
            sa.Column("flow_sha256", sa.String(64), nullable=False),
            sa.Column("resource_injection_json", sa.Text(), nullable=False)]


def _create_bindings():
    table = "action_execution_bindings"
    op.create_table(table, *_common(table), *_recorded(table), *_flow())
    table = "action_resource_bindings"
    op.create_table(table, *_common(table), *_recorded(table), *_flow(),
        sa.Column("owner_test_identity_id", sa.String(36), primary_key=True),
        sa.Column("actual_resource_id", sa.String(256), nullable=False),
        sa.CheckConstraint("owner_test_identity_id = test_identity_id", name=op.f("ck_action_resource_bindings_owner_identity_match")),
        sa.CheckConstraint("length(actual_resource_id) BETWEEN 1 AND 256", name=op.f("ck_action_resource_bindings_resource_value_bound")))
    table = "action_evidence_bindings"
    op.create_table(table, *_common(table), *_recorded(table, nullable=True),
        sa.Column("effect_id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("step_id", sa.String(64), nullable=True),
        sa.Column("request_template_json", sa.Text(), nullable=True),
        sa.Column("observer_reference_json", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "(kind = 'RECORDED_OBSERVATION' AND source_recording_id IS NOT NULL "
            "AND source_draft_revision IS NOT NULL AND source_draft_sha256 IS NOT NULL "
            "AND step_id IS NOT NULL AND request_template_json IS NOT NULL AND observer_reference_json IS NULL) OR "
            "(kind = 'REGISTERED_OBSERVER' AND source_recording_id IS NULL "
            "AND source_draft_revision IS NULL AND source_draft_sha256 IS NULL "
            "AND step_id IS NULL AND request_template_json IS NULL AND observer_reference_json IS NOT NULL)",
            name=op.f("ck_action_evidence_bindings_evidence_source_matrix")))
    table = "action_recovery_bindings"
    op.create_table(table, *_common(table), *_recorded(table),
        sa.Column("step_id", sa.String(64), nullable=False),
        sa.Column("request_template_json", sa.Text(), nullable=False))


def downgrade():
    # 业务准备来源不能被向旧格式猜测转换；降级只允许无录制、无绑定的库。
    bind = op.get_bind()
    _preflight(bind, (*_BINDING_TABLES, "flow_draft_revisions", "recordings"))
    raise RuntimeError("action assurance downgrade is unsupported; keep the database and restore an explicit backup")
