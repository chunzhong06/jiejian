# 保存五类材料建议和回执，并保留批准时的精确实体引用；既有建议之外的材料事实保持原位。
from __future__ import annotations
import hashlib
import json
import sqlalchemy as sa
from alembic import op

revision = "0014_preparation_suggestions"
down_revision = "0013_rule_decisions"
branch_labels = None
depends_on = None
_PRIOR_SCHEMA_SHA256 = "6c97ee74a71d07332a09d476809b41a05edd349c096aef64112591c434ffddcc"

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

_CREATE_SQL = ('\nCREATE TABLE preparation_suggestions (\n\tsuggestion_id VARCHAR(36) NOT NULL, \n\tproject_id VARCHAR(64) NOT NULL, \n\trevision INTEGER NOT NULL, \n\tcreated_at_us BIGINT NOT NULL, \n\tupdated_at_us BIGINT NOT NULL, \n\tCONSTRAINT pk_preparation_suggestions PRIMARY KEY (suggestion_id), \n\tCONSTRAINT ck_preparation_suggestions_revision_positive CHECK (revision >= 1), \n\tCONSTRAINT fk_preparation_suggestions_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT\n)\n\n', '\nCREATE TABLE preparation_suggestion_revisions (\n\tsuggestion_id VARCHAR(36) NOT NULL, \n\trevision INTEGER NOT NULL, \n\tpayload TEXT NOT NULL, \n\tCONSTRAINT pk_preparation_suggestion_revisions PRIMARY KEY (suggestion_id, revision), \n\tCONSTRAINT ck_preparation_suggestion_revisions_revision_positive CHECK (revision >= 1), \n\tCONSTRAINT fk_preparation_suggestion_revisions_suggestion_id_preparation_suggestions FOREIGN KEY(suggestion_id) REFERENCES preparation_suggestions (suggestion_id) ON DELETE RESTRICT\n)\n\n', '\nCREATE TABLE preparation_suggestion_receipts (\n\tproject_id VARCHAR(64) NOT NULL, \n\toperation_id VARCHAR(32) NOT NULL, \n\trequest_fingerprint VARCHAR(64) NOT NULL, \n\tsuggestion_id VARCHAR(36) NOT NULL, \n\trevision INTEGER NOT NULL, \n\tCONSTRAINT pk_preparation_suggestion_receipts PRIMARY KEY (project_id, operation_id), \n\tCONSTRAINT fk_preparation_suggestion_receipts_suggestion_id_preparation_suggestion_revisions FOREIGN KEY(suggestion_id, revision) REFERENCES preparation_suggestion_revisions (suggestion_id, revision) ON DELETE RESTRICT, \n\tCONSTRAINT fk_preparation_suggestion_receipts_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT\n)\n\n')

def _preflight(bind):
    rows = bind.exec_driver_sql("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE type IN ('table','index','trigger') AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL")
    signature = sorted((kind, name, table, _normalize_table_sql(sql) if kind == "table" else _normalize_sql(sql)) for kind, name, table, sql in rows)
    digest = hashlib.sha256(json.dumps(signature, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    if digest != _PRIOR_SCHEMA_SHA256 or bind.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
        raise RuntimeError("STATE_PRECONDITION: exact valid 0013 structure required")


def upgrade():
    bind = op.get_bind()
    _preflight(bind)
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql("BEGIN IMMEDIATE")
    bind.exec_driver_sql("SAVEPOINT preparation_suggestions")
    try:
        _preflight(bind)
        for statement in _CREATE_SQL:
            bind.exec_driver_sql(statement)
        # 旧批准没有这份映射时保持NULL，不能凭名字猜对应的业务结果。
        op.add_column("rule_candidate_approval_mappings", sa.Column("entity_references_json", sa.Text(), nullable=True))
        if bind.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
            raise RuntimeError("STATE_PRECONDITION: invalid preparation suggestion references")
        bind.exec_driver_sql("RELEASE SAVEPOINT preparation_suggestions")
    except BaseException:
        bind.exec_driver_sql("ROLLBACK TO SAVEPOINT preparation_suggestions")
        bind.exec_driver_sql("RELEASE SAVEPOINT preparation_suggestions")
        raise


def downgrade():
    raise RuntimeError("STATE_PRECONDITION: preparation suggestion downgrade requires an explicit backup")
