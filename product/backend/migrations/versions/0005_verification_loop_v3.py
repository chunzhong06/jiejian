# 将空旧执行结构增量迁到冻结权限实验；预检拒绝历史执行数据，保留录制与通用租约。
from __future__ import annotations

import hashlib
import json

from alembic import op
import sqlalchemy as sa

revision = "0005_verification_loop_v3"
down_revision = "0004_action_resource_ownership"
branch_labels = None
depends_on = None

_PRIOR_SCHEMA_SHA256 = "f0928883ed63f53436d0b895c8da1e5226540d725e24ff1c0b34d676bfa12012"
_DORMANT_TABLES = (
    "runs", "evidence_index", "findings", "finding_occurrences", "run_finalizations",
    "regression_baselines", "gate_results", "change_manifests", "source_change_sets",
    "change_impact_assessments",
)


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
    rows = bind.exec_driver_sql("SELECT type,name,tbl_name,sql FROM sqlite_master "
        "WHERE type IN ('table','index','trigger') AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL")
    signature = sorted((kind, name, table, _normalize_table_sql(sql) if kind == "table" else _normalize_sql(sql))
        for kind, name, table, sql in rows)
    digest = hashlib.sha256(json.dumps(signature, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    if digest != _PRIOR_SCHEMA_SHA256:
        raise RuntimeError("STATE_PRECONDITION: exact 0004 structure required")
    if bind.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
        raise RuntimeError("STATE_PRECONDITION: invalid prior foreign keys")
    for table in _DORMANT_TABLES:
        if bind.exec_driver_sql(f'SELECT 1 FROM "{table}" LIMIT 1').first() is not None:
            raise RuntimeError("STATE_PRECONDITION: unmappable historical execution data")
    if bind.exec_driver_sql("SELECT 1 FROM jobs WHERE run_id IS NOT NULL LIMIT 1").first() is not None:
        raise RuntimeError("STATE_PRECONDITION: historical run job")


def _create_run_table():
    op.create_table("runs",
        sa.Column("run_id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("plan_fingerprint", sa.String(64), nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("policy_epoch", sa.BigInteger(), nullable=False),
        sa.Column("engine_version", sa.String(64), nullable=False),
        sa.Column("lifecycle", sa.String(24), nullable=False),
        sa.Column("verdict", sa.String(16)),
        sa.Column("created_at_us", sa.BigInteger(), nullable=False),
        sa.Column("updated_at_us", sa.BigInteger(), nullable=False),
        sa.Column("finished_at_us", sa.BigInteger()),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="RESTRICT"),
        sa.CheckConstraint("length(run_id) = 36 AND substr(run_id, 1, 4) = 'run_' AND substr(run_id, 5) NOT GLOB '*[^0-9a-f]*'", name="run_id_format"),
        sa.CheckConstraint("lifecycle IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED', 'SAFETY_STOPPED')", name="lifecycle_value"),
        sa.CheckConstraint("verdict IS NULL OR verdict IN ('PASS', 'BLOCK', 'INCONCLUSIVE')", name="verdict_value"),
        sa.CheckConstraint("(lifecycle = 'COMPLETED' AND verdict IS NOT NULL) OR "
            "(lifecycle = 'SAFETY_STOPPED' AND (verdict IS NULL OR verdict IN ('BLOCK', 'INCONCLUSIVE'))) OR "
            "(lifecycle NOT IN ('COMPLETED', 'SAFETY_STOPPED') AND verdict IS NULL)", name="lifecycle_verdict_matrix"),
        sa.CheckConstraint("policy_epoch >= 0", name="policy_epoch_nonnegative"),
        sa.CheckConstraint("length(engine_version) BETWEEN 1 AND 64", name="engine_version_length"),
        sa.CheckConstraint("created_at_us >= 0 AND updated_at_us >= created_at_us AND (finished_at_us IS NULL OR finished_at_us >= created_at_us)", name="time_order"),
        *(sa.CheckConstraint(f"length({name}) = 64 AND {name} NOT GLOB '*[^0-9a-f]*'", name=f"{name}_format")
          for name in ("request_hash", "plan_fingerprint", "source_fingerprint")),
    )
    op.create_index("ix_runs_project_created", "runs", ["project_id", "created_at_us"])
    op.create_index("ix_runs_lifecycle_updated", "runs", ["lifecycle", "updated_at_us"])


def _create_publications():
    op.create_table("check_publications",
        sa.Column("run_id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("fencing_token", sa.BigInteger(), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("result_hash", sa.String(64), nullable=False),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        sa.Column("published_at_us", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.run_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("job_id", name="uq_check_publications_job_id"),
        sa.CheckConstraint("attempt >= 1 AND fencing_token >= 1 AND published_at_us >= 0", name="publication_bounds"),
        *(sa.CheckConstraint(f"length({name}) = 64 AND {name} NOT GLOB '*[^0-9a-f]*'", name=f"{name}_format")
          for name in ("request_hash", "result_hash", "manifest_hash")),
    )


def upgrade():
    bind = op.get_bind()
    _preflight(bind)
    # jobs 的 Recording 行及租约原位保留；禁用 FK 只覆盖已预检的空父表替换事务。
    with op.get_context().autocommit_block():
        bind.exec_driver_sql("PRAGMA foreign_keys=OFF")
    bind.exec_driver_sql("BEGIN IMMEDIATE")
    try:
        # 获得写锁后再次预检，消除首次只读核对到 DDL 之间的数据漂移窗口。
        _preflight(bind)
        op.drop_table("runs")
        _create_run_table()
        _create_publications()
        if bind.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
            raise RuntimeError("STATE_PRECONDITION: publication foreign keys invalid")
        bind.exec_driver_sql("COMMIT")
    except BaseException:
        bind.exec_driver_sql("ROLLBACK")
        raise
    finally:
        with op.get_context().autocommit_block():
            bind.exec_driver_sql("PRAGMA foreign_keys=ON")


def downgrade():
    raise RuntimeError("STATE_PRECONDITION: verification downgrade requires an explicit backup")
