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


class ContractVersionRepository:
    """保存内部版本链；状态转换之外的既有版本正文不可改写。"""

    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def add(self, contract: ContractVersion) -> None:
        ensure_storage_payload_safe(contract.model_dump(mode="json"), self._known_secrets)
        self._session.add(
            ContractVersionRow(
                project_id=contract.project_id,
                contract_id=contract.contract_id,
                version=contract.version,
                status=contract.status.value,
                snapshot_json=_canonical_json(contract.snapshot.model_dump(mode="json")),
                provenance_json=_canonical_json(contract.provenance.model_dump(mode="json")),
                supersedes_version=contract.supersedes_version,
                audit_json=_canonical_json(
                    [entry.model_dump(mode="json") for entry in contract.audit]
                ),
                created_at_us=contract.created_at_us,
                updated_at_us=contract.updated_at_us,
            )
        )
        _flush(self._session)

    def get(self, project_id: str, contract_id: str, version: int) -> ContractVersion | None:
        row = _scalar(
            self._session,
            select(ContractVersionRow).where(
                ContractVersionRow.project_id == project_id,
                ContractVersionRow.contract_id == contract_id,
                ContractVersionRow.version == version,
            ),
        )
        return None if row is None else self._record(row)

    def get_active(self, project_id: str, contract_id: str) -> ContractVersion | None:
        row = _scalar(
            self._session,
            select(ContractVersionRow).where(
                ContractVersionRow.project_id == project_id,
                ContractVersionRow.contract_id == contract_id,
                ContractVersionRow.status == ContractStatus.ACTIVE.value,
            ),
        )
        return None if row is None else self._record(row)

    def list_for_contract(
        self,
        project_id: str,
        contract_id: str,
    ) -> tuple[ContractVersion, ...]:
        rows = _scalars(
            self._session,
            select(ContractVersionRow)
            .where(
                ContractVersionRow.project_id == project_id,
                ContractVersionRow.contract_id == contract_id,
            )
            .order_by(ContractVersionRow.version),
        )
        return tuple(self._record(row) for row in rows)

    def list_for_project(self, project_id: str) -> tuple[ContractVersion, ...]:
        rows = _scalars(
            self._session,
            select(ContractVersionRow)
            .where(ContractVersionRow.project_id == project_id)
            .order_by(ContractVersionRow.contract_id, ContractVersionRow.version),
        )
        return tuple(self._record(row) for row in rows)

    def replace(self, contract: ContractVersion) -> None:
        ensure_storage_payload_safe(contract.model_dump(mode="json"), self._known_secrets)
        row = _scalar(
            self._session,
            select(ContractVersionRow).where(
                ContractVersionRow.project_id == contract.project_id,
                ContractVersionRow.contract_id == contract.contract_id,
                ContractVersionRow.version == contract.version,
            ),
        )
        if row is None:
            raise JiejianError(ErrorCode.CONTRACT_NOT_FOUND, "契约版本不存在")
        current = self._record(row)
        allowed = {
            ContractStatus.DRAFT: {ContractStatus.REVIEW},
            ContractStatus.REVIEW: {ContractStatus.ACTIVE, ContractStatus.REJECTED},
            ContractStatus.ACTIVE: {ContractStatus.SUPERSEDED},
        }
        if contract.status not in allowed.get(current.status, set()):
            code = (
                ErrorCode.CONTRACT_IMMUTABLE
                if current.status in {ContractStatus.ACTIVE, ContractStatus.SUPERSEDED}
                else ErrorCode.STATE_INVALID_TRANSITION
            )
            raise JiejianError(code, "契约版本不能原地修改")
        if (
            contract.snapshot != current.snapshot
            or contract.provenance != current.provenance
            or contract.supersedes_version != current.supersedes_version
            or contract.created_at_us != current.created_at_us
            or contract.audit[:-1] != current.audit
        ):
            raise JiejianError(ErrorCode.CONTRACT_IMMUTABLE, "状态转换不能改写契约正文")
        row.status = contract.status.value
        row.snapshot_json = _canonical_json(contract.snapshot.model_dump(mode="json"))
        row.audit_json = _canonical_json(
            [entry.model_dump(mode="json") for entry in contract.audit]
        )
        row.updated_at_us = contract.updated_at_us
        _flush(self._session)

    @staticmethod
    def _record(row: ContractVersionRow) -> ContractVersion:
        return ContractVersion(
            project_id=row.project_id,
            contract_id=row.contract_id,
            version=row.version,
            status=ContractStatus(row.status),
            snapshot=parse_permission_contract(row.snapshot_json),
            provenance=ContractProvenance.model_validate_json(row.provenance_json),
            supersedes_version=row.supersedes_version,
            audit=tuple(
                ContractAuditEntry.model_validate_json(
                    json.dumps(item, ensure_ascii=False, separators=(",", ":"))
                )
                for item in json.loads(row.audit_json)
            ),
            created_at_us=row.created_at_us,
            updated_at_us=row.updated_at_us,
        )
