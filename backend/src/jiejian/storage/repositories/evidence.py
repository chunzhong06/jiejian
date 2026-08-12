# =============================================================================
# Evidence 索引仓储
#
# 定位
#   已发布 Evidence 元数据与内容摘要的持久化适配器
#
# 职责
#   写入证据索引｜保持 Run 关联与排序｜读取发布后的完整性元数据
#
# 调用链
#   Publication / Results → EvidenceIndexRepository → Evidence ORM rows
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

class EvidenceIndexRecord(StorageRecord):
    evidence_id: str = Field(pattern=EVIDENCE_ID_PATTERN)
    run_id: str = Field(pattern=RUN_ID_PATTERN)
    case_id: str = Field(min_length=1, max_length=128)
    artifact_path: str = Field(min_length=1, max_length=512)
    sha256: str = Field(pattern=SHA256_PATTERN)
    byte_count: int = Field(ge=0, le=STAGED_ARTIFACT_MAX_BYTES)
    created_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_content_address_and_path(self) -> EvidenceIndexRecord:
        StagedArtifactV1(
            schema_version="1",
            path=self.artifact_path,
            byte_count=self.byte_count,
            sha256=self.sha256,
        )
        if self.evidence_id[3:] != self.sha256[: len(self.evidence_id) - 3]:
            raise ValueError("evidence ID does not match its content hash")
        return self
class EvidenceIndexRepository:
    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def add(self, record: EvidenceIndexRecord) -> None:
        ensure_storage_payload_safe(
            record.model_dump(mode="json"), self._known_secrets
        )
        self._session.add(
            EvidenceIndexRow(
                evidence_id=record.evidence_id,
                run_id=record.run_id,
                case_id=record.case_id,
                artifact_path=record.artifact_path,
                sha256=record.sha256,
                byte_count=record.byte_count,
                created_at_us=record.created_at_us,
            )
        )
        _flush(self._session)

    def list_for_run(self, run_id: str) -> tuple[EvidenceIndexRecord, ...]:
        rows = _scalars(
            self._session,
            select(EvidenceIndexRow)
            .where(EvidenceIndexRow.run_id == run_id)
            .order_by(EvidenceIndexRow.created_at_us, EvidenceIndexRow.evidence_id),
        )
        return tuple(
            EvidenceIndexRecord(
                evidence_id=row.evidence_id,
                run_id=row.run_id,
                case_id=row.case_id,
                artifact_path=row.artifact_path,
                sha256=row.sha256,
                byte_count=row.byte_count,
                created_at_us=row.created_at_us,
            )
            for row in rows
        )
