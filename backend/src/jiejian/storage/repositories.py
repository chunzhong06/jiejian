"""阶段 2.1 的持久化 DTO 与具体 Repository。"""

from __future__ import annotations

import hashlib
import json
import re
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

from ..domain.identifiers import (
    EVIDENCE_ID_PATTERN,
    JOB_ID_PATTERN,
    PROJECT_ID_PATTERN,
    RECORDING_ID_PATTERN,
    RUN_ID_PATTERN,
    SHA256_PATTERN,
)
from ..domain.lifecycle import JobState, ProjectStatus, RunLifecycle, RunVerdict
from ..domain.recording import (
    Recording,
    RecordingState,
    RecordingStateEvent,
    RecordingTerminalState,
)
from ..errors import ErrorCode, JiejianError
from ..protocols import (
    STAGED_ARTIFACT_MAX_BYTES,
    FlowDraftV1,
    RecordingEventKind,
    RecordingEventV1,
    RecordingHeaderV1,
    StagedArtifactV1,
    canonical_flow_draft_json_bytes,
)
from .models import (
    EvidenceIndexRow,
    FlowDraftRevisionRow,
    JobEventRow,
    JobRow,
    ProjectRow,
    RecordingRow,
    RunRow,
)

_METADATA_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SENSITIVE_METADATA_KEY = re.compile(
    r"(?:authorization|cookie|credential|password|passwd|secret|token|api[_-]?key)",
    re.IGNORECASE,
)
_INLINE_SECRET = re.compile(
    r"(?:\bBearer\s+\S+|\b(?:authorization|cookie|credential|password|passwd|"
    r"secret|token|api[_-]?key)\s*[:=]\s*\S+)",
    re.IGNORECASE,
)

MetadataValue = str | int | bool | None


