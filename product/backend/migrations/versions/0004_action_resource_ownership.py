# 增量分离录制操作身份与资源所有者；所有历史校验在 DDL 前完成，不改写原始文件。
from __future__ import annotations

import hashlib
import json
from alembic import op
import sqlalchemy as sa

revision = "0004_action_resource_ownership"
down_revision = "0003_action_assurance_recording"
branch_labels = None
depends_on = None

_KINDS = {
    "action_execution_bindings": "ActionExecutionBinding",
    "action_resource_bindings": "ActionResourceBinding",
    "action_evidence_bindings": "ActionEvidenceBinding",
    "action_recovery_bindings": "ActionRecoveryBinding",
}
_JSON = {"resource_injection_json", "request_template_json", "observer_reference_json"}


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _facts(row):
    return {key[:-5] if key in _JSON else key: json.loads(value) if key in _JSON and value is not None else value
            for key, value in row.items() if key not in {"binding_fingerprint", "confirmed_at_us"}}


def _hash(kind, facts):
    return hashlib.sha256(_canonical({"kind": kind, "facts": facts})).hexdigest()


def _preflight(bind):
    inspector = sa.inspect(bind)
    if bind.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
        raise RuntimeError("ownership migration requires valid historical foreign keys")
    prepared = {}
    for table, kind in _KINDS.items():
        columns = {item["name"] for item in inspector.get_columns(table)}
        if not {"test_identity_id", "identity_fingerprint", "binding_fingerprint"} <= columns or "subject_test_identity_id" in columns:
            raise RuntimeError("ownership migration requires the exact prior identity structure")
        prepared[table] = []
        for row in bind.execute(sa.text(f'SELECT * FROM "{table}"')).mappings():
            original = dict(row)
            if table == "action_resource_bindings" and original["owner_test_identity_id"] != original["test_identity_id"]:
                raise RuntimeError("historical resource ownership violates the published invariant")
            facts = _facts(original)
            # 历史可空模板字段属于模型默认值，也必须参加旧 hash 检查。
            if table == "action_evidence_bindings":
                facts.setdefault("observer_reference", None)
            if _hash(kind, facts) != original["binding_fingerprint"]:
                raise RuntimeError("historical binding fingerprint is invalid")
            subject = facts.pop("test_identity_id")
            fingerprint = facts.pop("identity_fingerprint")
            facts.pop("owner_test_identity_id", None)
            facts.update(subject_test_identity_id=subject, subject_identity_fingerprint=fingerprint,
                         resource_owner_test_identity_id=subject, owner_identity_fingerprint=fingerprint)
            prepared[table].append((original, _hash(kind, facts)))
    if "test_identity_id" not in {item["name"] for item in inspector.get_columns("recordings")}:
        raise RuntimeError("historical recording structure is invalid")
    return prepared


def _foreign_keys(bind, enabled):
    with op.get_context().autocommit_block():
        bind.exec_driver_sql("PRAGMA foreign_keys=" + ("ON" if enabled else "OFF"))


