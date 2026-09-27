# 追加材料回执、有限草稿与示例所有权；严格保留既有 0006 的业务和执行事实。
from __future__ import annotations
import hashlib
import json
from alembic import op

revision = "0007_preparation_recovery"
down_revision = "0006_product_provenance"
branch_labels = None
depends_on = None

_PRIOR_SCHEMA_SHA256 = 'fd538ed558d0572a3c8ce3e4c7adabd0a5a40f41a4fe4d078af6593518c05b90'

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
    """CREATE TABLE preparation_receipts (
	operation_id VARCHAR(32) NOT NULL,
	project_id VARCHAR(64) NOT NULL,
	request_fingerprint VARCHAR(64) NOT NULL,
	created_at_us BIGINT NOT NULL,
	payload TEXT NOT NULL,
	CONSTRAINT pk_preparation_receipts PRIMARY KEY (operation_id),
	CONSTRAINT fk_preparation_receipts_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT
)""",
    """CREATE TABLE preparation_drafts (
	project_id VARCHAR(64) NOT NULL,
	revision BIGINT NOT NULL,
	payload TEXT NOT NULL,
	CONSTRAINT pk_preparation_drafts PRIMARY KEY (project_id),
	CONSTRAINT ck_preparation_drafts_revision CHECK (revision >= 1),
	CONSTRAINT fk_preparation_drafts_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT
)""",
    """CREATE TABLE sample_workspaces (
	workspace_id VARCHAR(36) NOT NULL,
	project_id VARCHAR(64),
	source_root TEXT NOT NULL,
	scenario_version VARCHAR(24) NOT NULL,
	created_at_us BIGINT NOT NULL,
	CONSTRAINT pk_sample_workspaces PRIMARY KEY (workspace_id),
	CONSTRAINT fk_sample_workspaces_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT
)""",
    """CREATE TABLE sample_instances (
	instance_id VARCHAR(36) NOT NULL,
	workspace_id VARCHAR(36) NOT NULL,
	kernel_identity TEXT NOT NULL,
	created_at_us BIGINT NOT NULL,
	CONSTRAINT pk_sample_instances PRIMARY KEY (instance_id),
	CONSTRAINT fk_sample_instances_workspace_id_sample_workspaces FOREIGN KEY(workspace_id) REFERENCES sample_workspaces (workspace_id) ON DELETE RESTRICT
)""",
    """CREATE TABLE sample_reconciliations (
	reconciliation_id VARCHAR(32) NOT NULL,
	instance_id VARCHAR(36) NOT NULL,
	observed_at_us BIGINT NOT NULL,
	outcome VARCHAR(24) NOT NULL,
	CONSTRAINT pk_sample_reconciliations PRIMARY KEY (reconciliation_id),
	CONSTRAINT fk_sample_reconciliations_instance_id_sample_instances FOREIGN KEY(instance_id) REFERENCES sample_instances (instance_id) ON DELETE RESTRICT
)""",
    """CREATE TABLE preparation_candidate_recordings (
	recording_id VARCHAR(36) NOT NULL,
	CONSTRAINT pk_preparation_candidate_recordings PRIMARY KEY (recording_id),
	CONSTRAINT fk_preparation_candidate_recordings_recording_id_recordings FOREIGN KEY(recording_id) REFERENCES recordings (recording_id) ON DELETE RESTRICT
)""",
)

def _preflight(bind):
    rows = bind.exec_driver_sql("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE type IN ('table','index','trigger') AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL")
    signature = sorted((kind, name, table, _normalize_table_sql(sql) if kind == "table" else _normalize_sql(sql)) for kind, name, table, sql in rows)
    digest = hashlib.sha256(json.dumps(signature, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    if digest != _PRIOR_SCHEMA_SHA256 or bind.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
        raise RuntimeError("STATE_PRECONDITION: exact valid 0006 structure required")


def upgrade():
    bind = op.get_bind()
    _preflight(bind)
    # SQLite legacy transaction mode 不会为 DDL 自动 BEGIN；显式开启后让 Alembic
    # 在同一事务内更新 revision。局部失败回滚新增表，不碰历史业务行。
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql("BEGIN IMMEDIATE")
    bind.exec_driver_sql("SAVEPOINT preparation_recovery")
    try:
        _preflight(bind)
        for statement in _CREATE_SQL:
            bind.exec_driver_sql(statement)
        if bind.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
            raise RuntimeError("STATE_PRECONDITION: invalid provenance foreign keys")
        bind.exec_driver_sql("RELEASE SAVEPOINT preparation_recovery")
    except BaseException:
        bind.exec_driver_sql("ROLLBACK TO SAVEPOINT preparation_recovery")
        bind.exec_driver_sql("RELEASE SAVEPOINT preparation_recovery")
        raise


def downgrade():
    raise RuntimeError("STATE_PRECONDITION: provenance downgrade requires an explicit backup")
