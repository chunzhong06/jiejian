# 为唯一检查历史增加规则定位、覆盖与操作回执；不回填猜测的历史结论。
import hashlib
import json
from alembic import op

revision="0017_rule_history"
down_revision="0016_capture_recovery"
branch_labels=None
depends_on=None
_PRIOR_SCHEMA_SHA256='2aced556e009393207729b33c22cdc44b1dd4a1e862383f511a88c89ae8e88a6'
_CREATE_SQL=('\nCREATE TABLE rule_check_index (\n\tproject_id VARCHAR(64) NOT NULL, \n\tintent_id VARCHAR(36) NOT NULL, \n\trevision INTEGER NOT NULL, \n\tintent_hash VARCHAR(64) NOT NULL, \n\trun_id VARCHAR(36) NOT NULL, \n\tcase_id VARCHAR(37) NOT NULL, \n\tmanifest_hash VARCHAR(64) NOT NULL, \n\tcreated_at_us BIGINT NOT NULL, \n\tCONSTRAINT pk_rule_check_index PRIMARY KEY (project_id, intent_id, revision, intent_hash, run_id, case_id), \n\tCONSTRAINT ck_rule_check_index_bounds CHECK (revision >= 1 AND created_at_us >= 0), \n\tCONSTRAINT fk_rule_check_index_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT, \n\tCONSTRAINT fk_rule_check_index_run_id_runs FOREIGN KEY(run_id) REFERENCES runs (run_id) ON DELETE RESTRICT\n)\n\n', 'CREATE INDEX ix_rule_check_index_rule ON rule_check_index (project_id, intent_id, revision, intent_hash, created_at_us, run_id)', '\nCREATE TABLE rule_history_runs (\n\trun_id VARCHAR(36) NOT NULL, \n\tmanifest_hash VARCHAR(64) NOT NULL, \n\terror_code VARCHAR(64), \n\tCONSTRAINT pk_rule_history_runs PRIMARY KEY (run_id), \n\tCONSTRAINT fk_rule_history_runs_run_id_runs FOREIGN KEY(run_id) REFERENCES runs (run_id) ON DELETE RESTRICT\n)\n\n', '\nCREATE TABLE rule_history_coverage (\n\tproject_id VARCHAR(64) NOT NULL, \n\tcheckpoint INTEGER NOT NULL, \n\tgeneration INTEGER NOT NULL, \n\tupper_time BIGINT NOT NULL, \n\tupper_run VARCHAR(36) NOT NULL, \n\tcursor_time BIGINT NOT NULL, \n\tcursor_run VARCHAR(36) NOT NULL, \n\tprocessed INTEGER NOT NULL, \n\tfailed INTEGER NOT NULL, \n\tcomplete BOOLEAN NOT NULL, \n\tCONSTRAINT pk_rule_history_coverage PRIMARY KEY (project_id), \n\tCONSTRAINT ck_rule_history_coverage_bounds CHECK (checkpoint >= 0 AND generation >= 0 AND processed >= 0 AND failed >= 0), \n\tCONSTRAINT fk_rule_history_coverage_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT\n)\n\n', '\nCREATE TABLE rule_history_receipts (\n\tproject_id VARCHAR(64) NOT NULL, \n\toperation_id VARCHAR(32) NOT NULL, \n\trequest_hash VARCHAR(64) NOT NULL, \n\tcheckpoint INTEGER NOT NULL, \n\tprocessed INTEGER NOT NULL, \n\tfailed INTEGER NOT NULL, \n\tcomplete BOOLEAN NOT NULL, \n\tCONSTRAINT pk_rule_history_receipts PRIMARY KEY (project_id, operation_id), \n\tCONSTRAINT ck_rule_history_receipts_bounds CHECK (checkpoint >= 1 AND processed >= 0 AND failed >= 0), \n\tCONSTRAINT fk_rule_history_receipts_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT\n)\n\n')

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
        raise RuntimeError("STATE_PRECONDITION: exact valid 0016 structure required")


def upgrade():
    bind=op.get_bind();_preflight(bind)
    if not bind.connection.driver_connection.in_transaction:bind.exec_driver_sql('BEGIN IMMEDIATE')
    bind.exec_driver_sql('SAVEPOINT rule_history')
    try:
        _preflight(bind)
        for statement in _CREATE_SQL:bind.exec_driver_sql(statement)
        if bind.exec_driver_sql('PRAGMA foreign_key_check').first() is not None:raise RuntimeError('STATE_PRECONDITION: invalid rule history relations')
        bind.exec_driver_sql('RELEASE SAVEPOINT rule_history')
    except BaseException:
        bind.exec_driver_sql('ROLLBACK TO SAVEPOINT rule_history');bind.exec_driver_sql('RELEASE SAVEPOINT rule_history');raise


def downgrade():
    raise RuntimeError('STATE_PRECONDITION: rule history downgrade requires an explicit backup')
