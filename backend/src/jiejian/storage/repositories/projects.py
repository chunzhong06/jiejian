# =============================================================================
# Project 聚合仓储
#
# 定位
#   Project 自身配置、状态与安全范围的持久化适配器
#
# 职责
#   映射 Project 记录｜保存配置和状态｜提供项目级查询
#
# 调用链
#   ProjectControlService → ProjectRepository → Project ORM rows
# =============================================================================

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ...domain.identifiers import (
    EVIDENCE_ID_PATTERN,
    JOB_ID_PATTERN,
    PROJECT_ID_PATTERN,
    RECORDING_ID_PATTERN,
    RUN_ID_PATTERN,
    SHA256_PATTERN,
)
from ...contracts.models import (
    ContractAuditEntry,
    ContractCandidate,
    ContractProvenance,
    ContractSourceType,
    ContractVersion,
    LLMGenerationMetadata,
    Requirement,
    SourceReference,
)
from ...domain.lifecycle import JobState, ProjectStatus, RunLifecycle, RunVerdict
from ...domain.lifecycle import ContractStatus
from ...verification.models import ContractRule, SecurityContract
from ...recording.models import (
    Recording,
    RecordingState,
    RecordingStateEvent,
    RecordingTerminalState,
)
from ...errors import ErrorCode, JiejianError
from ...protocols import (
    STAGED_ARTIFACT_MAX_BYTES,
    FlowDraftV1,
    RecordingEventKind,
    RecordingEventV1,
    RecordingHeaderV1,
    StagedArtifactV1,
    canonical_flow_draft_json_bytes,
)
from ..models import (
    ContractCandidateRow,
    ContractVersionRow,
    EvidenceIndexRow,
    FlowDraftRevisionRow,
    JobEventRow,
    JobRow,
    ProjectRow,
    RequirementRow,
    RecordingRow,
    RunRow,
)
from .base import (
    MetadataValue,
    StorageRecord,
    _METADATA_KEY,
    _SENSITIVE_METADATA_KEY,
    _canonical_json,
    _flush,
    _scalar,
    _scalars,
    ensure_storage_payload_safe,
)

class ProjectRecord(StorageRecord):

    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    name: str = Field(min_length=1, max_length=128)
    status: ProjectStatus
    source_path: str | None = Field(default=None, min_length=1, max_length=1024)
    source_hash: str | None = Field(default=None, pattern=SHA256_PATTERN)
    active_contract_path: str | None = Field(default=None, min_length=1, max_length=1024)
    active_contract_hash: str | None = Field(default=None, pattern=SHA256_PATTERN)
    governed_contract_id: str | None = Field(default=None, min_length=1, max_length=128)
    governed_contract_version: int | None = Field(default=None, ge=1)
    created_at_us: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_time_order(self) -> ProjectRecord:
        if self.updated_at_us < self.created_at_us:
            raise ValueError("project update time precedes creation")
        if (self.governed_contract_id is None) != (self.governed_contract_version is None):
            raise ValueError("governed contract binding must contain id and version together")
        return self
class ProjectRepository:
    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def add(self, record: ProjectRecord) -> None:
        ensure_storage_payload_safe(
            record.model_dump(mode="json"), self._known_secrets
        )
        self._session.add(
            ProjectRow(
                project_id=record.project_id,
                name=record.name,
                status=record.status.value,
                source_path=record.source_path,
                source_hash=record.source_hash,
                active_contract_path=record.active_contract_path,
                active_contract_hash=record.active_contract_hash,
                governed_contract_id=record.governed_contract_id,
                governed_contract_version=record.governed_contract_version,
                created_at_us=record.created_at_us,
                updated_at_us=record.updated_at_us,
            )
        )
        _flush(self._session)

    def get(self, project_id: str) -> ProjectRecord | None:
        row = _scalar(
            self._session,
            select(ProjectRow).where(ProjectRow.project_id == project_id),
        )
        if row is None:
            return None
        return ProjectRecord(
            project_id=row.project_id,
            name=row.name,
            status=ProjectStatus(row.status),
            source_path=row.source_path,
            source_hash=row.source_hash,
            active_contract_path=row.active_contract_path,
            active_contract_hash=row.active_contract_hash,
            governed_contract_id=row.governed_contract_id,
            governed_contract_version=row.governed_contract_version,
            created_at_us=row.created_at_us,
            updated_at_us=row.updated_at_us,
        )
    def list_all(self) -> tuple[ProjectRecord, ...]:
        rows = _scalars(
            self._session,
            select(ProjectRow).order_by(ProjectRow.updated_at_us.desc(), ProjectRow.project_id),
        )
        return tuple(self._record(row) for row in rows)

    def replace(self, record: ProjectRecord) -> None:
        ensure_storage_payload_safe(
            record.model_dump(mode="json"), self._known_secrets

        )
        row = _scalar(
            self._session,
            select(ProjectRow).where(ProjectRow.project_id == record.project_id),
        )
        if row is None:
            raise JiejianError(ErrorCode.STORAGE_CONSTRAINT, "项目对象不存在")
        row.name = record.name
        row.status = record.status.value
        row.source_path = record.source_path
        row.source_hash = record.source_hash
        row.active_contract_path = record.active_contract_path
        row.active_contract_hash = record.active_contract_hash
        row.governed_contract_id = record.governed_contract_id
        row.governed_contract_version = record.governed_contract_version
        row.updated_at_us = record.updated_at_us
        _flush(self._session)

    @staticmethod
    def _record(row: ProjectRow) -> ProjectRecord:
        return ProjectRecord(
            project_id=row.project_id,
            name=row.name,
            status=ProjectStatus(row.status),
            source_path=row.source_path,
            source_hash=row.source_hash,
            active_contract_path=row.active_contract_path,
            active_contract_hash=row.active_contract_hash,
            governed_contract_id=row.governed_contract_id,
            governed_contract_version=row.governed_contract_version,
            created_at_us=row.created_at_us,
            updated_at_us=row.updated_at_us,
        )
