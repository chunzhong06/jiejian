# 历史表与只读记录形状保留用于无损升级；当前产品已退出这组仓储写入。
# 内部 ContractVersion 的 SQLAlchemy 映射与不可变版本仓储。

from __future__ import annotations

import json
from collections.abc import Sequence

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, String, Text, select
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, Session, mapped_column

from product.backend.core.contracts.models import (
    ContractAuditEntry,
    ContractProvenance,
    ContractVersion,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import ContractStatus
from product.backend.core.verification.permissions import parse_permission_contract
from product.backend.infra.storage.base import (
    Base,
    _canonical_json,
    _flush,
    _scalar,
    _scalars,
    ensure_storage_payload_safe,
)


class ContractVersionRow(Base):
    __tablename__ = "contract_versions"
    __table_args__ = (
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
        ForeignKey("projects.project_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    contract_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    provenance_json: Mapped[str] = mapped_column(Text, nullable=False)
    supersedes_version: Mapped[int | None] = mapped_column(Integer)
    audit_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
