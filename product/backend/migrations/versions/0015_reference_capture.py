# 新增私有参照输入和一次正常取样Job；旧任务及来源修订保持原文。
from __future__ import annotations
import hashlib
import json
import sqlalchemy as sa
from alembic import op

revision = "0015_reference_capture"
down_revision = "0014_preparation_suggestions"
branch_labels = None
depends_on = None
_PRIOR_SCHEMA_SHA256 = "f3083cd45395d52c4bddb556100d2b698968104f62fb76e6b0ef4e2ce427af68"

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

_CREATE_SQL = ("\nCREATE TABLE proof_artifact_inputs (\n\tasset_id VARCHAR(36) NOT NULL, \n\tproject_id VARCHAR(64) NOT NULL, \n\tstate VARCHAR(16) NOT NULL, \n\tbyte_count INTEGER NOT NULL, \n\tpayload TEXT NOT NULL, \n\tcreated_at_us BIGINT NOT NULL, \n\tCONSTRAINT pk_proof_artifact_inputs PRIMARY KEY (asset_id), \n\tCONSTRAINT ck_proof_artifact_inputs_size_bounds CHECK (byte_count >= 0 AND byte_count <= 4194304), \n\tCONSTRAINT ck_proof_artifact_inputs_state_value CHECK (state IN ('PENDING','COMPLETE','INCOMPLETE','CANCELLED')), \n\tCONSTRAINT fk_proof_artifact_inputs_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT\n)\n\n", '\nCREATE TABLE reference_capture_authorizations (\n\tauthorization_id VARCHAR(36) NOT NULL, \n\tproject_id VARCHAR(64) NOT NULL, \n\tplan_hash VARCHAR(64) NOT NULL, \n\tcontrol_session_id VARCHAR(36) NOT NULL, \n\tcreated_at_us BIGINT NOT NULL, \n\trevoked_at_us BIGINT, \n\tCONSTRAINT pk_reference_capture_authorizations PRIMARY KEY (authorization_id), \n\tCONSTRAINT fk_reference_capture_authorizations_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT\n)\n\n', '\nCREATE TABLE reference_captures (\n\tcapture_id VARCHAR(36) NOT NULL, \n\tproject_id VARCHAR(64) NOT NULL, \n\tauthorization_id VARCHAR(36) NOT NULL, \n\tasset_id VARCHAR(36) NOT NULL, \n\trequest_hash VARCHAR(64) NOT NULL, \n\trequest_json TEXT NOT NULL, \n\treport_sha256 VARCHAR(64), \n\trecovery_resolved_at_us BIGINT, \n\tcreated_at_us BIGINT NOT NULL, \n\tCONSTRAINT pk_reference_captures PRIMARY KEY (capture_id), \n\tCONSTRAINT fk_reference_captures_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT, \n\tCONSTRAINT uq_reference_captures_authorization_id UNIQUE (authorization_id), \n\tCONSTRAINT fk_reference_captures_authorization_id_reference_capture_authorizations FOREIGN KEY(authorization_id) REFERENCES reference_capture_authorizations (authorization_id) ON DELETE RESTRICT, \n\tCONSTRAINT uq_reference_captures_asset_id UNIQUE (asset_id), \n\tCONSTRAINT fk_reference_captures_asset_id_proof_artifact_inputs FOREIGN KEY(asset_id) REFERENCES proof_artifact_inputs (asset_id) ON DELETE RESTRICT\n)\n\n', '\nCREATE TABLE proof_artifact_references (\n\tasset_id VARCHAR(36) NOT NULL, \n\tsource_id VARCHAR(36) NOT NULL, \n\tsource_revision INTEGER NOT NULL, \n\tCONSTRAINT pk_proof_artifact_references PRIMARY KEY (asset_id, source_id, source_revision), \n\tCONSTRAINT fk_proof_artifact_references_source_id_proof_source_revisions FOREIGN KEY(source_id, source_revision) REFERENCES proof_source_revisions (source_id, revision) ON DELETE RESTRICT, \n\tCONSTRAINT fk_proof_artifact_references_asset_id_proof_artifact_inputs FOREIGN KEY(asset_id) REFERENCES proof_artifact_inputs (asset_id) ON DELETE RESTRICT\n)\n\n')

def _preflight(bind):
    rows = bind.exec_driver_sql("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE type IN ('table','index','trigger') AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL")
    signature = sorted((kind, name, table, _normalize_table_sql(sql) if kind == "table" else _normalize_sql(sql)) for kind, name, table, sql in rows)
    digest = hashlib.sha256(json.dumps(signature, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    if digest != _PRIOR_SCHEMA_SHA256 or bind.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
        raise RuntimeError("STATE_PRECONDITION: exact valid 0014 structure required")


def upgrade():
    bind=op.get_bind()
    _preflight(bind)
    if not bind.connection.driver_connection.in_transaction:bind.exec_driver_sql("BEGIN IMMEDIATE")
    bind.exec_driver_sql("SAVEPOINT reference_capture")
    try:
        _preflight(bind)
        bind.exec_driver_sql("PRAGMA defer_foreign_keys=ON")
        for statement in _CREATE_SQL:bind.exec_driver_sql(statement)
        with op.batch_alter_table("jobs",recreate="always") as batch:
            batch.add_column(sa.Column("reference_capture_id",sa.String(36),nullable=True))
            batch.create_foreign_key(op.f("fk_jobs_reference_capture_id_reference_captures"),"reference_captures",["reference_capture_id"],["capture_id"],ondelete="RESTRICT")
            batch.create_unique_constraint(op.f("uq_jobs_reference_capture_id"),["reference_capture_id"])
            batch.drop_constraint(op.f("ck_jobs_exactly_one_target"),type_="check")
            batch.create_check_constraint(op.f("ck_jobs_exactly_one_target"),"(run_id IS NOT NULL) + (recording_id IS NOT NULL) + (runtime_load_id IS NOT NULL) + (preflight_id IS NOT NULL) + (reference_capture_id IS NOT NULL) = 1")
            batch.create_check_constraint(op.f("ck_jobs_capture_operation_type"),"(reference_capture_id IS NOT NULL) = (operation_type = 'REFERENCE_CAPTURE')")
            batch.create_check_constraint(op.f("ck_jobs_capture_single_attempt"),"reference_capture_id IS NULL OR max_attempts = 1")
        if bind.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:raise RuntimeError("STATE_PRECONDITION: invalid reference capture relations")
        bind.exec_driver_sql("PRAGMA defer_foreign_keys=OFF")
        bind.exec_driver_sql("RELEASE SAVEPOINT reference_capture")
    except BaseException:
        bind.exec_driver_sql("ROLLBACK TO SAVEPOINT reference_capture")
        bind.exec_driver_sql("RELEASE SAVEPOINT reference_capture")
        bind.exec_driver_sql("PRAGMA defer_foreign_keys=OFF")
        raise


def downgrade():
    raise RuntimeError("STATE_PRECONDITION: reference capture downgrade requires an explicit backup")
