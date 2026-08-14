"""Permission Execution Profile 的非秘密摘要仓储。"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...domain.identifiers import PROJECT_ID_PATTERN, SHA256_PATTERN
from ...errors import ErrorCode, JiejianError
from ...storage.models import PermissionExecutionProfileRow
from .base import StorageRecord, _flush, _scalar, _scalars, ensure_storage_payload_safe


class PermissionExecutionProfileRecord(StorageRecord):
    schema_version: str = Field(default="2", pattern=r"^2$")
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
    def validate_time(self) -> PermissionExecutionProfileRecord:
        if self.updated_at_us < self.created_at_us:
            raise ValueError("profile update time precedes creation")
        return self


class PermissionExecutionProfileRepository:
    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def add(self, record: PermissionExecutionProfileRecord) -> None:
        values = record.model_dump(mode="json", exclude={"schema_version"})
        values["schema_version"] = record.schema_version
        ensure_storage_payload_safe(values, self._known_secrets)
        self._session.add(PermissionExecutionProfileRow(**values))
        _flush(self._session)

    def get(self, profile_id: str) -> PermissionExecutionProfileRecord | None:
        row = _scalar(
            self._session,
            select(PermissionExecutionProfileRow).where(
                PermissionExecutionProfileRow.profile_id == profile_id
            ),
        )
        return None if row is None else self._record(row)

    def list_for_project(self, project_id: str) -> tuple[PermissionExecutionProfileRecord, ...]:
        rows = _scalars(
            self._session,
            select(PermissionExecutionProfileRow)
            .where(PermissionExecutionProfileRow.project_id == project_id)
            .order_by(PermissionExecutionProfileRow.profile_id),
        )
        return tuple(self._record(row) for row in rows)

    def replace(self, record: PermissionExecutionProfileRecord) -> None:
        values = record.model_dump(mode="json")
        ensure_storage_payload_safe(values, self._known_secrets)
        row = _scalar(
            self._session,
            select(PermissionExecutionProfileRow).where(
                PermissionExecutionProfileRow.profile_id == record.profile_id
            ),
        )
        if row is None:
            raise JiejianError(ErrorCode.PERMISSION_PROFILE_NOT_FOUND, "权限 Profile 不存在")
        if row.project_id != record.project_id:
            raise JiejianError(
                ErrorCode.PERMISSION_PROFILE_PROJECT_CONFLICT,
                "权限 Profile 与项目不匹配",
            )
        for key, value in values.items():
            setattr(row, key, value)
        _flush(self._session)

    @staticmethod
    def _record(row: PermissionExecutionProfileRow) -> PermissionExecutionProfileRecord:
        return PermissionExecutionProfileRecord.model_validate(
            {
                "schema_version": row.schema_version,
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
