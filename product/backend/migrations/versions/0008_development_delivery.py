# 追加开发任务、冻结上下文、交付及操作回执，保留已有项目和历史事实。
from __future__ import annotations
import hashlib
import json
from alembic import op

revision = "0008_development_delivery"
down_revision = "0007_preparation_recovery"
branch_labels = None
depends_on = None

_PRIOR_SCHEMA_SHA256 = '9b09a9beddca2fb810d1f6100f0033176290baf386cb270343afc7528e097d89'

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



_CREATE_SQL = (
    'CREATE TABLE development_receipts (\n\tproject_id VARCHAR(64) NOT NULL, \n\tkind VARCHAR(16) NOT NULL, \n\toperation_id VARCHAR(32) NOT NULL, \n\tpayload TEXT NOT NULL, \n\tCONSTRAINT pk_development_receipts PRIMARY KEY (project_id, kind, operation_id), \n\tCONSTRAINT fk_development_receipts_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT\n)',
    "CREATE TABLE development_tasks (\n\ttask_id VARCHAR(36) NOT NULL, \n\tproject_id VARCHAR(64) NOT NULL, \n\tstatus VARCHAR(16) NOT NULL, \n\tversion INTEGER NOT NULL, \n\trevision INTEGER NOT NULL, \n\tcreated_at_us BIGINT NOT NULL, \n\tpayload TEXT NOT NULL, \n\tCONSTRAINT pk_development_tasks PRIMARY KEY (task_id), \n\tCONSTRAINT ck_development_tasks_revisions CHECK (version >= 1 AND revision >= 1), \n\tCONSTRAINT ck_development_tasks_status CHECK (status IN ('ACTIVE','CLOSED','CANCELLED')), \n\tCONSTRAINT fk_development_tasks_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT\n)",
    'CREATE TABLE development_contexts (\n\tcontext_id VARCHAR(36) NOT NULL, \n\ttask_id VARCHAR(36) NOT NULL, \n\trevision INTEGER NOT NULL, \n\tpayload TEXT NOT NULL, \n\tCONSTRAINT pk_development_contexts PRIMARY KEY (context_id), \n\tCONSTRAINT uq_development_contexts_task_id UNIQUE (task_id, revision), \n\tCONSTRAINT ck_development_contexts_revision CHECK (revision >= 1), \n\tCONSTRAINT fk_development_contexts_task_id_development_tasks FOREIGN KEY(task_id) REFERENCES development_tasks (task_id) ON DELETE RESTRICT\n)',
    'CREATE TABLE development_acceptances (\n\tcontext_id VARCHAR(36) NOT NULL, \n\tpayload TEXT NOT NULL, \n\tCONSTRAINT pk_development_acceptances PRIMARY KEY (context_id), \n\tCONSTRAINT fk_development_acceptances_context_id_development_contexts FOREIGN KEY(context_id) REFERENCES development_contexts (context_id) ON DELETE RESTRICT\n)',
    'CREATE TABLE development_deliveries (\n\tdelivery_id VARCHAR(36) NOT NULL, \n\ttask_id VARCHAR(36) NOT NULL, \n\tcontext_id VARCHAR(36) NOT NULL, \n\tchange_id VARCHAR(36) NOT NULL, \n\tordinal INTEGER NOT NULL, \n\tpayload TEXT NOT NULL, \n\tCONSTRAINT pk_development_deliveries PRIMARY KEY (delivery_id), \n\tCONSTRAINT uq_development_deliveries_task_id UNIQUE (task_id, ordinal), \n\tCONSTRAINT ck_development_deliveries_ordinal CHECK (ordinal >= 1), \n\tCONSTRAINT fk_development_deliveries_task_id_development_tasks FOREIGN KEY(task_id) REFERENCES development_tasks (task_id) ON DELETE RESTRICT, \n\tCONSTRAINT fk_development_deliveries_context_id_development_contexts FOREIGN KEY(context_id) REFERENCES development_contexts (context_id) ON DELETE RESTRICT, \n\tCONSTRAINT uq_development_deliveries_change_id UNIQUE (change_id), \n\tCONSTRAINT fk_development_deliveries_change_id_change_manifests FOREIGN KEY(change_id) REFERENCES change_manifests (change_id) ON DELETE RESTRICT\n)',
    "CREATE UNIQUE INDEX uq_development_active_project ON development_tasks (project_id) WHERE status = 'ACTIVE'",
)

def _preflight(bind):
    rows = bind.exec_driver_sql("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE type IN ('table','index','trigger') AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL")
    signature = sorted((kind, name, table, _normalize_table_sql(sql) if kind == "table" else _normalize_sql(sql)) for kind, name, table, sql in rows)
    digest = hashlib.sha256(json.dumps(signature, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    if digest != _PRIOR_SCHEMA_SHA256 or bind.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
        raise RuntimeError("STATE_PRECONDITION: exact valid 0007 structure required")


def upgrade():
    bind = op.get_bind()
    _preflight(bind)
    # SQLite legacy transaction mode 不会为 DDL 自动 BEGIN；显式开启后让 Alembic
    # 在同一事务内更新 revision。局部失败回滚新增表，不碰历史业务行。
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql("BEGIN IMMEDIATE")
    bind.exec_driver_sql("SAVEPOINT development_delivery")
    try:
        _preflight(bind)
        for statement in _CREATE_SQL:
            bind.exec_driver_sql(statement)
        if bind.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
            raise RuntimeError("STATE_PRECONDITION: invalid development foreign keys")
        bind.exec_driver_sql("RELEASE SAVEPOINT development_delivery")
    except BaseException:
        bind.exec_driver_sql("ROLLBACK TO SAVEPOINT development_delivery")
        bind.exec_driver_sql("RELEASE SAVEPOINT development_delivery")
        raise


def downgrade():
    raise RuntimeError("STATE_PRECONDITION: development downgrade requires an explicit backup")
