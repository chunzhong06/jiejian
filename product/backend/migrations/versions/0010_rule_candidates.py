# 追加规则候选、不可变修订、提案关联和幂等回执；保留既有正式权限与历史。
from __future__ import annotations
import hashlib
import json
from alembic import op

revision = "0010_rule_candidates"
down_revision = "0009_delivery_check_links"
branch_labels = None
depends_on = None

_PRIOR_SCHEMA_SHA256 = '3b4acae798747f1c1fd7af0355eee66556f4ca4cc0788ca5d724888f0ff63f5b'

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



_CREATE_SQL = ('\nCREATE TABLE rule_candidates (\n\tcandidate_id VARCHAR(36) NOT NULL, \n\tproject_id VARCHAR(64) NOT NULL, \n\trevision INTEGER NOT NULL, \n\tcreated_at_us BIGINT NOT NULL, \n\tCONSTRAINT pk_rule_candidates PRIMARY KEY (candidate_id), \n\tCONSTRAINT ck_rule_candidates_revision_positive CHECK (revision >= 1), \n\tCONSTRAINT fk_rule_candidates_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT\n)\n\n', '\nCREATE TABLE rule_candidate_revisions (\n\tcandidate_id VARCHAR(36) NOT NULL, \n\trevision INTEGER NOT NULL, \n\tpayload TEXT NOT NULL, \n\tCONSTRAINT pk_rule_candidate_revisions PRIMARY KEY (candidate_id, revision), \n\tCONSTRAINT ck_rule_candidate_revisions_revision_positive CHECK (revision >= 1), \n\tCONSTRAINT fk_rule_candidate_revisions_candidate_id_rule_candidates FOREIGN KEY(candidate_id) REFERENCES rule_candidates (candidate_id) ON DELETE RESTRICT\n)\n\n', '\nCREATE TABLE rule_candidate_proposals (\n\tcandidate_id VARCHAR(36) NOT NULL, \n\trevision INTEGER NOT NULL, \n\tproposal_id VARCHAR(36) NOT NULL, \n\tCONSTRAINT pk_rule_candidate_proposals PRIMARY KEY (candidate_id, revision), \n\tCONSTRAINT fk_rule_candidate_proposals_candidate_id_rule_candidate_revisions FOREIGN KEY(candidate_id, revision) REFERENCES rule_candidate_revisions (candidate_id, revision) ON DELETE RESTRICT, \n\tCONSTRAINT uq_rule_candidate_proposals_proposal_id UNIQUE (proposal_id), \n\tCONSTRAINT fk_rule_candidate_proposals_proposal_id_boundary_proposals FOREIGN KEY(proposal_id) REFERENCES boundary_proposals (proposal_id) ON DELETE RESTRICT\n)\n\n', "\nCREATE TABLE rule_candidate_receipts (\n\tproject_id VARCHAR(64) NOT NULL, \n\toperation_kind VARCHAR(16) NOT NULL, \n\toperation_id VARCHAR(32) NOT NULL, \n\trequest_fingerprint VARCHAR(64) NOT NULL, \n\tcandidate_id VARCHAR(36) NOT NULL, \n\trevision INTEGER NOT NULL, \n\tCONSTRAINT pk_rule_candidate_receipts PRIMARY KEY (project_id, operation_kind, operation_id), \n\tCONSTRAINT ck_rule_candidate_receipts_operation_kind_value CHECK (operation_kind IN ('SAVE','PROPOSE')), \n\tCONSTRAINT fk_rule_candidate_receipts_candidate_id_rule_candidate_revisions FOREIGN KEY(candidate_id, revision) REFERENCES rule_candidate_revisions (candidate_id, revision) ON DELETE RESTRICT, \n\tCONSTRAINT fk_rule_candidate_receipts_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT\n)\n\n")

def _preflight(bind):
    rows = bind.exec_driver_sql("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE type IN ('table','index','trigger') AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL")
    signature = sorted((kind, name, table, _normalize_table_sql(sql) if kind == "table" else _normalize_sql(sql)) for kind, name, table, sql in rows)
    digest = hashlib.sha256(json.dumps(signature, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    if digest != _PRIOR_SCHEMA_SHA256 or bind.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
        raise RuntimeError("STATE_PRECONDITION: exact valid 0009 structure required")


def upgrade():
    bind = op.get_bind()
    _preflight(bind)
    # SQLite legacy transaction mode 不会为 DDL 自动 BEGIN；显式开启后让 Alembic
    # 在同一事务内更新 revision。局部失败回滚新增表，不碰历史业务行。
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql("BEGIN IMMEDIATE")
    bind.exec_driver_sql("SAVEPOINT rule_candidates")
    try:
        _preflight(bind)
        for statement in _CREATE_SQL:
            bind.exec_driver_sql(statement)
        if bind.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
            raise RuntimeError("STATE_PRECONDITION: invalid rule candidate foreign keys")
        bind.exec_driver_sql("RELEASE SAVEPOINT rule_candidates")
    except BaseException:
        bind.exec_driver_sql("ROLLBACK TO SAVEPOINT rule_candidates")
        bind.exec_driver_sql("RELEASE SAVEPOINT rule_candidates")
        raise


def downgrade():
    raise RuntimeError("STATE_PRECONDITION: rule candidate downgrade requires an explicit backup")
