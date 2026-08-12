# 阶段 2.1 的 SQLAlchemy typed declarative 映射。

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

from .base import Base

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
