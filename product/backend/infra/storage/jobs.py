# Storage 的 SQLAlchemy typed declarative 映射。

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from product.backend.infra.storage.base import Base

class JobRow(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_jobs_run_id"),
        UniqueConstraint("recording_id", name="uq_jobs_recording_id"),
        UniqueConstraint(
            "project_id",
            "operation_type",
            "idempotency_key",
            name="uq_jobs_idempotency_scope",
        ),
        CheckConstraint(
            "length(job_id) = 36 AND substr(job_id, 1, 4) = 'job_' "
            "AND substr(job_id, 5) NOT GLOB '*[^0-9a-f]*'",
            name="job_id_format",
        ),
        CheckConstraint(
            "length(operation_type) BETWEEN 1 AND 64 "
            "AND operation_type NOT GLOB '*[^A-Z0-9_]*'",
            name="operation_type_format",
        ),
        CheckConstraint(
            "(run_id IS NOT NULL AND recording_id IS NULL) OR "
            "(run_id IS NULL AND recording_id IS NOT NULL)",
            name="exactly_one_target",
        ),
        CheckConstraint(
            "state IN ('PENDING', 'RUNNING', 'RETRY_WAIT', 'SUCCEEDED', "
            "'FAILED', 'CANCELLED')",
            name="state_value",
        ),
        CheckConstraint(
            "length(idempotency_key) BETWEEN 1 AND 128",
            name="idempotency_key_length",
        ),
        CheckConstraint(
            "length(request_hash) = 64 "
            "AND request_hash NOT GLOB '*[^0-9a-f]*'",
            name="request_hash_format",
        ),
        CheckConstraint(
            "attempt >= 0 AND max_attempts >= 1 AND attempt <= max_attempts",
            name="attempt_bounds",
        ),
        CheckConstraint("fencing_token >= 0", name="fencing_nonnegative"),
        CheckConstraint(
            "(attempt = 0 AND fencing_token = 0 AND lease_owner IS NULL "
            "AND lease_expires_at_us IS NULL) OR "
            "(attempt > 0 AND fencing_token > 0)",
            name="attempt_fencing_relation",
        ),
        CheckConstraint(
            "(lease_owner IS NULL AND lease_expires_at_us IS NULL) OR "
            "(lease_owner IS NOT NULL AND lease_expires_at_us IS NOT NULL)",
            name="lease_pair",
        ),
        CheckConstraint(

            "state <> 'RUNNING' OR (lease_owner IS NOT NULL "
            "AND fencing_token > 0 AND lease_expires_at_us IS NOT NULL)",
            name="running_lease_required",
        ),
        CheckConstraint(
            "lease_owner IS NULL OR (length(lease_owner) BETWEEN 1 AND 128 "
            "AND lease_owner NOT GLOB '*[^A-Za-z0-9._:-]*')",
            name="lease_owner_format",
        ),
        CheckConstraint(
            "created_at_us >= 0 AND updated_at_us >= created_at_us "
            "AND available_at_us >= 0 "
            "AND (lease_expires_at_us IS NULL OR lease_expires_at_us >= 0) "
            "AND (cancel_requested_at_us IS NULL "
            "OR cancel_requested_at_us >= created_at_us)",
            name="time_bounds",
        ),
        Index("ix_jobs_state_available", "state", "available_at_us"),
        Index("ix_jobs_state_lease_expires", "state", "lease_expires_at_us"),
    )

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="RESTRICT"),
        nullable=False,
    )
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("runs.run_id", ondelete="RESTRICT"),
        nullable=True,
    )
    recording_id: Mapped[str | None] = mapped_column(
        ForeignKey("recordings.recording_id", ondelete="RESTRICT"),
        nullable=True,
    )
    operation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    available_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    fencing_token: Mapped[int] = mapped_column(BigInteger, nullable=False)
    lease_expires_at_us: Mapped[int | None] = mapped_column(BigInteger)
    cancel_requested_at_us: Mapped[int | None] = mapped_column(BigInteger)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
class JobEventRow(Base):
    __tablename__ = "job_events"
    __table_args__ = (
        CheckConstraint("sequence >= 1", name="sequence_positive"),
        CheckConstraint(
            "length(event_type) BETWEEN 1 AND 64 "
            "AND event_type NOT GLOB '*[^A-Z0-9_]*'",
            name="event_type_format",
        ),
        CheckConstraint(
            "source_state IS NULL OR source_state IN ('PENDING', 'RUNNING', "
            "'RETRY_WAIT', 'SUCCEEDED', 'FAILED', 'CANCELLED')",
            name="source_state_value",
        ),
        CheckConstraint(
            "target_state IS NULL OR target_state IN ('PENDING', 'RUNNING', "
            "'RETRY_WAIT', 'SUCCEEDED', 'FAILED', 'CANCELLED')",
            name="target_state_value",
        ),
        CheckConstraint("occurred_at_us >= 0", name="occurred_nonnegative"),
        CheckConstraint(
            "length(metadata_json) BETWEEN 2 AND 4096",
            name="metadata_length",
        ),
        Index("ix_job_events_job_occurred", "job_id", "occurred_at_us"),
    )

    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.job_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_state: Mapped[str | None] = mapped_column(String(16))
    target_state: Mapped[str | None] = mapped_column(String(16))
    occurred_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

