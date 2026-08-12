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
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

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
