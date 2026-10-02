# 追加普通运行加载输入/回执及独立Job目标；重建Job保留所有历史行、事件和发布关联。
from __future__ import annotations
import hashlib
import json
import sqlalchemy as sa
from alembic import op

revision = "0011_runtime_load_jobs"
down_revision = "0010_rule_candidates"
branch_labels = None
depends_on = None
_PRIOR_SCHEMA_SHA256 = "3fcc531c53577d7275c5fca597490aa9ea59de36e7453eb805e534aebce24b0a"

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
_CREATE_SQL = '\nCREATE TABLE runtime_loads (\n\tload_id VARCHAR(36) NOT NULL, \n\tproject_id VARCHAR(64) NOT NULL, \n\toperation_id VARCHAR(32) NOT NULL, \n\trequest_fingerprint VARCHAR(64) NOT NULL, \n\trequest_json TEXT NOT NULL, \n\treceipt_json TEXT, \n\tcreated_at_us BIGINT NOT NULL, \n\tCONSTRAINT pk_runtime_loads PRIMARY KEY (load_id), \n\tCONSTRAINT uq_runtime_load_operation UNIQUE (project_id, operation_id), \n\tCONSTRAINT ck_runtime_loads_time_nonnegative CHECK (created_at_us >= 0), \n\tCONSTRAINT fk_runtime_loads_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT\n)\n\n'


def _preflight(bind):
    rows = bind.exec_driver_sql("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE type IN ('table','index','trigger') AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL")
    signature = sorted((kind, name, table, _normalize_table_sql(sql) if kind == "table" else _normalize_sql(sql)) for kind, name, table, sql in rows)
    digest = hashlib.sha256(json.dumps(signature, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    if digest != _PRIOR_SCHEMA_SHA256 or bind.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
        raise RuntimeError("STATE_PRECONDITION: exact valid 0010 structure required")


def upgrade():
    bind = op.get_bind()
    _preflight(bind)
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql("BEGIN IMMEDIATE")
    bind.exec_driver_sql("SAVEPOINT runtime_load_jobs")
    try:
        _preflight(bind)
        # 只延后外键核对，不关闭约束；避免为父表重建提前提交Alembic版本事务。
        bind.exec_driver_sql("PRAGMA defer_foreign_keys=ON")
        bind.exec_driver_sql(_CREATE_SQL)
        with op.batch_alter_table("jobs", recreate="always") as batch:
            batch.add_column(sa.Column("runtime_load_id", sa.String(36), nullable=True))
            batch.create_foreign_key(op.f("fk_jobs_runtime_load_id_runtime_loads"), "runtime_loads", ["runtime_load_id"], ["load_id"], ondelete="RESTRICT")
            batch.create_unique_constraint(op.f("uq_jobs_runtime_load_id"), ["runtime_load_id"])
            batch.drop_constraint(op.f("ck_jobs_exactly_one_target"), type_="check")
            batch.create_check_constraint(op.f("ck_jobs_exactly_one_target"), "(run_id IS NOT NULL) + (recording_id IS NOT NULL) + (runtime_load_id IS NOT NULL) = 1")
            batch.create_check_constraint(op.f("ck_jobs_runtime_operation_type"), "runtime_load_id IS NULL OR operation_type = 'RUNTIME_LOAD'")
        if bind.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
            raise RuntimeError("STATE_PRECONDITION: invalid runtime load foreign keys")
        # 替换后引用已逐项复核，清除DROP旧父表产生的暂时延期债务；事务保持未提交。
        bind.exec_driver_sql("PRAGMA defer_foreign_keys=OFF")
        bind.exec_driver_sql("RELEASE SAVEPOINT runtime_load_jobs")
    except BaseException:
        bind.exec_driver_sql("ROLLBACK TO SAVEPOINT runtime_load_jobs")
        bind.exec_driver_sql("RELEASE SAVEPOINT runtime_load_jobs")
        bind.exec_driver_sql("PRAGMA defer_foreign_keys=OFF")
        raise


def downgrade():
    raise RuntimeError("STATE_PRECONDITION: runtime load downgrade requires an explicit backup")
