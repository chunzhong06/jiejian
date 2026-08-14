"""Permission Execution Profile 的非秘密治理元数据映射。"""

from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PermissionExecutionProfileRow(Base):
    __tablename__ = "permission_execution_profiles"
    __table_args__ = (
        CheckConstraint("schema_version = '2'", name="profile_schema_version_value"),
        CheckConstraint(
            "length(profile_id) BETWEEN 1 AND 64 AND "
            "substr(profile_id, 1, 1) GLOB '[a-z]' AND "
            "profile_id NOT GLOB '*[^a-z0-9_-]*'",
            name="profile_id_format",
        ),
        CheckConstraint("contract_version >= 1", name="profile_contract_version"),
        CheckConstraint(
            "length(source_hash) = 64 AND length(contract_fingerprint) = 64 "
            "AND length(plan_fingerprint) = 64",
            name="profile_hash_lengths",
        ),
        CheckConstraint(
            "created_at_us >= 0 AND updated_at_us >= created_at_us",
            name="profile_time_order",
        ),
        Index("ix_permission_profiles_project_updated", "project_id", "updated_at_us"),
    )

    profile_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(8), nullable=False)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.project_id"), nullable=False
    )
    source_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_id: Mapped[str] = mapped_column(String(128), nullable=False)
    contract_version: Mapped[int] = mapped_column(Integer, nullable=False)
    contract_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
