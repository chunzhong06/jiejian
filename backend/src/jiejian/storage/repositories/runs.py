# =============================================================================
# Verification Run 仓储
#
# 定位
#   Run 生命周期、冻结快照和 Verdict 的持久化适配器
#
# 职责
#   保存 Run 记录｜保持生命周期与结论分离｜提供结果和恢复读取
#
# 调用链
#   Execution / Results → RunRepository → Run ORM rows
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

class RunRecord(StorageRecord):
    run_id: str = Field(pattern=RUN_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    contract_id: str = Field(min_length=1, max_length=128)
    contract_version: int = Field(ge=1)
    engine_version: str = Field(min_length=1, max_length=64)
    lifecycle: RunLifecycle
    verdict: RunVerdict | None = None
    created_at_us: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)
    finished_at_us: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_run_matrix(self) -> RunRecord:
        if (self.lifecycle is RunLifecycle.COMPLETED) != (self.verdict is not None):
            raise ValueError("run lifecycle and verdict are inconsistent")
        if self.updated_at_us < self.created_at_us:
            raise ValueError("run update time precedes creation")
        if self.finished_at_us is not None and self.finished_at_us < self.created_at_us:
            raise ValueError("run finish time precedes creation")
        return self
class RunRepository:
    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def add(self, record: RunRecord) -> None:
        ensure_storage_payload_safe(

            record.model_dump(mode="json"), self._known_secrets
        )
        self._session.add(
            RunRow(
                run_id=record.run_id,
                project_id=record.project_id,
                contract_id=record.contract_id,
                contract_version=record.contract_version,
                engine_version=record.engine_version,
                lifecycle=record.lifecycle.value,
                verdict=record.verdict.value if record.verdict is not None else None,
                created_at_us=record.created_at_us,
                updated_at_us=record.updated_at_us,
                finished_at_us=record.finished_at_us,
            )
        )
        _flush(self._session)

    def get(self, run_id: str) -> RunRecord | None:
        row = _scalar(
            self._session,
            select(RunRow).where(RunRow.run_id == run_id),
        )
        if row is None:
            return None
        return RunRecord(
            run_id=row.run_id,
            project_id=row.project_id,
            contract_id=row.contract_id,
            contract_version=row.contract_version,
            engine_version=row.engine_version,
            lifecycle=RunLifecycle(row.lifecycle),
            verdict=RunVerdict(row.verdict) if row.verdict is not None else None,
            created_at_us=row.created_at_us,
            updated_at_us=row.updated_at_us,
            finished_at_us=row.finished_at_us,
        )
    def list_for_project(self, project_id: str) -> tuple[RunRecord, ...]:
        rows = _scalars(
            self._session,
            select(RunRow)
            .where(RunRow.project_id == project_id)
            .order_by(RunRow.created_at_us.desc(), RunRow.run_id),
        )
        return tuple(
            RunRecord(
                run_id=row.run_id,
                project_id=row.project_id,
                contract_id=row.contract_id,
                contract_version=row.contract_version,
                engine_version=row.engine_version,
                lifecycle=RunLifecycle(row.lifecycle),
                verdict=RunVerdict(row.verdict) if row.verdict is not None else None,
                created_at_us=row.created_at_us,
                updated_at_us=row.updated_at_us,
                finished_at_us=row.finished_at_us,
            )
            for row in rows
        )
