# 把 1.0.3 当前值权限单元迁移为不可变 Ledger revision、epoch 与实现绑定。

from __future__ import annotations

import hashlib
import json

from alembic import op
import sqlalchemy as sa


revision = "0003_permission_intent_ledger"
down_revision = "0002_remove_contract_workbench"
branch_labels = None
depends_on = None


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _setup_fingerprints(bind) -> dict[tuple[str, str], tuple[str, dict[str, object]]]:
    rows = bind.execute(
        sa.text(
            "SELECT r.project_id, r.action_candidate_id, r.resource_id, r.logical_name, "
            "r.resource_type, r.fingerprint AS resource_fingerprint, "
            "o.fingerprint AS observation_fingerprint, "
            "c.fingerprint AS recovery_fingerprint, e.kind AS effect_kind, "
            "e.protected_fields, e.fingerprint AS effect_fingerprint "
            "FROM test_resources r "
            "LEFT JOIN observation_bindings o ON o.resource_id = r.resource_id "
            "LEFT JOIN recovery_bindings c ON c.resource_id = r.resource_id "
            "LEFT JOIN security_effect_confirmations e ON e.resource_id = r.resource_id"
        )
    ).mappings()
    result: dict[tuple[str, str], tuple[str, dict[str, object]]] = {}
    for row in rows:
        fingerprint = _sha256(
            {
                "resource": row["resource_fingerprint"],
                "observation": row["observation_fingerprint"],
                "recovery": row["recovery_fingerprint"],
                "effect": row["effect_fingerprint"],
            }
        )
        effect: dict[str, object] = {}
        if row["effect_kind"] is not None:
            effect = {
                "kind": row["effect_kind"],
                "resource_type": row["resource_type"],
                "business_label": row["logical_name"],
                "protected_fields": json.loads(row["protected_fields"]),
            }
        result[(row["project_id"], row["action_candidate_id"])] = (fingerprint, effect)
    return result


