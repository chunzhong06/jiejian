# 保存人的含义决定和精确批准来源；旧候选与提案关联保留，不补造历史选择。
from __future__ import annotations
import hashlib
import json
import sqlalchemy as sa
from alembic import op

revision = "0013_rule_decisions"
down_revision = "0012_proof_preparation"
branch_labels = None
depends_on = None
_PRIOR_SCHEMA_SHA256 = "7864a85e4b69f2cbe36fc06e5a57be73ee02ece98c8fd44217d0ceb9bbdab510"

def _normalize_sql(statement):
    return " ".join(statement.split())


def _normalize_table_sql(statement):
    # 冻结 0004 的结构比较算法：只忽略反射生成的具名约束排列，不忽略列与约束内容。
    start = statement.find("(")
    if start < 0:
        return _normalize_sql(statement)
    clauses, segment, depth, quote = [], start + 1, 1, None
    index = segment
    while index < len(statement):
        char = statement[index]
        if quote is not None:
            if char == quote:
                if quote != "]" and index + 1 < len(statement) and statement[index + 1] == quote:
                    index += 2
                    continue
                quote = None
        elif char in "'\"`[":
            quote = "]" if char == "[" else char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                clauses.append(_normalize_sql(statement[segment:index]))
                break
        elif char == "," and depth == 1:
            clauses.append(_normalize_sql(statement[segment:index]))
            segment = index + 1
        index += 1
    if depth or quote is not None:
        raise RuntimeError("STATE_PRECONDITION: invalid prior schema")
    constraints = sorted(clause for clause in clauses if clause.startswith("CONSTRAINT "))
    columns = [clause for clause in clauses if not clause.startswith("CONSTRAINT ")]
    return json.dumps((_normalize_sql(statement[:start]), columns, constraints,
        _normalize_sql(statement[index + 1:])), ensure_ascii=False, separators=(",", ":"))

_CREATE_SQL = ('\nCREATE TABLE rule_candidate_decisions (\n\tdecision_id VARCHAR(38) NOT NULL, \n\tproject_id VARCHAR(64) NOT NULL, \n\tcandidate_id VARCHAR(36) NOT NULL, \n\toutput_revision INTEGER NOT NULL, \n\tpayload TEXT NOT NULL, \n\tCONSTRAINT pk_rule_candidate_decisions PRIMARY KEY (decision_id), \n\tCONSTRAINT fk_rule_candidate_decisions_candidate_id_rule_candidate_revisions FOREIGN KEY(candidate_id, output_revision) REFERENCES rule_candidate_revisions (candidate_id, revision) ON DELETE RESTRICT, \n\tCONSTRAINT fk_rule_candidate_decisions_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT\n)\n\n', 'CREATE INDEX ix_rule_candidate_decisions_revision ON rule_candidate_decisions (candidate_id, output_revision)', '\nCREATE TABLE rule_candidate_approval_mappings (\n\tproposal_id VARCHAR(36) NOT NULL, \n\tpermission_item_id VARCHAR(22) NOT NULL, \n\tintent_id VARCHAR(36) NOT NULL, \n\tintent_revision INTEGER NOT NULL, \n\tintent_hash VARCHAR(64) NOT NULL, \n\tboundary_decision_id VARCHAR(36) NOT NULL, \n\treused BOOLEAN NOT NULL, \n\tscenario_decision_ids_json TEXT NOT NULL, \n\tCONSTRAINT pk_rule_candidate_approval_mappings PRIMARY KEY (proposal_id, permission_item_id), \n\tCONSTRAINT fk_rule_candidate_approval_mappings_intent_id_permission_intent_revisions FOREIGN KEY(intent_id, intent_revision) REFERENCES permission_intent_revisions (intent_id, revision) ON DELETE RESTRICT, \n\tCONSTRAINT fk_rule_candidate_approval_mappings_proposal_id_rule_candidate_proposals FOREIGN KEY(proposal_id) REFERENCES rule_candidate_proposals (proposal_id) ON DELETE RESTRICT, \n\tCONSTRAINT fk_rule_candidate_approval_mappings_boundary_decision_id_boundary_proposal_decisions FOREIGN KEY(boundary_decision_id) REFERENCES boundary_proposal_decisions (decision_id) ON DELETE RESTRICT\n)\n\n', 'CREATE INDEX ix_rule_candidate_approval_intent ON rule_candidate_approval_mappings (intent_id, intent_revision)')

def _preflight(bind):
    rows = bind.exec_driver_sql("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE type IN ('table','index','trigger') AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL")
    signature = sorted((kind, name, table, _normalize_table_sql(sql) if kind == "table" else _normalize_sql(sql)) for kind, name, table, sql in rows)
    digest = hashlib.sha256(json.dumps(signature, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    if digest != _PRIOR_SCHEMA_SHA256 or bind.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
        raise RuntimeError("STATE_PRECONDITION: exact valid 0012 structure required")


def upgrade():
    bind = op.get_bind()
    _preflight(bind)
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql("BEGIN IMMEDIATE")
    bind.exec_driver_sql("SAVEPOINT rule_decisions")
    try:
        _preflight(bind)
        bind.exec_driver_sql("PRAGMA defer_foreign_keys=ON")
        with op.batch_alter_table("rule_candidate_proposals", recreate="always") as batch:
            batch.add_column(sa.Column("candidate_content_hash", sa.String(64), nullable=True))
            batch.add_column(sa.Column("decision_set_digest", sa.String(64), nullable=True))
            batch.create_check_constraint(op.f("ck_rule_candidate_proposals_source_hashes_paired"),
                "(candidate_content_hash IS NULL) = (decision_set_digest IS NULL)")
        with op.batch_alter_table("rule_candidate_receipts", recreate="always") as batch:
            batch.drop_constraint(op.f("ck_rule_candidate_receipts_operation_kind_value"), type_="check")
            batch.create_check_constraint(op.f("ck_rule_candidate_receipts_operation_kind_value"),
                "operation_kind IN ('SAVE','PROPOSE','DECIDE')")
        for statement in _CREATE_SQL:
            bind.exec_driver_sql(statement)
        if bind.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
            raise RuntimeError("STATE_PRECONDITION: invalid candidate decision references")
        bind.exec_driver_sql("PRAGMA defer_foreign_keys=OFF")
        bind.exec_driver_sql("RELEASE SAVEPOINT rule_decisions")
    except BaseException:
        bind.exec_driver_sql("ROLLBACK TO SAVEPOINT rule_decisions")
        bind.exec_driver_sql("RELEASE SAVEPOINT rule_decisions")
        bind.exec_driver_sql("PRAGMA defer_foreign_keys=OFF")
        raise


def downgrade():
    raise RuntimeError("STATE_PRECONDITION: candidate decision downgrade requires an explicit backup")