class StorageRecord(BaseModel):
    """不向调用方泄露 ORM 对象的冻结数据结构。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    schema_version: Literal["1"] = "1"


class ProjectRecord(StorageRecord):
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    name: str = Field(min_length=1, max_length=128)
    status: ProjectStatus
    created_at_us: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_time_order(self) -> ProjectRecord:
        if self.updated_at_us < self.created_at_us:
            raise ValueError("project update time precedes creation")
        return self


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


class RecordingRecord(StorageRecord):
    recording_id: str = Field(pattern=RECORDING_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    flow_id: str = Field(pattern=PROJECT_ID_PATTERN)
    state: RecordingState
    created_at_us: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)
    started_at_us: int | None = Field(default=None, ge=0)
    capture_finished_at_us: int | None = Field(default=None, ge=0)
    finished_at_us: int | None = Field(default=None, ge=0)
    pending_terminal_state: RecordingTerminalState | None = None
    reason_codes: tuple[str, ...] = Field(default=(), max_length=64)
    state_events: tuple[RecordingStateEvent, ...] = Field(default=(), max_length=128)
    browser_events: tuple[RecordingEventV1, ...] = Field(default=(), max_length=10_000)

    @model_validator(mode="after")
    def validate_recording_lifecycle(self) -> RecordingRecord:
        self.to_domain()
        if tuple(event.sequence for event in self.browser_events) != tuple(
            range(1, len(self.browser_events) + 1)
        ):
            raise ValueError("recording browser event sequence must be continuous")
        return self

    def to_domain(self) -> Recording:
        return Recording(
            schema_version="1",
            recording_id=self.recording_id,
            project_id=self.project_id,
            state=self.state,
            created_at_us=self.created_at_us,
            updated_at_us=self.updated_at_us,
            started_at_us=self.started_at_us,
            capture_finished_at_us=self.capture_finished_at_us,
            finished_at_us=self.finished_at_us,
            pending_terminal_state=self.pending_terminal_state,
            reason_codes=self.reason_codes,
            events=self.state_events,
        )

    @classmethod
    def from_domain(
        cls,
        recording: Recording,
        *,
        flow_id: str,
        browser_events: tuple[RecordingEventV1, ...] = (),
    ) -> RecordingRecord:
        return cls(
            recording_id=recording.recording_id,
            project_id=recording.project_id,
            flow_id=flow_id,
            state=recording.state,
            created_at_us=recording.created_at_us,
            updated_at_us=recording.updated_at_us,
            started_at_us=recording.started_at_us,
            capture_finished_at_us=recording.capture_finished_at_us,
            finished_at_us=recording.finished_at_us,
            pending_terminal_state=recording.pending_terminal_state,
            reason_codes=recording.reason_codes,
            state_events=recording.events,
            browser_events=browser_events,
        )


class FlowDraftRevisionRecord(StorageRecord):
    recording_id: str = Field(pattern=RECORDING_ID_PATTERN)
    revision: int = Field(ge=1)
    flow_id: str = Field(pattern=PROJECT_ID_PATTERN)
    draft: FlowDraftV1
    draft_sha256: str = Field(pattern=SHA256_PATTERN)
    created_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_draft_identity(self) -> FlowDraftRevisionRecord:
        if self.draft.recording_id != self.recording_id:
            raise ValueError("flow draft recording ID is inconsistent")
        if self.draft.revision != self.revision or self.draft.flow_id != self.flow_id:
            raise ValueError("flow draft revision identity is inconsistent")
        digest = hashlib.sha256(canonical_flow_draft_json_bytes(self.draft)).hexdigest()
        if digest != self.draft_sha256:
            raise ValueError("flow draft hash is inconsistent")
        return self


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
            created_at_us=row.created_at_us,
            updated_at_us=row.updated_at_us,
        )


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


class RecordingRepository:
    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def add(self, record: RecordingRecord) -> None:
        ensure_storage_payload_safe(
            record.model_dump(mode="json"), self._known_secrets
        )
        self._session.add(self._row(record))
        _flush(self._session)

    def replace(self, record: RecordingRecord) -> None:
        ensure_storage_payload_safe(
            record.model_dump(mode="json"), self._known_secrets
        )
        row = _scalar(
            self._session,
            select(RecordingRow).where(
                RecordingRow.recording_id == record.recording_id
            ),
        )
        if row is None:
            raise JiejianError(ErrorCode.STORAGE_CONSTRAINT, "录制对象不存在")
        values = self._row_values(record)
        for name, value in values.items():
            setattr(row, name, value)
        _flush(self._session)

    def get(self, recording_id: str) -> RecordingRecord | None:
        row = _scalar(
            self._session,
            select(RecordingRow).where(RecordingRow.recording_id == recording_id),
        )
        return self._record(row) if row is not None else None

    def _row(self, record: RecordingRecord) -> RecordingRow:
        return RecordingRow(
            recording_id=record.recording_id,
            project_id=record.project_id,
            flow_id=record.flow_id,
            **self._row_values(record),
        )

    @staticmethod
    def _row_values(record: RecordingRecord) -> dict[str, Any]:
        return {
            "state": record.state.value,
            "created_at_us": record.created_at_us,
            "updated_at_us": record.updated_at_us,
            "started_at_us": record.started_at_us,
            "capture_finished_at_us": record.capture_finished_at_us,
            "finished_at_us": record.finished_at_us,
            "pending_terminal_state": (
                record.pending_terminal_state.value
                if record.pending_terminal_state is not None
                else None
            ),
            "reason_codes_json": _canonical_json(record.reason_codes),
            "state_events_json": _canonical_json(
                tuple(event.model_dump(mode="json") for event in record.state_events)
            ),
            "browser_events_json": _canonical_json(
                tuple(event.model_dump(mode="json") for event in record.browser_events)
            ),
        }

    @staticmethod
    def _record(row: RecordingRow) -> RecordingRecord:
        return RecordingRecord(
            recording_id=row.recording_id,
            project_id=row.project_id,
            flow_id=row.flow_id,
            state=RecordingState(row.state),
            created_at_us=row.created_at_us,
            updated_at_us=row.updated_at_us,
            started_at_us=row.started_at_us,
            capture_finished_at_us=row.capture_finished_at_us,
            finished_at_us=row.finished_at_us,
            pending_terminal_state=(
                RecordingTerminalState(row.pending_terminal_state)
                if row.pending_terminal_state is not None
                else None
            ),
            reason_codes=tuple(json.loads(row.reason_codes_json)),
            state_events=tuple(
                RecordingStateEvent.model_validate(
                    {
                        **item,
                        "source": RecordingState(item["source"]),
                        "target": RecordingState(item["target"]),
                    },
                    strict=True,
                )
                for item in json.loads(row.state_events_json)
            ),
            browser_events=tuple(
                RecordingEventV1.model_validate(
                    {
                        **item,
                        "kind": RecordingEventKind(item["kind"]),
                        "headers": tuple(
                            RecordingHeaderV1.model_validate(header, strict=True)
                            for header in item.get("headers", ())
                        ),
                    },
                    strict=True,
                )
                for item in json.loads(row.browser_events_json)
            ),
        )


class FlowDraftRevisionRepository:
    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def add(self, record: FlowDraftRevisionRecord) -> None:
        payload = record.model_dump(mode="json")
        ensure_storage_payload_safe(payload, self._known_secrets)
        draft_json = canonical_flow_draft_json_bytes(
            record.draft,
            known_secrets=self._known_secrets,
        ).decode("utf-8")
        self._session.add(
            FlowDraftRevisionRow(
                recording_id=record.recording_id,
                revision=record.revision,
                flow_id=record.flow_id,
                draft_json=draft_json,
                draft_sha256=record.draft_sha256,
                created_at_us=record.created_at_us,
            )
        )
        _flush(self._session)

    def list_for_recording(
        self,
        recording_id: str,
    ) -> tuple[FlowDraftRevisionRecord, ...]:
        rows = _scalars(
            self._session,
            select(FlowDraftRevisionRow)
            .where(FlowDraftRevisionRow.recording_id == recording_id)
            .order_by(FlowDraftRevisionRow.revision),
        )
        return tuple(self._record(row) for row in rows)

    def latest(self, recording_id: str) -> FlowDraftRevisionRecord | None:
        row = _scalar(
            self._session,
            select(FlowDraftRevisionRow)
            .where(FlowDraftRevisionRow.recording_id == recording_id)
            .order_by(FlowDraftRevisionRow.revision.desc())
            .limit(1),
        )
        return self._record(row) if row is not None else None

    @staticmethod
    def _record(row: FlowDraftRevisionRow) -> FlowDraftRevisionRecord:
        draft = FlowDraftV1.model_validate_json(row.draft_json, strict=True)
        return FlowDraftRevisionRecord(
            recording_id=row.recording_id,
            revision=row.revision,
            flow_id=row.flow_id,
            draft=draft,
            draft_sha256=row.draft_sha256,
            created_at_us=row.created_at_us,
        )


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


def ensure_storage_payload_safe(value: Any, known_secrets: Sequence[str]) -> None:
    """在进入数据库前拒绝内联凭据和本次尝试的已知秘密。"""
    normalized = tuple(secret for secret in known_secrets if secret)
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, Mapping):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, (list, tuple)):
            pending.extend(item)
        elif isinstance(item, str) and (
            _INLINE_SECRET.search(item) is not None
            or any(secret in item for secret in normalized)
        ):
            raise JiejianError(ErrorCode.STORAGE_SECRET, "持久化数据包含敏感内容")


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError):
        raise JiejianError(ErrorCode.STORAGE_CONSTRAINT, "持久化 JSON 无效") from None


def _flush(session: Session) -> None:
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise JiejianError(
            ErrorCode.STORAGE_CONSTRAINT,
            "数据库约束拒绝写入",
        ) from None
    except SQLAlchemyError:
        session.rollback()
        raise JiejianError(ErrorCode.STORAGE_FAILURE, "数据库操作失败") from None


def _scalar(session: Session, statement: Select[Any]) -> Any | None:
    try:
        return session.execute(statement).scalar_one_or_none()
    except SQLAlchemyError:
        session.rollback()
        raise JiejianError(ErrorCode.STORAGE_FAILURE, "数据库操作失败") from None


def _scalars(session: Session, statement: Select[Any]) -> tuple[Any, ...]:
    try:
        return tuple(session.execute(statement).scalars())
    except SQLAlchemyError:
        session.rollback()
        raise JiejianError(ErrorCode.STORAGE_FAILURE, "数据库操作失败") from None
