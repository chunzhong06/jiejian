# 为已应用的取样存储增加独立恢复报告；保留0015结构及已有记录。
from __future__ import annotations
import hashlib
import json
import sqlalchemy as sa
from alembic import op

revision = "0016_capture_recovery"
down_revision = "0015_reference_capture"
branch_labels = None
depends_on = None
_PRIOR_SCHEMA_SHA256 = "364bb129ce3656f262dfa4f2423a3f5db69ae13d2bb0dcd990f3507d35a46ce6"

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
        raise RuntimeError("STATE_PRECONDITION: exact valid 0015 structure required")


def upgrade():
    bind=op.get_bind()
    _preflight(bind)
    if not bind.connection.driver_connection.in_transaction:bind.exec_driver_sql("BEGIN IMMEDIATE")
    bind.exec_driver_sql("SAVEPOINT capture_recovery")
    try:
        _preflight(bind)
        bind.exec_driver_sql("PRAGMA defer_foreign_keys=ON")
        with op.batch_alter_table("reference_captures",recreate="always") as batch:
            batch.alter_column("asset_id",existing_type=sa.String(36),nullable=True)
            batch.add_column(sa.Column("recovery_report_sha256",sa.String(64),nullable=True))
        if bind.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
            raise RuntimeError("STATE_PRECONDITION: invalid capture recovery relations")
        bind.exec_driver_sql("PRAGMA defer_foreign_keys=OFF")
        bind.exec_driver_sql("RELEASE SAVEPOINT capture_recovery")
    except BaseException:
        bind.exec_driver_sql("ROLLBACK TO SAVEPOINT capture_recovery")
        bind.exec_driver_sql("RELEASE SAVEPOINT capture_recovery")
        bind.exec_driver_sql("PRAGMA defer_foreign_keys=OFF")
        raise


def downgrade():
    raise RuntimeError("STATE_PRECONDITION: capture recovery downgrade requires an explicit backup")
