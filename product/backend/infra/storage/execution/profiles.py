# Permission Execution Profile 的非秘密治理元数据映射。

from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from product.backend.infra.storage.base import Base


class ExecutionProfileRow(Base):
    __tablename__ = "execution_profiles"
    __table_args__ = (
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

# 本聚合的 Repository 与持久化记录边界。

"""Permission Execution Profile 的非秘密摘要仓储。"""

from collections.abc import Sequence

from pydantic import Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from product.backend.core.identifiers import PROJECT_ID_PATTERN, SHA256_PATTERN
from product.backend.core.errors import ErrorCode, JiejianError

from product.backend.infra.storage.base import StorageRecord, _flush, _scalar, _scalars, ensure_storage_payload_safe


class ExecutionProfileRecord(StorageRecord):
    profile_id: str = Field(pattern=PROJECT_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    source_path: str = Field(min_length=1, max_length=2048)
    source_hash: str = Field(pattern=SHA256_PATTERN)
    contract_id: str = Field(min_length=1, max_length=128)
    contract_version: int = Field(ge=1)
    contract_fingerprint: str = Field(pattern=SHA256_PATTERN)
    plan_fingerprint: str = Field(pattern=SHA256_PATTERN)
    engine_version: str = Field(min_length=1, max_length=128)
    created_at_us: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_time(self) -> ExecutionProfileRecord:
        if self.updated_at_us < self.created_at_us:
            raise ValueError("profile update time precedes creation")
        return self


class ExecutionProfileRepository:
    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def add(self, record: ExecutionProfileRecord) -> None:
        values = record.model_dump(mode="json")
        ensure_storage_payload_safe(values, self._known_secrets)
        self._session.add(ExecutionProfileRow(**values))
        _flush(self._session)

    def get(self, profile_id: str) -> ExecutionProfileRecord | None:
        row = _scalar(
            self._session,
            select(ExecutionProfileRow).where(
                ExecutionProfileRow.profile_id == profile_id
            ),
        )
        return None if row is None else self._record(row)

    def list_for_project(self, project_id: str) -> tuple[ExecutionProfileRecord, ...]:
        rows = _scalars(
            self._session,
            select(ExecutionProfileRow)
            .where(ExecutionProfileRow.project_id == project_id)
            .order_by(ExecutionProfileRow.profile_id),
        )
        return tuple(self._record(row) for row in rows)

    def replace(self, record: ExecutionProfileRecord) -> None:
        values = record.model_dump(mode="json")
        ensure_storage_payload_safe(values, self._known_secrets)
        row = _scalar(
            self._session,
            select(ExecutionProfileRow).where(
                ExecutionProfileRow.profile_id == record.profile_id
            ),
        )
        if row is None:
            raise JiejianError(ErrorCode.EXECUTION_PROFILE_NOT_FOUND, "权限 Profile 不存在")
        if row.project_id != record.project_id:
            raise JiejianError(
                ErrorCode.EXECUTION_PROFILE_PROJECT_CONFLICT,
                "权限 Profile 与项目不匹配",
            )
        for key, value in values.items():
            setattr(row, key, value)
        _flush(self._session)

    @staticmethod
    def _record(row: ExecutionProfileRow) -> ExecutionProfileRecord:
        return ExecutionProfileRecord.model_validate(
            {
                "profile_id": row.profile_id,
                "project_id": row.project_id,
                "source_path": row.source_path,
                "source_hash": row.source_hash,
                "contract_id": row.contract_id,
                "contract_version": row.contract_version,
                "contract_fingerprint": row.contract_fingerprint,
                "plan_fingerprint": row.plan_fingerprint,
                "engine_version": row.engine_version,
                "created_at_us": row.created_at_us,
                "updated_at_us": row.updated_at_us,
            }
        )
