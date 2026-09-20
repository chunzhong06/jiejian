# 增量追加材料修订、代码观察和环境回执；精确校验旧 0005，不改写任何历史事实。
from __future__ import annotations
import hashlib
import json
from alembic import op

revision = "0006_product_provenance"
down_revision = "0005_verification_loop_v3"
branch_labels = None
depends_on = None

_PRIOR_SCHEMA_SHA256 = 'ea29077e398cbe5be0143e489234fa55f670668a76219a1d95f32e538d114ed2'

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
    """CREATE TABLE code_observations (
	observation_id VARCHAR(36) NOT NULL,
	project_id VARCHAR(64) NOT NULL,
	source_fingerprint VARCHAR(64) NOT NULL,
	observed_at_us BIGINT NOT NULL,
	git_status VARCHAR(32) NOT NULL,
	head VARCHAR(64),
	has_local_changes BOOLEAN,
	consistency VARCHAR(16) NOT NULL,
	scope VARCHAR(32) NOT NULL,
	CONSTRAINT pk_code_observations PRIMARY KEY (observation_id),
	CONSTRAINT ck_code_observations_identity_bound CHECK (length(source_fingerprint) = 64 AND observed_at_us >= 0),
	CONSTRAINT ck_code_observations_git_status CHECK (git_status IN ('AVAILABLE','UNBORN','NOT_A_REPOSITORY','UNAVAILABLE')),
	CONSTRAINT ck_code_observations_scope CHECK (consistency IN ('CONSISTENT','UNAVAILABLE') AND scope = 'AUTHORIZED_SOURCE_SCAN'),
	CONSTRAINT ck_code_observations_head_length CHECK (head IS NULL OR length(head) IN (40,64)),
	CONSTRAINT ck_code_observations_unknown_identity CHECK (consistency != 'UNAVAILABLE' OR (git_status = 'UNAVAILABLE' AND head IS NULL AND has_local_changes IS NULL)),
	CONSTRAINT fk_code_observations_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT
)""",
    """CREATE TABLE environment_operations (
	operation_id VARCHAR(36) NOT NULL,
	operation VARCHAR(8) NOT NULL,
	state VARCHAR(16) NOT NULL,
	started_at_us BIGINT NOT NULL,
	finished_at_us BIGINT,
	experience_id VARCHAR(36),
	project_id VARCHAR(64),
	error_code VARCHAR(64),
	cleanup_confirmed BOOLEAN NOT NULL,
	CONSTRAINT pk_environment_operations PRIMARY KEY (operation_id),
	CONSTRAINT ck_environment_operations_operation CHECK (operation IN ('start','reset','stop')),
	CONSTRAINT ck_environment_operations_state CHECK (state IN ('PENDING','SUCCEEDED','FAILED','UNKNOWN')),
	CONSTRAINT ck_environment_operations_time_order CHECK (started_at_us >= 0 AND (finished_at_us IS NULL OR finished_at_us >= started_at_us)),
	CONSTRAINT fk_environment_operations_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT
)""",
    """CREATE TABLE change_code_observations (
	project_id VARCHAR(64) NOT NULL,
	change_id VARCHAR(36) NOT NULL,
	observation_id VARCHAR(36) NOT NULL,
	CONSTRAINT pk_change_code_observations PRIMARY KEY (project_id, change_id),
	CONSTRAINT fk_change_code_observations_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT,
	CONSTRAINT fk_change_code_observations_change_id_change_manifests FOREIGN KEY(change_id) REFERENCES change_manifests (change_id) ON DELETE RESTRICT,
	CONSTRAINT uq_change_code_observations_observation_id UNIQUE (observation_id),
	CONSTRAINT fk_change_code_observations_observation_id_code_observations FOREIGN KEY(observation_id) REFERENCES code_observations (observation_id) ON DELETE RESTRICT
)""",
    """CREATE TABLE run_code_observations (
	project_id VARCHAR(64) NOT NULL,
	run_id VARCHAR(36) NOT NULL,
	observation_id VARCHAR(36) NOT NULL,
	CONSTRAINT pk_run_code_observations PRIMARY KEY (project_id, run_id),
	CONSTRAINT fk_run_code_observations_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT,
	CONSTRAINT fk_run_code_observations_run_id_runs FOREIGN KEY(run_id) REFERENCES runs (run_id) ON DELETE RESTRICT,
	CONSTRAINT uq_run_code_observations_observation_id UNIQUE (observation_id),
	CONSTRAINT fk_run_code_observations_observation_id_code_observations FOREIGN KEY(observation_id) REFERENCES code_observations (observation_id) ON DELETE RESTRICT
)""",
    """CREATE TABLE supplemental_material_revisions (
	material_id VARCHAR(36) NOT NULL,
	revision INTEGER NOT NULL,
	project_id VARCHAR(64) NOT NULL,
	action_id VARCHAR(36) NOT NULL,
	action_revision INTEGER NOT NULL,
	document_json TEXT NOT NULL,
	fingerprint VARCHAR(64) NOT NULL,
	received_at_us BIGINT NOT NULL,
	updated_at_us BIGINT NOT NULL,
	withdrawn BOOLEAN NOT NULL,
	CONSTRAINT pk_supplemental_material_revisions PRIMARY KEY (material_id, revision),
	CONSTRAINT fk_supplemental_material_revisions_action_id_business_action_revisions FOREIGN KEY(action_id, action_revision) REFERENCES business_action_revisions (action_id, revision) ON DELETE RESTRICT,
	CONSTRAINT ck_supplemental_material_revisions_revision_positive CHECK (revision >= 1 AND action_revision >= 1),
	CONSTRAINT ck_supplemental_material_revisions_document_bound CHECK (length(document_json) <= 65536 AND length(fingerprint) = 64),
	CONSTRAINT ck_supplemental_material_revisions_time_order CHECK (received_at_us >= 0 AND updated_at_us >= received_at_us),
	CONSTRAINT fk_supplemental_material_revisions_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT
)""",
    """CREATE INDEX ix_supplemental_material_project_action ON supplemental_material_revisions (project_id, action_id, updated_at_us)""",
    """CREATE TABLE supplemental_material_receipts (
	project_id VARCHAR(64) NOT NULL,
	request_id VARCHAR(36) NOT NULL,
	content_fingerprint VARCHAR(64) NOT NULL,
	material_id VARCHAR(36) NOT NULL,
	revision INTEGER NOT NULL,
	CONSTRAINT pk_supplemental_material_receipts PRIMARY KEY (project_id, request_id),
	CONSTRAINT fk_supplemental_material_receipts_material_id_supplemental_material_revisions FOREIGN KEY(material_id, revision) REFERENCES supplemental_material_revisions (material_id, revision) ON DELETE RESTRICT,
	CONSTRAINT ck_supplemental_material_receipts_fingerprint_length CHECK (length(content_fingerprint) = 64),
	CONSTRAINT fk_supplemental_material_receipts_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT
)""",
)

