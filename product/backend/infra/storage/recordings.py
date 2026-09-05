# Storage 的 SQLAlchemy typed declarative 映射。

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from product.backend.infra.storage.base import Base

class RecordingRow(Base):
    __tablename__ = "recordings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["business_action_id", "action_revision"],
            ["business_action_revisions.action_id", "business_action_revisions.revision"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("action_revision >= 1", name="action_revision_positive"),
        CheckConstraint(
            "(purpose = 'TARGET' AND parent_recording_id IS NULL AND effect_id IS NULL) OR "
            "(purpose = 'OBSERVATION' AND parent_recording_id IS NOT NULL AND effect_id IS NOT NULL) OR "
            "(purpose = 'RECOVERY' AND parent_recording_id IS NOT NULL AND effect_id IS NULL)",
            name="purpose_context_matrix",
        ),
        CheckConstraint(
            "length(recording_id) = 36 AND substr(recording_id, 1, 4) = 'rec_' "
            "AND substr(recording_id, 5) NOT GLOB '*[^0-9a-f]*'",
            name="recording_id_format",
        ),
        CheckConstraint(
            "state IN ('CREATED', 'STARTING', 'RECORDING', 'CLEANING', "
            "'PROCESSING', 'PENDING_REVIEW', 'COMPLETED', 'FAILED', "
            "'CANCELLED', 'SAFETY_STOPPED')",
            name="state_value",
        ),
        CheckConstraint(
            "length(flow_id) BETWEEN 1 AND 64 "
            "AND substr(flow_id, 1, 1) GLOB '[a-z]' "
            "AND flow_id NOT GLOB '*[^a-z0-9_-]*'",
            name="flow_id_format",
        ),
        CheckConstraint(
            "pending_terminal_state IS NULL OR pending_terminal_state IN "
            "('FAILED', 'CANCELLED', 'SAFETY_STOPPED')",
            name="pending_terminal_state_value",
        ),
        CheckConstraint(
            "created_at_us >= 0 AND updated_at_us >= created_at_us "
            "AND (started_at_us IS NULL OR started_at_us >= created_at_us) "
            "AND (capture_finished_at_us IS NULL OR "
            "capture_finished_at_us >= started_at_us) "
            "AND (finished_at_us IS NULL OR finished_at_us >= updated_at_us)",
            name="time_order",
        ),
        CheckConstraint(
            "(state IN ('COMPLETED', 'FAILED', 'CANCELLED', 'SAFETY_STOPPED') "
            "AND finished_at_us IS NOT NULL) OR "
            "(state NOT IN ('COMPLETED', 'FAILED', 'CANCELLED', "
            "'SAFETY_STOPPED') AND finished_at_us IS NULL)",
            name="terminal_finish_matrix",
        ),
        CheckConstraint(
            "length(reason_codes_json) BETWEEN 2 AND 8192 "
            "AND length(state_events_json) BETWEEN 2 AND 131072 "
            "AND length(browser_events_json) BETWEEN 2 AND 4194304",
            name="json_size_bounds",
        ),
        Index("ix_recordings_project_created", "project_id", "created_at_us"),
        Index("ix_recordings_parent_purpose", "parent_recording_id", "purpose"),
        Index("ix_recordings_state_updated", "state", "updated_at_us"),
    )

    recording_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="RESTRICT"),
        nullable=False,
    )
    business_action_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    preparation_source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    test_identity_id: Mapped[str] = mapped_column(
        # 保留录制时的身份来源；账号可被删除，实时可用性由 preparation 检查。
        String(36), nullable=False,
    )
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)
    parent_recording_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("recordings.recording_id", ondelete="RESTRICT"),
    )
    effect_id: Mapped[str | None] = mapped_column(String(36))
    flow_id: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    started_at_us: Mapped[int | None] = mapped_column(BigInteger)
    capture_finished_at_us: Mapped[int | None] = mapped_column(BigInteger)
    finished_at_us: Mapped[int | None] = mapped_column(BigInteger)
    pending_terminal_state: Mapped[str | None] = mapped_column(String(24))
    reason_codes_json: Mapped[str] = mapped_column(Text, nullable=False)
    state_events_json: Mapped[str] = mapped_column(Text, nullable=False)
    browser_events_json: Mapped[str] = mapped_column(Text, nullable=False)
