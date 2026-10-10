# 明确区分旧Python示例与受控Node示例的工作空间归属；旧记录保留原运行种类。
import hashlib
import json
from alembic import op

revision="0018_node_sample"
down_revision="0017_rule_history"
branch_labels=None
depends_on=None
_PRIOR_SCHEMA_SHA256='9e4812415ff5ea71c6ddc62f5d69774ca12d10b951e1c81960ae76e4f2698a0b'
_CREATE_SQL=("ALTER TABLE sample_workspaces ADD COLUMN runtime_kind VARCHAR(16) DEFAULT 'PYTHON' NOT NULL",)


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

def _preflight(bind):
    rows = bind.exec_driver_sql("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE type IN ('table','index','trigger') AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL")
    signature = sorted((kind, name, table, _normalize_table_sql(sql) if kind == "table" else _normalize_sql(sql)) for kind, name, table, sql in rows)
    digest = hashlib.sha256(json.dumps(signature, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    if digest != _PRIOR_SCHEMA_SHA256 or bind.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
        raise RuntimeError("STATE_PRECONDITION: exact valid 0017 structure required")


def upgrade():
    bind=op.get_bind();_preflight(bind)
    if not bind.connection.driver_connection.in_transaction:bind.exec_driver_sql('BEGIN IMMEDIATE')
    bind.exec_driver_sql('SAVEPOINT node_sample')
    try:
        _preflight(bind)
        for statement in _CREATE_SQL:bind.exec_driver_sql(statement)
        if bind.exec_driver_sql('PRAGMA foreign_key_check').first() is not None:raise RuntimeError('STATE_PRECONDITION: invalid node sample relations')
        bind.exec_driver_sql('RELEASE SAVEPOINT node_sample')
    except BaseException:
        bind.exec_driver_sql('ROLLBACK TO SAVEPOINT node_sample');bind.exec_driver_sql('RELEASE SAVEPOINT node_sample');raise


def downgrade():
    raise RuntimeError('STATE_PRECONDITION: node sample downgrade requires an explicit backup')