def _preflight(bind):
    rows = bind.exec_driver_sql("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE type IN ('table','index','trigger') AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL")
    signature = sorted((kind, name, table, _normalize_table_sql(sql) if kind == "table" else _normalize_sql(sql)) for kind, name, table, sql in rows)
    digest = hashlib.sha256(json.dumps(signature, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    if digest != _PRIOR_SCHEMA_SHA256 or bind.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
        raise RuntimeError("STATE_PRECONDITION: exact valid 0005 structure required")


def upgrade():
    bind = op.get_bind()
    _preflight(bind)
    # SQLite legacy transaction mode 不会为 DDL 自动 BEGIN；显式开启后让 Alembic
    # 在同一事务内更新 revision。局部失败回滚新增表，不碰历史业务行。
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql("BEGIN IMMEDIATE")
    bind.exec_driver_sql("SAVEPOINT product_provenance")
    try:
        _preflight(bind)
        for statement in _CREATE_SQL:
            bind.exec_driver_sql(statement)
        if bind.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
            raise RuntimeError("STATE_PRECONDITION: invalid provenance foreign keys")
        bind.exec_driver_sql("RELEASE SAVEPOINT product_provenance")
    except BaseException:
        bind.exec_driver_sql("ROLLBACK TO SAVEPOINT product_provenance")
        bind.exec_driver_sql("RELEASE SAVEPOINT product_provenance")
        raise


def downgrade():
    raise RuntimeError("STATE_PRECONDITION: provenance downgrade requires an explicit backup")