def upgrade():
    bind = op.get_bind()
    prepared = _preflight(bind)
    # 重建被 Job/Draft 引用的父表需要暂时关闭 FK；显式事务保证本次表变更一起回滚。
    _foreign_keys(bind, False)
    bind.exec_driver_sql("BEGIN IMMEDIATE")
    try:
        with op.batch_alter_table("recordings", recreate="always") as batch:
            batch.alter_column("test_identity_id", new_column_name="subject_test_identity_id")
            batch.add_column(sa.Column("resource_owner_test_identity_id", sa.String(36), nullable=True))
        bind.exec_driver_sql("UPDATE recordings SET resource_owner_test_identity_id=subject_test_identity_id")
        with op.batch_alter_table("recordings", recreate="always") as batch:
            batch.alter_column("resource_owner_test_identity_id", existing_type=sa.String(36), nullable=False)
        for table in _KINDS:
            with op.batch_alter_table(table, recreate="always") as batch:
                batch.alter_column("test_identity_id", new_column_name="subject_test_identity_id")
                batch.alter_column("identity_fingerprint", new_column_name="subject_identity_fingerprint")
                if table == "action_resource_bindings":
                    batch.drop_constraint(op.f("ck_action_resource_bindings_owner_identity_match"), type_="check")
                    batch.alter_column("owner_test_identity_id", new_column_name="resource_owner_test_identity_id")
                else:
                    batch.add_column(sa.Column("resource_owner_test_identity_id", sa.String(36), nullable=True))
                batch.add_column(sa.Column("owner_identity_fingerprint", sa.String(64), nullable=True))
            bind.exec_driver_sql(f'UPDATE "{table}" SET resource_owner_test_identity_id=subject_test_identity_id, owner_identity_fingerprint=subject_identity_fingerprint')
            for original, digest in prepared[table]:
                keys = ["business_action_id", "action_revision"]
                if table == "action_resource_bindings":
                    keys.append("resource_owner_test_identity_id")
                    original["resource_owner_test_identity_id"] = original["test_identity_id"]
                if table == "action_evidence_bindings":
                    keys.append("effect_id")
                where = " AND ".join(f'"{key}"=:{key}' for key in keys)
                bind.execute(sa.text(f'UPDATE "{table}" SET binding_fingerprint=:digest WHERE {where}'),
                             {**{key: original[key] for key in keys}, "digest": digest})
            with op.batch_alter_table(table, recreate="always") as batch:
                batch.alter_column("resource_owner_test_identity_id", existing_type=sa.String(36), nullable=False)
                batch.alter_column("owner_identity_fingerprint", existing_type=sa.String(64), nullable=False)
        _create_selection()
        if bind.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
            raise RuntimeError("ownership migration produced invalid foreign keys")
        bind.exec_driver_sql("COMMIT")
    except BaseException:
        bind.exec_driver_sql("ROLLBACK")
        raise
    finally:
        _foreign_keys(bind, True)


def _create_selection():
    table = "action_allow_control_bindings"
    op.create_table(table,
        sa.Column("project_id", sa.String(64), primary_key=True),
        sa.Column("deny_intent_id", sa.String(36), primary_key=True),
        sa.Column("deny_intent_revision", sa.Integer(), nullable=False),
        sa.Column("deny_intent_hash", sa.String(64), nullable=False),
        sa.Column("selected_allow_intent_id", sa.String(36), nullable=False),
        sa.Column("selected_allow_intent_revision", sa.Integer(), nullable=False),
        sa.Column("selected_allow_intent_hash", sa.String(64), nullable=False),
        sa.Column("selection_fingerprint", sa.String(64), nullable=False),
        sa.Column("confirmed_at_us", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["deny_intent_id", "deny_intent_revision"], ["permission_intent_revisions.intent_id", "permission_intent_revisions.revision"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["selected_allow_intent_id", "selected_allow_intent_revision"], ["permission_intent_revisions.intent_id", "permission_intent_revisions.revision"], ondelete="RESTRICT"),
        sa.CheckConstraint("deny_intent_revision >= 1 AND selected_allow_intent_revision >= 1 AND confirmed_at_us >= 0", name="revision_time_bounds"),
        *(sa.CheckConstraint(f"length({name}) = 64 AND {name} NOT GLOB '*[^0-9a-f]*'", name=f"{name}_format") for name in ("deny_intent_hash", "selected_allow_intent_hash", "selection_fingerprint")),
        *(sa.CheckConstraint(f"length({name}) = 36 AND substr({name}, 1, 4) = 'pin_' AND substr({name}, 5) NOT GLOB '*[^0-9a-f]*'", name=f"{name}_format") for name in ("deny_intent_id", "selected_allow_intent_id")),
    )


def downgrade():
    raise RuntimeError("ownership downgrade cannot preserve the new semantics; restore an explicit backup")
