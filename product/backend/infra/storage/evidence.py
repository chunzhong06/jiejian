# Evidence 索引的 SQLAlchemy 映射；同一用例可产生多份证据，唯一性由内容地址和工件路径约束。

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from product.backend.infra.storage.base import Base

class EvidenceIndexRow(Base):
    __tablename__ = "evidence_index"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "artifact_path",
            name="uq_evidence_run_artifact_path",
        ),
        CheckConstraint(
            "length(evidence_id) BETWEEN 23 AND 67 "
            "AND substr(evidence_id, 1, 3) = 'ev_' "

            "AND substr(evidence_id, 4) NOT GLOB '*[^0-9a-f]*'",
            name="evidence_id_format",
        ),
        CheckConstraint(
            "length(case_id) BETWEEN 1 AND 128",
            name="case_id_length",
        ),
        CheckConstraint(
            "length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'",
            name="sha256_format",
        ),
        CheckConstraint(
            "substr(sha256, 1, length(evidence_id) - 3) = substr(evidence_id, 4)",
            name="content_address_match",
        ),
        CheckConstraint(
            "length(artifact_path) BETWEEN 1 AND 512 "
            "AND substr(artifact_path, 1, 1) <> '/' "
            "AND instr(artifact_path, '\\') = 0 "
            "AND instr(artifact_path, ':') = 0 "
            "AND instr(artifact_path, char(0)) = 0 "
            "AND artifact_path NOT LIKE '%//%'",
            name="artifact_path_basic",
        ),
        CheckConstraint(
            "byte_count BETWEEN 0 AND 1073741824",
            name="byte_count_bounds",
        ),
        CheckConstraint("created_at_us >= 0", name="created_nonnegative"),
        Index("ix_evidence_run_created", "run_id", "created_at_us"),
    )

    evidence_id: Mapped[str] = mapped_column(String(67), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.run_id", ondelete="RESTRICT"),
        nullable=False,
    )
    case_id: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_path: Mapped[str] = mapped_column(
        String(512, collation="NOCASE"),
        nullable=False,
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)

# 本聚合的 Repository 与持久化记录边界。

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

from product.backend.core.identifiers import EVIDENCE_ID_PATTERN, JOB_ID_PATTERN, PROJECT_ID_PATTERN, RECORDING_ID_PATTERN, RUN_ID_PATTERN, SHA256_PATTERN
from product.backend.core.contracts.models import ContractAuditEntry, ContractCandidate, ContractProvenance, ContractSourceType, ContractVersion, LLMGenerationMetadata, Requirement, SourceReference
from product.backend.core.lifecycle import JobState, ProjectStatus, RunLifecycle, RunVerdict
from product.backend.core.lifecycle import ContractStatus
from product.backend.core.contracts.models import CandidateSuggestion
from product.backend.core.verification.permissions import PermissionContract
from product.backend.core.recording import Recording, RecordingState, RecordingStateEvent, RecordingTerminalState
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import STAGED_ARTIFACT_MAX_BYTES, FlowDraft, RecordingEventKind, RecordingEvent, RecordingHeader, StagedArtifact, canonical_flow_draft_json_bytes
from product.backend.infra.storage.contracts import ContractCandidateRow, ContractVersionRow, RequirementRow
from product.backend.infra.storage.recordings import FlowDraftRevisionRow, RecordingRow
from product.backend.infra.storage.jobs import JobEventRow, JobRow
from product.backend.infra.storage.projects import ProjectRow
from product.backend.infra.storage.runs import RunRow
from product.backend.infra.storage.base import MetadataValue, StorageRecord, _METADATA_KEY, _SENSITIVE_METADATA_KEY, _canonical_json, _flush, _scalar, _scalars, ensure_storage_payload_safe

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
        StagedArtifact(
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
