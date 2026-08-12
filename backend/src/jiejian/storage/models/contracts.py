# 阶段 2.1 的 SQLAlchemy typed declarative 映射。

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text as sql_text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

class RequirementRow(Base):
    __tablename__ = "requirements"
    __table_args__ = (
        CheckConstraint("schema_version = '1'", name="schema_version_value"),
        CheckConstraint(
            "source_type IN ('requirement_text', 'project_config', 'recording_flow', "
            "'static_analysis', 'llm')",
            name="source_type_value",
        ),
        CheckConstraint(
            "length(requirement_id) = 36 AND substr(requirement_id, 1, 4) = 'req_' "
            "AND substr(requirement_id, 5) NOT GLOB '*[^0-9a-f]*'",
            name="requirement_id_format",
        ),
        CheckConstraint("length(source_locator) BETWEEN 1 AND 1024", name="source_locator_length"),
        CheckConstraint(
            "length(source_sha256) = 64 AND source_sha256 NOT GLOB '*[^0-9a-f]*'",
            name="source_sha256_format",
        ),
        CheckConstraint("length(requirement_text) BETWEEN 1 AND 16384", name="text_length"),
        CheckConstraint("length(security_tags_json) BETWEEN 2 AND 8192", name="tags_json_length"),
        CheckConstraint("length(created_by) BETWEEN 1 AND 128", name="created_by_length"),
        CheckConstraint("created_at_us >= 0", name="created_nonnegative"),
        Index("ix_requirements_project_created", "project_id", "created_at_us"),
    )

    requirement_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(8), nullable=False)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_locator: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    requirement_text: Mapped[str] = mapped_column(Text, nullable=False)
    security_tags_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
class ContractCandidateRow(Base):
    __tablename__ = "contract_candidates"
    __table_args__ = (
        CheckConstraint("schema_version = '1'", name="schema_version_value"),
        CheckConstraint(
            "source_type IN ('requirement_text', 'project_config', 'recording_flow', "
            "'static_analysis', 'llm')",
            name="source_type_value",
        ),
        CheckConstraint(
            "length(candidate_id) = 37 AND substr(candidate_id, 1, 5) = 'cand_' "
            "AND substr(candidate_id, 6) NOT GLOB '*[^0-9a-f]*'",
            name="candidate_id_format",
        ),
        CheckConstraint("length(source_locator) BETWEEN 1 AND 1024", name="source_locator_length"),
        CheckConstraint(
            "length(source_sha256) = 64 AND source_sha256 NOT GLOB '*[^0-9a-f]*'",
            name="source_sha256_format",
        ),
        CheckConstraint("length(rule_json) BETWEEN 2 AND 65536", name="rule_json_length"),
        CheckConstraint("length(requirement_ids_json) BETWEEN 2 AND 65536", name="requirement_ids_json_length"),
        CheckConstraint("length(created_by) BETWEEN 1 AND 128", name="created_by_length"),
        CheckConstraint("created_at_us >= 0", name="created_nonnegative"),
        Index("ix_contract_candidates_project_created", "project_id", "created_at_us"),
    )

    candidate_id: Mapped[str] = mapped_column(String(37), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(8), nullable=False)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_locator: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_json: Mapped[str] = mapped_column(Text, nullable=False)
    requirement_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    llm_metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
class ContractVersionRow(Base):
    __tablename__ = "contract_versions"
    __table_args__ = (
        CheckConstraint("schema_version = '1'", name="schema_version_value"),

        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "status IN ('DRAFT', 'REVIEW', 'ACTIVE', 'SUPERSEDED', 'REJECTED')",
            name="status_value",
        ),
        CheckConstraint("length(contract_id) BETWEEN 1 AND 128", name="contract_id_length"),
        CheckConstraint("length(snapshot_json) BETWEEN 2 AND 1048576", name="snapshot_json_length"),
        CheckConstraint("length(provenance_json) BETWEEN 2 AND 1048576", name="provenance_json_length"),
        CheckConstraint("length(audit_json) BETWEEN 2 AND 131072", name="audit_json_length"),
        CheckConstraint(
            "(version = 1 AND supersedes_version IS NULL) OR "
            "(version > 1 AND supersedes_version = version - 1)",
            name="supersedes_version_order",
        ),
        CheckConstraint(
            "created_at_us >= 0 AND updated_at_us >= created_at_us",
            name="time_order",
        ),
        Index("ix_contract_versions_project_status", "project_id", "status", "updated_at_us"),
        Index(
            "uq_contract_versions_active",
            "project_id",
            "contract_id",
            unique=True,
            sqlite_where=sql_text("status = 'ACTIVE'"),
        ),
    )

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="RESTRICT"), primary_key=True
    )
    contract_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    provenance_json: Mapped[str] = mapped_column(Text, nullable=False)
    supersedes_version: Mapped[int | None] = mapped_column(Integer)
    audit_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
