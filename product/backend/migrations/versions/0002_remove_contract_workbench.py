# 删除旧 Contract Workbench 仓储，并把保留版本的 provenance 收敛为内部来源。

from __future__ import annotations

import hashlib
import json

from alembic import op
import sqlalchemy as sa


revision = "0002_remove_contract_workbench"
down_revision = "0001_web_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    versions = bind.execute(
        sa.text(
            "SELECT project_id, contract_id, version, provenance_json "
            "FROM contract_versions"
        )
    ).mappings()
    for row in versions:
        raw = json.loads(row["provenance_json"])
        sources = [
            source
            for source in raw.get("sources", [])
            if isinstance(source, dict)
            and source.get("source_type") == "project_config"
        ]
        provenance = json.dumps(
            {"sources": sources},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        bind.execute(
            sa.text(
                "UPDATE contract_versions SET provenance_json = :provenance "
                "WHERE project_id = :project_id AND contract_id = :contract_id "
                "AND version = :version"
            ),
            {
                "provenance": provenance,
                "project_id": row["project_id"],
                "contract_id": row["contract_id"],
                "version": row["version"],
            },
        )

    # 旧手工 Contract 不再是产品入口；只解除项目绑定，保留历史版本记录。
    projects = bind.execute(
        sa.text(
            "SELECT project_id, governed_contract_id FROM projects "
            "WHERE governed_contract_id IS NOT NULL"
        )
    ).mappings()
    for project in projects:
        generated_id = (
            "generated-contract-"
            + hashlib.sha256(project["project_id"].encode("utf-8")).hexdigest()[:24]
        )
        if project["governed_contract_id"] != generated_id:
            bind.execute(
                sa.text(
                    "UPDATE projects SET governed_contract_id = NULL, "
                    "governed_contract_version = NULL WHERE project_id = :project_id"
                ),
                {"project_id": project["project_id"]},
            )

    op.drop_index("ix_contract_candidates_project_created", table_name="contract_candidates")
    op.drop_table("contract_candidates")
    op.drop_index("ix_requirements_project_created", table_name="requirements")
    op.drop_table("requirements")


def downgrade() -> None:
    # 已删除的手工需求、候选及项目绑定不可恢复；downgrade 只恢复 0001 结构。
    op.create_table(
        "requirements",
        sa.Column("requirement_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_locator", sa.String(length=1024), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("requirement_text", sa.Text(), nullable=False),
        sa.Column("security_tags_json", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at_us", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("created_at_us >= 0", name=op.f("ck_requirements_created_nonnegative")),
        sa.CheckConstraint("length(created_by) BETWEEN 1 AND 128", name=op.f("ck_requirements_created_by_length")),
        sa.CheckConstraint("length(requirement_id) = 36 AND substr(requirement_id, 1, 4) = 'req_' AND substr(requirement_id, 5) NOT GLOB '*[^0-9a-f]*'", name=op.f("ck_requirements_requirement_id_format")),
        sa.CheckConstraint("length(requirement_text) BETWEEN 1 AND 16384", name=op.f("ck_requirements_text_length")),
        sa.CheckConstraint("length(security_tags_json) BETWEEN 2 AND 8192", name=op.f("ck_requirements_tags_json_length")),
        sa.CheckConstraint("length(source_locator) BETWEEN 1 AND 1024", name=op.f("ck_requirements_source_locator_length")),
        sa.CheckConstraint("length(source_sha256) = 64 AND source_sha256 NOT GLOB '*[^0-9a-f]*'", name=op.f("ck_requirements_source_sha256_format")),
        sa.CheckConstraint("source_type IN ('requirement_text', 'project_config', 'recording_flow', 'static_analysis', 'llm')", name=op.f("ck_requirements_source_type_value")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], name=op.f("fk_requirements_project_id_projects"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("requirement_id", name=op.f("pk_requirements")),
    )
    op.create_index("ix_requirements_project_created", "requirements", ["project_id", "created_at_us"], unique=False)
    op.create_table(
        "contract_candidates",
        sa.Column("candidate_id", sa.String(length=37), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_locator", sa.String(length=1024), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("rule_json", sa.Text(), nullable=False),
        sa.Column("requirement_ids_json", sa.Text(), nullable=False),
        sa.Column("llm_metadata_json", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at_us", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("created_at_us >= 0", name=op.f("ck_contract_candidates_created_nonnegative")),
        sa.CheckConstraint("length(candidate_id) = 37 AND substr(candidate_id, 1, 5) = 'cand_' AND substr(candidate_id, 6) NOT GLOB '*[^0-9a-f]*'", name=op.f("ck_contract_candidates_candidate_id_format")),
        sa.CheckConstraint("length(created_by) BETWEEN 1 AND 128", name=op.f("ck_contract_candidates_created_by_length")),
        sa.CheckConstraint("length(requirement_ids_json) BETWEEN 2 AND 65536", name=op.f("ck_contract_candidates_requirement_ids_json_length")),
        sa.CheckConstraint("length(rule_json) BETWEEN 2 AND 65536", name=op.f("ck_contract_candidates_rule_json_length")),
        sa.CheckConstraint("length(source_locator) BETWEEN 1 AND 1024", name=op.f("ck_contract_candidates_source_locator_length")),
        sa.CheckConstraint("length(source_sha256) = 64 AND source_sha256 NOT GLOB '*[^0-9a-f]*'", name=op.f("ck_contract_candidates_source_sha256_format")),
        sa.CheckConstraint("source_type IN ('requirement_text', 'project_config', 'recording_flow', 'static_analysis', 'llm')", name=op.f("ck_contract_candidates_source_type_value")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], name=op.f("fk_contract_candidates_project_id_projects"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("candidate_id", name=op.f("pk_contract_candidates")),
    )
    op.create_index("ix_contract_candidates_project_created", "contract_candidates", ["project_id", "created_at_us"], unique=False)

    bind = op.get_bind()
    versions = bind.execute(
        sa.text(
            "SELECT project_id, contract_id, version, provenance_json "
            "FROM contract_versions"
        )
    ).mappings()
    for row in versions:
        raw = json.loads(row["provenance_json"])
        provenance = json.dumps(
            {
                "candidate_ids": [],
                "requirement_ids": [],
                "sources": raw.get("sources", []),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        bind.execute(
            sa.text(
                "UPDATE contract_versions SET provenance_json = :provenance "
                "WHERE project_id = :project_id AND contract_id = :contract_id "
                "AND version = :version"
            ),
            {
                "provenance": provenance,
                "project_id": row["project_id"],
                "contract_id": row["contract_id"],
                "version": row["version"],
            },
        )
