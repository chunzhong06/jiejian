# 追加交付与真实检查的精确关联，不按时间或相同源码推测历史归属。
from __future__ import annotations
import hashlib
import json
from alembic import op

revision = "0009_delivery_check_links"
down_revision = "0008_development_delivery"
branch_labels = None
depends_on = None

_PRIOR_SCHEMA_SHA256 = '4d003bbad0034e68b401b3c75c8171da2d9a1f0e2b0b9cedd1bb15bba8a240eb'

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
    'CREATE TABLE development_check_runs (\n\trun_id VARCHAR(36) NOT NULL, \n\tdelivery_id VARCHAR(36) NOT NULL, \n\tcreated_at_us BIGINT NOT NULL, \n\tCONSTRAINT pk_development_check_runs PRIMARY KEY (run_id), \n\tCONSTRAINT fk_development_check_runs_run_id_runs FOREIGN KEY(run_id) REFERENCES runs (run_id) ON DELETE RESTRICT, \n\tCONSTRAINT fk_development_check_runs_delivery_id_development_deliveries FOREIGN KEY(delivery_id) REFERENCES development_deliveries (delivery_id) ON DELETE RESTRICT\n)',
    'CREATE INDEX ix_development_check_runs_delivery ON development_check_runs (delivery_id, created_at_us)',
)

def _preflight(bind):
    rows = bind.exec_driver_sql("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE type IN ('table','index','trigger') AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL")
    signature = sorted((kind, name, table, _normalize_table_sql(sql) if kind == "table" else _normalize_sql(sql)) for kind, name, table, sql in rows)
    digest = hashlib.sha256(json.dumps(signature, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    if digest != _PRIOR_SCHEMA_SHA256 or bind.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
        raise RuntimeError("STATE_PRECONDITION: exact valid 0008 structure required")


def upgrade():
    bind = op.get_bind()
    _preflight(bind)
    # SQLite legacy transaction mode 不会为 DDL 自动 BEGIN；显式开启后让 Alembic
    # 在同一事务内更新 revision。局部失败回滚新增表，不碰历史业务行。
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql("BEGIN IMMEDIATE")
    bind.exec_driver_sql("SAVEPOINT delivery_check_links")
    try:
        _preflight(bind)
        for statement in _CREATE_SQL:
            bind.exec_driver_sql(statement)
        if bind.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
            raise RuntimeError("STATE_PRECONDITION: invalid development foreign keys")
        bind.exec_driver_sql("RELEASE SAVEPOINT delivery_check_links")
    except BaseException:
        bind.exec_driver_sql("ROLLBACK TO SAVEPOINT delivery_check_links")
        bind.exec_driver_sql("RELEASE SAVEPOINT delivery_check_links")
        raise


def downgrade():
    raise RuntimeError("STATE_PRECONDITION: development downgrade requires an explicit backup")