def upgrade() -> None:
    op.create_table(
        "permission_intent_revisions",
        sa.Column("intent_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("effective_state", sa.String(length=16), nullable=False),
        sa.Column("subject_display_name", sa.String(length=128), nullable=False),
        sa.Column("action_display_name", sa.String(length=256), nullable=False),
        sa.Column("resource_owner_display_name", sa.String(length=128), nullable=False),
        sa.Column("relation", sa.String(length=32), nullable=False),
        sa.Column("expectation", sa.String(length=8), nullable=False),
        sa.Column("protected_effects_json", sa.Text(), nullable=False),
        sa.Column("intent_hash", sa.String(length=64), nullable=False),
        sa.Column("policy_epoch", sa.Integer(), nullable=False),
        sa.Column("approval_json", sa.Text(), nullable=False),
        sa.Column("created_at_us", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("length(intent_id) = 36 AND intent_id GLOB 'pin_[0-9a-f]*'", name=op.f("ck_permission_intent_revisions_intent_id_format")),
        sa.CheckConstraint("revision >= 1", name=op.f("ck_permission_intent_revisions_revision_positive")),
        sa.CheckConstraint("effective_state IN ('ACTIVE', 'RETIRED')", name=op.f("ck_permission_intent_revisions_effective_state_value")),
        sa.CheckConstraint("relation IN ('OWNS', 'SAME_ROLE_OTHER_ACCOUNT', 'OTHER_ROLE')", name=op.f("ck_permission_intent_revisions_relation_value")),
        sa.CheckConstraint("expectation IN ('ALLOW', 'DENY')", name=op.f("ck_permission_intent_revisions_expectation_value")),
        sa.CheckConstraint("policy_epoch >= 1", name=op.f("ck_permission_intent_revisions_policy_epoch_positive")),
        sa.CheckConstraint("created_at_us >= 0", name=op.f("ck_permission_intent_revisions_created_nonnegative")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], name=op.f("fk_permission_intent_revisions_project_id_projects"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("intent_id", "revision", name=op.f("pk_permission_intent_revisions")),
    )
    op.create_index("ix_permission_intent_revisions_project", "permission_intent_revisions", ["project_id", "created_at_us"], unique=False)
    op.create_table(
        "project_policy_states",
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("policy_epoch", sa.Integer(), nullable=False),
        sa.Column("updated_at_us", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("policy_epoch >= 0", name=op.f("ck_project_policy_states_policy_epoch_nonnegative")),
        sa.CheckConstraint("updated_at_us >= 0", name=op.f("ck_project_policy_states_updated_nonnegative")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], name=op.f("fk_project_policy_states_project_id_projects"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id", name=op.f("pk_project_policy_states")),
    )
    op.create_table(
        "intent_implementation_bindings",
        sa.Column("intent_id", sa.String(length=36), nullable=False),
        sa.Column("intent_revision", sa.Integer(), nullable=False),
        sa.Column("action_candidate_id", sa.String(length=39), nullable=False),
        sa.Column("subject_role_candidate_id", sa.String(length=37), nullable=False),
        sa.Column("resource_owner_role_candidate_id", sa.String(length=37), nullable=False),
        sa.Column("understanding_revision", sa.Integer(), nullable=False),
        sa.Column("action_safety_setup_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("binding_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason_codes_json", sa.Text(), nullable=False),
        sa.Column("updated_at_us", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("status IN ('CURRENT', 'NEEDS_REVIEW', 'UNRESOLVED')", name=op.f("ck_intent_implementation_bindings_status_value")),
        sa.CheckConstraint("understanding_revision >= 0", name=op.f("ck_intent_implementation_bindings_understanding_revision_nonnegative")),
        sa.CheckConstraint("updated_at_us >= 0", name=op.f("ck_intent_implementation_bindings_updated_nonnegative")),
        sa.ForeignKeyConstraint(["intent_id", "intent_revision"], ["permission_intent_revisions.intent_id", "permission_intent_revisions.revision"], name=op.f("fk_intent_implementation_bindings_intent_id_permission_intent_revisions"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("intent_id", "intent_revision", name=op.f("pk_intent_implementation_bindings")),
    )
    op.create_index("ix_intent_bindings_action", "intent_implementation_bindings", ["action_candidate_id"], unique=False)
    op.create_table(
        "intent_proposals",
        sa.Column("proposal_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("intent_id", sa.String(length=36), nullable=True),
        sa.Column("semantic_change_json", sa.Text(), nullable=True),
        sa.Column("implementation_rebind_json", sa.Text(), nullable=True),
        sa.Column("proposed_by", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=512), nullable=False),
        sa.Column("created_at_us", sa.BigInteger(), nullable=False),
        sa.Column("decided_at_us", sa.BigInteger(), nullable=True),
        sa.CheckConstraint("kind IN ('SEMANTIC_CHANGE', 'IMPLEMENTATION_REBIND')", name=op.f("ck_intent_proposals_kind_value")),
        sa.CheckConstraint("status IN ('PENDING', 'APPROVED', 'REJECTED')", name=op.f("ck_intent_proposals_status_value")),
        sa.CheckConstraint("created_at_us >= 0 AND (decided_at_us IS NULL OR decided_at_us >= created_at_us)", name=op.f("ck_intent_proposals_time_order")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], name=op.f("fk_intent_proposals_project_id_projects"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("proposal_id", name=op.f("pk_intent_proposals")),
    )
    op.create_index("ix_intent_proposals_project_status", "intent_proposals", ["project_id", "status", "created_at_us"], unique=False)

    bind = op.get_bind()
    understandings: dict[str, tuple[int, dict[str, dict[str, object]], dict[str, dict[str, object]]]] = {}
    for row in bind.execute(sa.text("SELECT project_id, revision, role_candidates_json, action_candidates_json FROM application_understanding")).mappings():
        roles = {item["candidate_id"]: item for item in json.loads(row["role_candidates_json"])}
        actions = {item["candidate_id"]: item for item in json.loads(row["action_candidates_json"])}
        understandings[row["project_id"]] = (row["revision"], roles, actions)
    setups = _setup_fingerprints(bind)
    old_rows = tuple(bind.execute(sa.text("SELECT * FROM permission_intents ORDER BY project_id, intent_id")).mappings())
    project_times: dict[str, int] = {}
    for row in old_rows:
        project_times[row["project_id"]] = max(project_times.get(row["project_id"], 0), row["confirmed_at_us"])
    for project_id, updated_at_us in project_times.items():
        bind.execute(sa.text("INSERT INTO project_policy_states VALUES (:project_id, 1, :updated_at_us)"), {"project_id": project_id, "updated_at_us": updated_at_us})

    for row in old_rows:
        understanding_revision, roles, actions = understandings.get(row["project_id"], (0, {}, {}))
        action = actions.get(row["action_candidate_id"])
        subject = roles.get(row["subject_role_candidate_id"])
        owner = roles.get(row["resource_owner_role_candidate_id"])
        setup = setups.get((row["project_id"], row["action_candidate_id"]))
        setup_fingerprint = None if setup is None else setup[0]
        protected_effects = () if setup is None or not setup[1] else (setup[1],)
        semantic = {
            "effective_state": "ACTIVE",
            "subject_display_name": (subject or {}).get("display_name", "已迁移权限组"),
            "action_display_name": (action or {}).get("display_name", "已迁移业务动作"),
            "resource_owner_display_name": (owner or {}).get("display_name", "已迁移资源所有者权限组"),
            "relation": row["relation"],
            "expectation": row["expectation"],
            "protected_effects": protected_effects,
        }
        intent_hash = _sha256(semantic)
        approval = {
            "channel": "MIGRATED_USER_CONFIRMATION",
            "approved_by": row["confirmed_by"],
            "approved_at_us": row["confirmed_at_us"],
            "reason": "由界鉴 1.0.3 用户确认权限迁移",
        }
        bind.execute(
            sa.text(
                "INSERT INTO permission_intent_revisions VALUES "
                "(:intent_id, 1, :project_id, 'ACTIVE', :subject_name, :action_name, "
                ":owner_name, :relation, :expectation, :effects, :intent_hash, 1, "
                ":approval, :created_at_us)"
            ),
            {
                "intent_id": row["intent_id"],
                "project_id": row["project_id"],
                "subject_name": semantic["subject_display_name"],
                "action_name": semantic["action_display_name"],
                "owner_name": semantic["resource_owner_display_name"],
                "relation": row["relation"],
                "expectation": row["expectation"],
                "effects": _canonical(protected_effects),
                "intent_hash": intent_hash,
                "approval": _canonical(approval),
                "created_at_us": row["confirmed_at_us"],
            },
        )
        reasons = []
        for candidate, reason in (
            (action, "ACTION_CANDIDATE_STALE"),
            (subject, "SUBJECT_ROLE_CANDIDATE_STALE"),
            (owner, "OWNER_ROLE_CANDIDATE_STALE"),
        ):
            if candidate is None or candidate.get("decision") != "CONFIRMED" or candidate.get("stale"):
                reasons.append(reason)
        if setup_fingerprint is None:
            reasons.append("ACTION_SAFETY_SETUP_MISSING")
        binding_payload = {
            "intent_id": row["intent_id"],
            "intent_revision": 1,
            "action_candidate_id": row["action_candidate_id"],
            "subject_role_candidate_id": row["subject_role_candidate_id"],
            "resource_owner_role_candidate_id": row["resource_owner_role_candidate_id"],
            "understanding_revision": understanding_revision,
            "action_safety_setup_fingerprint": setup_fingerprint,
        }
        bind.execute(
            sa.text(
                "INSERT INTO intent_implementation_bindings VALUES "
                "(:intent_id, 1, :action_id, :subject_id, :owner_id, :understanding_revision, "
                ":setup_fingerprint, :binding_fingerprint, :status, :reasons, :updated_at_us)"
            ),
            {
                "intent_id": row["intent_id"],
                "action_id": row["action_candidate_id"],
                "subject_id": row["subject_role_candidate_id"],
                "owner_id": row["resource_owner_role_candidate_id"],
                "understanding_revision": understanding_revision,
                "setup_fingerprint": setup_fingerprint,
                "binding_fingerprint": _sha256(binding_payload),
                "status": "CURRENT" if not reasons else "UNRESOLVED",
                "reasons": _canonical(reasons),
                "updated_at_us": row["updated_at_us"],
            },
        )

    op.drop_index("ix_permission_intents_project_action", table_name="permission_intents")
    op.drop_table("permission_intents")


def downgrade() -> None:
    # Revision/epoch/proposal 不能压扁回 1.0.3 当前值；仅恢复旧结构，不伪造历史。
    op.create_table(
        "permission_intents",
        sa.Column("intent_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("action_candidate_id", sa.String(length=39), nullable=False),
        sa.Column("subject_role_candidate_id", sa.String(length=37), nullable=False),
        sa.Column("resource_owner_role_candidate_id", sa.String(length=37), nullable=False),
        sa.Column("relation", sa.String(length=32), nullable=False),
        sa.Column("expectation", sa.String(length=8), nullable=False),
        sa.Column("confirmation_source", sa.String(length=8), nullable=False),
        sa.Column("confirmed_by", sa.String(length=128), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("confirmed_at_us", sa.BigInteger(), nullable=False),
        sa.Column("created_at_us", sa.BigInteger(), nullable=False),
        sa.Column("updated_at_us", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("expectation IN ('ALLOW', 'DENY') AND confirmation_source = 'USER'", name=op.f("ck_permission_intents_permission_intent_confirmation_value")),
        sa.CheckConstraint("length(intent_id) = 36 AND intent_id GLOB 'pin_[0-9a-f]*'", name=op.f("ck_permission_intents_permission_intent_id_format")),
        sa.CheckConstraint("relation IN ('OWNS', 'SAME_ROLE_OTHER_ACCOUNT', 'OTHER_ROLE')", name=op.f("ck_permission_intents_permission_intent_relation_value")),
        sa.CheckConstraint("created_at_us >= 0 AND confirmed_at_us >= 0 AND updated_at_us >= created_at_us AND confirmed_at_us <= updated_at_us", name=op.f("ck_permission_intents_permission_intent_time_order")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], name=op.f("fk_permission_intents_project_id_projects"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("intent_id", name=op.f("pk_permission_intents")),
        sa.UniqueConstraint("project_id", "action_candidate_id", "subject_role_candidate_id", "resource_owner_role_candidate_id", "relation", name="uq_permission_intent_group_matrix_cell"),
    )
    op.create_index("ix_permission_intents_project_action", "permission_intents", ["project_id", "action_candidate_id"], unique=False)
    op.drop_index("ix_intent_proposals_project_status", table_name="intent_proposals")
    op.drop_table("intent_proposals")
    op.drop_index("ix_intent_bindings_action", table_name="intent_implementation_bindings")
    op.drop_table("intent_implementation_bindings")
    op.drop_table("project_policy_states")
    op.drop_index("ix_permission_intent_revisions_project", table_name="permission_intent_revisions")
    op.drop_table("permission_intent_revisions")
