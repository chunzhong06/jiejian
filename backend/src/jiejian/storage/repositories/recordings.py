# =============================================================================
# Recording 聚合仓储
#
# 定位
#   Recording、事件、审阅和 FlowDraft 的持久化适配器
#
# 职责
#   保存脱敏录制数据｜保持审阅版本｜提供 Recording 聚合读取
#
# 调用链
#   Recording services → Recording repositories → Recording ORM rows
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

    def list_for_project(self, project_id: str) -> tuple[RecordingRecord, ...]:
        rows = _scalars(

            self._session,
            select(RecordingRow)
            .where(RecordingRow.project_id == project_id)
            .order_by(RecordingRow.created_at_us.desc(), RecordingRow.recording_id),
        )
        return tuple(self._record(row) for row in rows)

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