class FlowDraftRevisionRow(Base):
    __tablename__ = "flow_draft_revisions"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(
            "length(flow_id) BETWEEN 1 AND 64 "
            "AND substr(flow_id, 1, 1) GLOB '[a-z]' "
            "AND flow_id NOT GLOB '*[^a-z0-9_-]*'",
            name="flow_id_format",
        ),
        CheckConstraint(
            "length(draft_sha256) = 64 "
            "AND draft_sha256 NOT GLOB '*[^0-9a-f]*'",
            name="draft_sha256_format",
        ),
        CheckConstraint(
            "length(draft_json) BETWEEN 2 AND 4194304",
            name="draft_json_size",
        ),

        CheckConstraint("created_at_us >= 0", name="created_nonnegative"),
        Index("ix_flow_drafts_flow_created", "flow_id", "created_at_us"),
    )

    recording_id: Mapped[str] = mapped_column(
        ForeignKey("recordings.recording_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    flow_id: Mapped[str] = mapped_column(String(64), nullable=False)
    draft_json: Mapped[str] = mapped_column(Text, nullable=False)
    draft_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)

# 本聚合的 Repository 与持久化记录边界。

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
from product.backend.core.lifecycle import JobState, ProjectStatus, RunLifecycle, RunVerdict
from product.backend.core.lifecycle import ContractStatus
from product.backend.core.verification.permissions import PermissionContract
from product.backend.core.recording import Recording, RecordingPurpose, RecordingState, RecordingStateEvent, RecordingTerminalState
from product.backend.core.business_boundary import ACTION_ID_PATTERN, EFFECT_ID_PATTERN
from product.backend.core.identifiers import TEST_IDENTITY_ID_PATTERN
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import STAGED_ARTIFACT_MAX_BYTES, FlowDraft, RecordingEventKind, RecordingEvent, RecordingHeader, StagedArtifact, canonical_flow_draft_json_bytes
from product.backend.infra.storage.base import MetadataValue, StorageRecord, _METADATA_KEY, _SENSITIVE_METADATA_KEY, _canonical_json, _flush, _scalar, _scalars, ensure_storage_payload_safe

class RecordingRecord(StorageRecord):
    recording_id: str = Field(pattern=RECORDING_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    business_action_id: str = Field(pattern=ACTION_ID_PATTERN)
    action_revision: int = Field(ge=1)
    test_identity_id: str = Field(pattern=TEST_IDENTITY_ID_PATTERN)
    preparation_source_fingerprint: str = Field(pattern=SHA256_PATTERN)
    purpose: RecordingPurpose = RecordingPurpose.TARGET
    parent_recording_id: str | None = Field(default=None, pattern=RECORDING_ID_PATTERN)
    effect_id: str | None = Field(default=None, pattern=EFFECT_ID_PATTERN)
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
    browser_events: tuple[RecordingEvent, ...] = Field(default=(), max_length=10_000)

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
            recording_id=self.recording_id,
            project_id=self.project_id,
            business_action_id=self.business_action_id,
            action_revision=self.action_revision,
            test_identity_id=self.test_identity_id,
            preparation_source_fingerprint=self.preparation_source_fingerprint,
            effect_id=self.effect_id,
            purpose=self.purpose,
            parent_recording_id=self.parent_recording_id,
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
        browser_events: tuple[RecordingEvent, ...] = (),
    ) -> RecordingRecord:
        return cls(
            recording_id=recording.recording_id,
            project_id=recording.project_id,
            business_action_id=recording.business_action_id,
            action_revision=recording.action_revision,
            test_identity_id=recording.test_identity_id,
            preparation_source_fingerprint=recording.preparation_source_fingerprint,
            effect_id=recording.effect_id,
            purpose=recording.purpose,
            parent_recording_id=recording.parent_recording_id,
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
    draft: FlowDraft
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
        # 生命周期更新不能顺带更换已提交的业务来源。
        for name in ("project_id", "business_action_id", "action_revision", "test_identity_id",
                     "purpose", "parent_recording_id", "effect_id", "flow_id", "preparation_source_fingerprint"):
            if getattr(row, name) != getattr(record, name):
                raise JiejianError(ErrorCode.STORAGE_CONSTRAINT, "录制来源不可更换")
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
            business_action_id=record.business_action_id,
            action_revision=record.action_revision,
            test_identity_id=record.test_identity_id,
            preparation_source_fingerprint=record.preparation_source_fingerprint,
            effect_id=record.effect_id,
            flow_id=record.flow_id,
            purpose=record.purpose.value,
            parent_recording_id=record.parent_recording_id,
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
            business_action_id=row.business_action_id,
            action_revision=row.action_revision,
            test_identity_id=row.test_identity_id,
            preparation_source_fingerprint=row.preparation_source_fingerprint,
            effect_id=row.effect_id,
            purpose=RecordingPurpose(row.purpose),
            parent_recording_id=row.parent_recording_id,
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
                RecordingEvent.model_validate(
                    {
                        **item,
                        "kind": RecordingEventKind(item["kind"]),
                        "headers": tuple(
                            RecordingHeader.model_validate(header, strict=True)
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
        draft = FlowDraft.model_validate_json(row.draft_json, strict=True)
        return FlowDraftRevisionRecord(
            recording_id=row.recording_id,
            revision=row.revision,
            flow_id=row.flow_id,
            draft=draft,
            draft_sha256=row.draft_sha256,
            created_at_us=row.created_at_us,
        )
