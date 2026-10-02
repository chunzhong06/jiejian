# 追加持久证明来源与独立预检查Job，保留旧材料回执和所有已发布检查外键。
from __future__ import annotations
import hashlib
import json
import sqlalchemy as sa
from alembic import op

revision = "0012_proof_preparation"
down_revision = "0011_runtime_load_jobs"
branch_labels = None
depends_on = None
_PRIOR_SCHEMA_SHA256 = "047ef5607ccf17a444cbe8f2ee46a6a1bbbd99308052a8f358db54d841408130"

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

_CREATE_SQL = ('\nCREATE TABLE proof_sources (\n\tsource_id VARCHAR(36) NOT NULL, \n\tproject_id VARCHAR(64) NOT NULL, \n\trevision INTEGER NOT NULL, \n\tadoption_json TEXT, \n\tcreated_at_us BIGINT NOT NULL, \n\tCONSTRAINT pk_proof_sources PRIMARY KEY (source_id), \n\tCONSTRAINT ck_proof_sources_revision_positive CHECK (revision >= 1), \n\tCONSTRAINT fk_proof_sources_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT\n)\n\n', '\nCREATE TABLE proof_source_revisions (\n\tsource_id VARCHAR(36) NOT NULL, \n\trevision INTEGER NOT NULL, \n\tfingerprint VARCHAR(64) NOT NULL, \n\tpayload TEXT NOT NULL, \n\tCONSTRAINT pk_proof_source_revisions PRIMARY KEY (source_id, revision), \n\tCONSTRAINT fk_proof_source_revisions_source_id_proof_sources FOREIGN KEY(source_id) REFERENCES proof_sources (source_id) ON DELETE RESTRICT\n)\n\n', '\nCREATE TABLE proof_read_scopes (\n\tscope_id VARCHAR(36) NOT NULL, \n\tproject_id VARCHAR(64) NOT NULL, \n\tfingerprint VARCHAR(64) NOT NULL, \n\tpayload TEXT NOT NULL, \n\trevoked_at_us BIGINT, \n\tCONSTRAINT pk_proof_read_scopes PRIMARY KEY (scope_id), \n\tCONSTRAINT fk_proof_read_scopes_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT\n)\n\n', '\nCREATE TABLE proof_preflights (\n\tpreflight_id VARCHAR(36) NOT NULL, \n\tproject_id VARCHAR(64) NOT NULL, \n\tsource_id VARCHAR(36) NOT NULL, \n\tsource_revision INTEGER NOT NULL, \n\tinput_fingerprint VARCHAR(64) NOT NULL, \n\tinput_json TEXT NOT NULL, \n\treport_sha256 VARCHAR(64), \n\tcreated_at_us BIGINT NOT NULL, \n\tCONSTRAINT pk_proof_preflights PRIMARY KEY (preflight_id), \n\tCONSTRAINT fk_proof_preflights_source_id_proof_source_revisions FOREIGN KEY(source_id, source_revision) REFERENCES proof_source_revisions (source_id, revision) ON DELETE RESTRICT, \n\tCONSTRAINT fk_proof_preflights_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT\n)\n\n')

def _preflight(bind):
    rows = bind.exec_driver_sql("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE type IN ('table','index','trigger') AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL")
    signature = sorted((kind, name, table, _normalize_table_sql(sql) if kind == "table" else _normalize_sql(sql)) for kind, name, table, sql in rows)
    digest = hashlib.sha256(json.dumps(signature, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    if digest != _PRIOR_SCHEMA_SHA256 or bind.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
        raise RuntimeError("STATE_PRECONDITION: exact valid 0011 structure required")


def upgrade():
    bind = op.get_bind()
    _preflight(bind)
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql("BEGIN IMMEDIATE")
    bind.exec_driver_sql("SAVEPOINT proof_preparation")
    try:
        _preflight(bind)
        bind.exec_driver_sql("PRAGMA defer_foreign_keys=ON")
        for statement in _CREATE_SQL:
            bind.exec_driver_sql(statement)
        with op.batch_alter_table("jobs", recreate="always") as batch:
            batch.add_column(sa.Column("preflight_id", sa.String(36), nullable=True))
            batch.create_foreign_key(op.f("fk_jobs_preflight_id_proof_preflights"), "proof_preflights", ["preflight_id"], ["preflight_id"], ondelete="RESTRICT")
            batch.create_unique_constraint(op.f("uq_jobs_preflight_id"), ["preflight_id"])
            batch.drop_constraint(op.f("ck_jobs_exactly_one_target"), type_="check")
            batch.create_check_constraint(op.f("ck_jobs_exactly_one_target"), "(run_id IS NOT NULL) + (recording_id IS NOT NULL) + (runtime_load_id IS NOT NULL) + (preflight_id IS NOT NULL) = 1")
            batch.create_check_constraint(op.f("ck_jobs_preflight_operation_type"), "preflight_id IS NULL OR operation_type = 'PROOF_PREFLIGHT'")
        # 旧材料回执原文保持不变，新增的操作种类只作为明确的仓储读取命名空间。
        with op.batch_alter_table("preparation_receipts", recreate="always") as batch:
            batch.add_column(sa.Column("operation_kind", sa.String(32), nullable=False, server_default="MATERIAL_CHANGE"))
            batch.drop_constraint(op.f("pk_preparation_receipts"), type_="primary")
            batch.create_primary_key(op.f("pk_preparation_receipts"), ["operation_id", "project_id", "operation_kind"])
        with op.batch_alter_table("preparation_receipts", recreate="always") as batch:
            batch.alter_column("operation_kind", server_default=None)
        if bind.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
            raise RuntimeError("STATE_PRECONDITION: invalid proof preparation references")
        bind.exec_driver_sql("PRAGMA defer_foreign_keys=OFF")
        bind.exec_driver_sql("RELEASE SAVEPOINT proof_preparation")
    except BaseException:
        bind.exec_driver_sql("ROLLBACK TO SAVEPOINT proof_preparation")
        bind.exec_driver_sql("RELEASE SAVEPOINT proof_preparation")
        bind.exec_driver_sql("PRAGMA defer_foreign_keys=OFF")
        raise


def downgrade():
    raise RuntimeError("STATE_PRECONDITION: proof preparation downgrade requires an explicit backup")
