"""建立阶段 5 契约治理持久化基础。"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_stage5_contracts"
down_revision: str | None = "0003_stage4_control_plane"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "requirements",
        sa.Column("requirement_id", sa.String(length=36), nullable=False),
        sa.Column("schema_version", sa.String(length=8), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_locator", sa.String(length=1024), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("requirement_text", sa.Text(), nullable=False),
        sa.Column("security_tags_json", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at_us", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("schema_version = '1'", name=op.f("ck_requirements_schema_version_value")),
        sa.CheckConstraint(
            "source_type IN ('requirement_text', 'project_config', 'recording_flow', "
            "'static_analysis', 'llm')",
            name=op.f("ck_requirements_source_type_value"),
        ),
        sa.CheckConstraint(
            "length(requirement_id) = 36 AND substr(requirement_id, 1, 4) = 'req_' "
            "AND substr(requirement_id, 5) NOT GLOB '*[^0-9a-f]*'",
            name=op.f("ck_requirements_requirement_id_format"),
        ),
        sa.CheckConstraint(
            "length(source_locator) BETWEEN 1 AND 1024",
            name=op.f("ck_requirements_source_locator_length"),
        ),
        sa.CheckConstraint(
            "length(source_sha256) = 64 AND source_sha256 NOT GLOB '*[^0-9a-f]*'",
            name=op.f("ck_requirements_source_sha256_format"),
        ),
        sa.CheckConstraint(
            "length(requirement_text) BETWEEN 1 AND 16384",
            name=op.f("ck_requirements_text_length"),
        ),
        sa.CheckConstraint(
            "length(security_tags_json) BETWEEN 2 AND 8192",
            name=op.f("ck_requirements_tags_json_length"),
        ),
        sa.CheckConstraint(
            "length(created_by) BETWEEN 1 AND 128",
            name=op.f("ck_requirements_created_by_length"),
        ),
        sa.CheckConstraint("created_at_us >= 0", name=op.f("ck_requirements_created_nonnegative")),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.project_id"],
            name=op.f("fk_requirements_project_id_projects"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("requirement_id", name=op.f("pk_requirements")),
    )
    op.create_index(
        "ix_requirements_project_created",
        "requirements",
        ["project_id", "created_at_us"],
        unique=False,
    )

    op.create_table(
        "contract_candidates",
        sa.Column("candidate_id", sa.String(length=37), nullable=False),
        sa.Column("schema_version", sa.String(length=8), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_locator", sa.String(length=1024), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("rule_json", sa.Text(), nullable=False),
        sa.Column("requirement_ids_json", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at_us", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("schema_version = '1'", name=op.f("ck_contract_candidates_schema_version_value")),
        sa.CheckConstraint(
            "source_type IN ('requirement_text', 'project_config', 'recording_flow', "
            "'static_analysis', 'llm')",
            name=op.f("ck_contract_candidates_source_type_value"),
        ),
        sa.CheckConstraint(
            "length(candidate_id) = 37 AND substr(candidate_id, 1, 5) = 'cand_' "
            "AND substr(candidate_id, 6) NOT GLOB '*[^0-9a-f]*'",
            name=op.f("ck_contract_candidates_candidate_id_format"),
        ),
        sa.CheckConstraint("length(source_locator) BETWEEN 1 AND 1024", name=op.f("ck_contract_candidates_source_locator_length")),
        sa.CheckConstraint("length(source_sha256) = 64 AND source_sha256 NOT GLOB '*[^0-9a-f]*'", name=op.f("ck_contract_candidates_source_sha256_format")),
        sa.CheckConstraint("length(rule_json) BETWEEN 2 AND 65536", name=op.f("ck_contract_candidates_rule_json_length")),
        sa.CheckConstraint("length(requirement_ids_json) BETWEEN 2 AND 65536", name=op.f("ck_contract_candidates_requirement_ids_json_length")),
        sa.CheckConstraint("length(created_by) BETWEEN 1 AND 128", name=op.f("ck_contract_candidates_created_by_length")),
        sa.CheckConstraint("created_at_us >= 0", name=op.f("ck_contract_candidates_created_nonnegative")),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.project_id"],
            name=op.f("fk_contract_candidates_project_id_projects"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("candidate_id", name=op.f("pk_contract_candidates")),
    )
    op.create_index(
        "ix_contract_candidates_project_created",
        "contract_candidates",
        ["project_id", "created_at_us"],
        unique=False,
    )

    op.create_table(
        "contract_versions",
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("contract_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("provenance_json", sa.Text(), nullable=False),
        sa.Column("supersedes_version", sa.Integer(), nullable=True),
        sa.Column("audit_json", sa.Text(), nullable=False),
        sa.Column("created_at_us", sa.BigInteger(), nullable=False),
        sa.Column("updated_at_us", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("schema_version = '1'", name=op.f("ck_contract_versions_schema_version_value")),
        sa.CheckConstraint("version >= 1", name=op.f("ck_contract_versions_version_positive")),
        sa.CheckConstraint("status IN ('DRAFT', 'REVIEW', 'ACTIVE', 'SUPERSEDED', 'REJECTED')", name=op.f("ck_contract_versions_status_value")),
        sa.CheckConstraint("length(contract_id) BETWEEN 1 AND 128", name=op.f("ck_contract_versions_contract_id_length")),
        sa.CheckConstraint("length(snapshot_json) BETWEEN 2 AND 1048576", name=op.f("ck_contract_versions_snapshot_json_length")),
        sa.CheckConstraint("length(provenance_json) BETWEEN 2 AND 1048576", name=op.f("ck_contract_versions_provenance_json_length")),
        sa.CheckConstraint("length(audit_json) BETWEEN 2 AND 131072", name=op.f("ck_contract_versions_audit_json_length")),
        sa.CheckConstraint(
            "(version = 1 AND supersedes_version IS NULL) OR "
            "(version > 1 AND supersedes_version = version - 1)",
            name=op.f("ck_contract_versions_supersedes_version_order"),
        ),
        sa.CheckConstraint("created_at_us >= 0 AND updated_at_us >= created_at_us", name=op.f("ck_contract_versions_time_order")),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.project_id"],
            name=op.f("fk_contract_versions_project_id_projects"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "project_id", "contract_id", "version",
            name=op.f("pk_contract_versions"),
        ),
    )
    op.create_index(
        "ix_contract_versions_project_status",
        "contract_versions",
        ["project_id", "status", "updated_at_us"],
        unique=False,
    )
    op.create_index(
        "uq_contract_versions_active",
        "contract_versions",
        ["project_id", "contract_id"],
        unique=True,
        sqlite_where=sa.text("status = 'ACTIVE'"),
    )


def downgrade() -> None:
    raise RuntimeError("界鉴数据库迁移只允许向前；请从备份恢复旧版本")