# 本聚合的 Repository 与持久化记录边界。

# =============================================================================
# Job 与 Job Event 仓储
#
# 定位
#   Job 生命周期记录和有序审计事件的常规持久化适配器
#
# 职责
#   映射 Job 状态｜追加有序事件｜提供调度与恢复查询
#
# 调用链
#   Execution services → JobRepository / JobEventRepository → Job ORM rows
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
from product.backend.infra.storage.evidence import EvidenceIndexRow
from product.backend.infra.storage.recordings import FlowDraftRevisionRow, RecordingRow
from product.backend.infra.storage.projects import ProjectRow
from product.backend.infra.storage.runs import RunRow
from product.backend.infra.storage.base import MetadataValue, StorageRecord, _METADATA_KEY, _SENSITIVE_METADATA_KEY, _canonical_json, _flush, _scalar, _scalars, ensure_storage_payload_safe

class JobRecord(StorageRecord):
    job_id: str = Field(pattern=JOB_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    run_id: str | None = Field(default=None, pattern=RUN_ID_PATTERN)
    recording_id: str | None = Field(default=None, pattern=RECORDING_ID_PATTERN)
    operation_type: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    state: JobState
    idempotency_key: str = Field(min_length=1, max_length=128)
    request_hash: str = Field(pattern=SHA256_PATTERN)
    attempt: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    available_at_us: int = Field(ge=0)
    lease_owner: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    fencing_token: int = Field(ge=0)
    lease_expires_at_us: int | None = Field(default=None, ge=0)
    cancel_requested_at_us: int | None = Field(default=None, ge=0)
    created_at_us: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_job_fields(self) -> JobRecord:
        if (self.run_id is None) == (self.recording_id is None):
            raise ValueError("job must reference exactly one execution target")
        if self.attempt > self.max_attempts:
            raise ValueError("job attempt exceeds maximum")
        if self.attempt == 0 and (
            self.fencing_token != 0
            or self.lease_owner is not None
            or self.lease_expires_at_us is not None
        ):
            raise ValueError("unclaimed job contains lease fields")
        if self.attempt > 0 and self.fencing_token <= 0:
            raise ValueError("claimed job requires a fencing token")
        if (self.lease_owner is None) != (self.lease_expires_at_us is None):
            raise ValueError("job lease owner and expiry must be stored together")
        if self.state is JobState.RUNNING and (
            self.lease_owner is None
            or self.fencing_token <= 0
            or self.lease_expires_at_us is None
        ):
            raise ValueError("running job requires a lease")
        if self.updated_at_us < self.created_at_us:
            raise ValueError("job update time precedes creation")
        if (
            self.cancel_requested_at_us is not None
            and self.cancel_requested_at_us < self.created_at_us
        ):
            raise ValueError("cancel request time precedes creation")
        return self
class JobEventRecord(StorageRecord):
    job_id: str = Field(pattern=JOB_ID_PATTERN)
    sequence: int = Field(ge=1)
    event_type: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    source_state: JobState | None = None
    target_state: JobState | None = None
    occurred_at_us: int = Field(ge=0)
    metadata: Mapping[str, MetadataValue] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(
        cls,
        value: Mapping[str, MetadataValue],
    ) -> Mapping[str, MetadataValue]:
        if len(value) > 32:
            raise ValueError("job event metadata has too many entries")

        for key, item in value.items():
            is_fencing_token = key == "fencing_token" and type(item) is int
            if _METADATA_KEY.fullmatch(key) is None or (
                _SENSITIVE_METADATA_KEY.search(key) is not None
                and not is_fencing_token
            ):
                raise ValueError("job event metadata key is not stable")
            if isinstance(item, str) and len(item) > 256:
                raise ValueError("job event metadata value is too long")
        encoded = json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if len(encoded) > 4096:
            raise ValueError("job event metadata exceeds its byte limit")
        return dict(value)
class JobRepository:
    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def add(self, record: JobRecord) -> None:
        ensure_storage_payload_safe(
            record.model_dump(mode="json"), self._known_secrets
        )
        self._session.add(
            JobRow(
                job_id=record.job_id,
                project_id=record.project_id,
                run_id=record.run_id,
                recording_id=record.recording_id,
                operation_type=record.operation_type,
                state=record.state.value,
                idempotency_key=record.idempotency_key,
                request_hash=record.request_hash,
                attempt=record.attempt,
                max_attempts=record.max_attempts,
                available_at_us=record.available_at_us,
                lease_owner=record.lease_owner,
                fencing_token=record.fencing_token,
                lease_expires_at_us=record.lease_expires_at_us,
                cancel_requested_at_us=record.cancel_requested_at_us,
                created_at_us=record.created_at_us,
                updated_at_us=record.updated_at_us,
            )
        )
        _flush(self._session)

    def get(self, job_id: str) -> JobRecord | None:
        row = _scalar(
            self._session,
            select(JobRow).where(JobRow.job_id == job_id),
        )
        if row is None:
            return None
        return JobRecord(
            job_id=row.job_id,
            project_id=row.project_id,
            run_id=row.run_id,
            recording_id=row.recording_id,
            operation_type=row.operation_type,
            state=JobState(row.state),
            idempotency_key=row.idempotency_key,
            request_hash=row.request_hash,
            attempt=row.attempt,
            max_attempts=row.max_attempts,
            available_at_us=row.available_at_us,
            lease_owner=row.lease_owner,
            fencing_token=row.fencing_token,
            lease_expires_at_us=row.lease_expires_at_us,
            cancel_requested_at_us=row.cancel_requested_at_us,
            created_at_us=row.created_at_us,
            updated_at_us=row.updated_at_us,

        )
    def get_by_idempotency(
        self,
        project_id: str,
        operation_type: str,
        idempotency_key: str,
    ) -> JobRecord | None:
        job_id = _scalar(
            self._session,
            select(JobRow.job_id).where(
                JobRow.project_id == project_id,
                JobRow.operation_type == operation_type,
                JobRow.idempotency_key == idempotency_key,
            ),
        )
        return self.get(job_id) if job_id is not None else None

    def get_by_run(self, run_id: str) -> JobRecord | None:
        job_id = _scalar(self._session, select(JobRow.job_id).where(JobRow.run_id == run_id))
        return self.get(job_id) if job_id is not None else None

    def get_by_recording(self, recording_id: str) -> JobRecord | None:
        job_id = _scalar(self._session, select(JobRow.job_id).where(JobRow.recording_id == recording_id))
        return self.get(job_id) if job_id is not None else None

    def next_pending(self, now_us: int | None = None) -> JobRecord | None:
        current = time.time_ns() // 1_000 if now_us is None else now_us
        row = _scalar(
            self._session,
            select(JobRow)
            .where(JobRow.state == JobState.PENDING.value, JobRow.available_at_us <= current)
            .order_by(JobRow.created_at_us, JobRow.job_id)
            .limit(1),
        )
        if row is None:
            return None
        return self._record(row)

    @staticmethod
    def _record(row: JobRow) -> JobRecord:
        return JobRecord(
            job_id=row.job_id,
            project_id=row.project_id,
            run_id=row.run_id,
            recording_id=row.recording_id,
            operation_type=row.operation_type,
            state=JobState(row.state),
            idempotency_key=row.idempotency_key,
            request_hash=row.request_hash,
            attempt=row.attempt,
            max_attempts=row.max_attempts,
            available_at_us=row.available_at_us,
            lease_owner=row.lease_owner,
            fencing_token=row.fencing_token,
            lease_expires_at_us=row.lease_expires_at_us,
            cancel_requested_at_us=row.cancel_requested_at_us,
            created_at_us=row.created_at_us,
            updated_at_us=row.updated_at_us,
        )
class JobEventRepository:
    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def append(self, record: JobEventRecord) -> None:
        payload = record.model_dump(mode="json")
        ensure_storage_payload_safe(payload, self._known_secrets)
        latest = _scalar(
            self._session,
            select(func.max(JobEventRow.sequence)).where(
                JobEventRow.job_id == record.job_id
            ),
        )
        if record.sequence != (latest or 0) + 1:
            raise JiejianError(
                ErrorCode.STORAGE_CONSTRAINT,
                "任务事件必须按连续序号追加",
            )
        metadata_json = json.dumps(
            dict(record.metadata),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        self._session.add(
            JobEventRow(
                job_id=record.job_id,
                sequence=record.sequence,
                event_type=record.event_type,
                source_state=(
                    record.source_state.value
                    if record.source_state is not None
                    else None
                ),
                target_state=(
                    record.target_state.value

                    if record.target_state is not None
                    else None
                ),
                occurred_at_us=record.occurred_at_us,
                metadata_json=metadata_json,
            )
        )
        _flush(self._session)

    def list_for_job(self, job_id: str) -> tuple[JobEventRecord, ...]:
        rows = _scalars(
            self._session,
            select(JobEventRow)
            .where(JobEventRow.job_id == job_id)
            .order_by(JobEventRow.sequence),
        )
        return tuple(
            JobEventRecord(
                job_id=row.job_id,
                sequence=row.sequence,
                event_type=row.event_type,
                source_state=(
                    JobState(row.source_state) if row.source_state is not None else None
                ),
                target_state=(
                    JobState(row.target_state) if row.target_state is not None else None
                ),
                occurred_at_us=row.occurred_at_us,
                metadata=json.loads(row.metadata_json),
            )
            for row in rows
        )
