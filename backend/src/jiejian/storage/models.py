"""阶段 2.1 的 SQLAlchemy typed declarative 映射。"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class ProjectRow(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            "length(project_id) BETWEEN 1 AND 64 "
            "AND substr(project_id, 1, 1) GLOB '[a-z]' "
            "AND project_id NOT GLOB '*[^a-z0-9_-]*'",
            name="project_id_format",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'READY', 'ARCHIVED')",
            name="status_value",
        ),
        CheckConstraint("length(name) BETWEEN 1 AND 128", name="name_length"),
        CheckConstraint(
            "created_at_us >= 0 AND updated_at_us >= created_at_us",
            name="time_order",
        ),
        Index("ix_projects_status_updated", "status", "updated_at_us"),
    )

    project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class RunRow(Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(
            "length(run_id) = 36 AND substr(run_id, 1, 4) = 'run_' "
            "AND substr(run_id, 5) NOT GLOB '*[^0-9a-f]*'",
            name="run_id_format",
        ),
        CheckConstraint(
            "lifecycle IN ('QUEUED', 'PREFLIGHT', 'PLANNING', 'EXECUTING', "
            "'VERIFYING', 'REPORTING', 'COMPLETED', 'FAILED', 'CANCELLED', "
            "'SAFETY_STOPPED')",
            name="lifecycle_value",
        ),
        CheckConstraint(
            "verdict IS NULL OR verdict IN ('PASS', 'BLOCK', 'INCONCLUSIVE')",
            name="verdict_value",
        ),
        CheckConstraint(
            "(lifecycle = 'COMPLETED' AND verdict IS NOT NULL) OR "
            "(lifecycle <> 'COMPLETED' AND verdict IS NULL)",
            name="lifecycle_verdict_matrix",
        ),
        CheckConstraint("contract_version >= 1", name="contract_version_positive"),
        CheckConstraint(
            "created_at_us >= 0 AND updated_at_us >= created_at_us "
            "AND (finished_at_us IS NULL OR finished_at_us >= created_at_us)",
            name="time_order",
        ),
        Index("ix_runs_project_created", "project_id", "created_at_us"),
        Index("ix_runs_lifecycle_updated", "lifecycle", "updated_at_us"),
    )

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="RESTRICT"),
        nullable=False,
    )
    contract_id: Mapped[str] = mapped_column(String(128), nullable=False)
    contract_version: Mapped[int] = mapped_column(Integer, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(24), nullable=False)
    verdict: Mapped[str | None] = mapped_column(String(16))
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    finished_at_us: Mapped[int | None] = mapped_column(BigInteger)


class RecordingRow(Base):
    __tablename__ = "recordings"
    __table_args__ = (
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
        Index("ix_recordings_state_updated", "state", "updated_at_us"),
    )

    recording_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="RESTRICT"),
        nullable=False,
    )
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


class EvidenceIndexRow(Base):
    __tablename__ = "evidence_index"
    __table_args__ = (
        UniqueConstraint("run_id", "case_id", name="uq_evidence_run_case"),
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
