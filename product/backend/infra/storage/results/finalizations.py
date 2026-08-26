# =============================================================================
# Run 结果最终化仓储
#
# 定位
#   保存 publication 之后的 Finding 与基础报告派生状态
#
# 职责
#   约束唯一最终化记录｜提供同一事务内的状态更新｜拒绝秘密和状态错配
#
# 边界
#   不读取 publication 文件、不执行 Target、不生成 Finding；ResultFinalizer 负责编排。
#
# 调用链
#   RunPublisher / ResultFinalizer → RunFinalizationRepository → run_finalizations
# =============================================================================

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator
from sqlalchemy import BigInteger, CheckConstraint, ForeignKeyConstraint, Index, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column, Session

from product.backend.core.identifiers import RUN_ID_PATTERN, SHA256_PATTERN
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage.base import Base, StorageRecord, _flush, _scalar, _scalars, ensure_storage_payload_safe


class FindingFinalizationState(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class BaseReportFinalizationState(StrEnum):
    BLOCKED = "BLOCKED"
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class RunFinalizationRow(Base):
    __tablename__ = "run_finalizations"
    __table_args__ = (
        CheckConstraint("length(publication_sha256) = 64 AND publication_sha256 NOT GLOB '*[^0-9a-f]*'", name="publication_sha256_format"),
        CheckConstraint("findings_state IN ('PENDING', 'RUNNING', 'COMPLETE', 'FAILED', 'BLOCKED')", name="findings_state_value"),
        CheckConstraint("base_report_state IN ('BLOCKED', 'PENDING', 'RUNNING', 'COMPLETE', 'FAILED')", name="base_report_state_value"),
        CheckConstraint("findings_attempt >= 0 AND base_report_attempt >= 0", name="attempt_nonnegative"),
        CheckConstraint(
            "(findings_state = 'COMPLETE' AND findings_snapshot_sha256 IS NOT NULL AND findings_completed_at_us IS NOT NULL AND findings_error_code IS NULL AND blocked_by_run_id IS NULL) OR "
            "(findings_state = 'FAILED' AND findings_error_code IS NOT NULL AND findings_snapshot_sha256 IS NULL AND findings_completed_at_us IS NULL AND blocked_by_run_id IS NULL) OR "
            "(findings_state = 'BLOCKED' AND blocked_by_run_id IS NOT NULL AND findings_error_code = 'RESULT_FINALIZATION_BLOCKED' AND findings_snapshot_sha256 IS NULL AND findings_completed_at_us IS NULL) OR "
            "(findings_state IN ('PENDING', 'RUNNING') AND findings_error_code IS NULL AND findings_snapshot_sha256 IS NULL AND findings_completed_at_us IS NULL AND blocked_by_run_id IS NULL)",
            name="findings_state_fields_matrix",
        ),
        CheckConstraint(
            "(base_report_state = 'COMPLETE' AND base_report_input_sha256 IS NOT NULL AND base_report_id IS NOT NULL AND base_report_completed_at_us IS NOT NULL AND base_report_error_code IS NULL) OR "
            "(base_report_state = 'FAILED' AND base_report_error_code IS NOT NULL AND base_report_input_sha256 IS NULL AND base_report_id IS NULL AND base_report_completed_at_us IS NULL) OR "
            "(base_report_state IN ('BLOCKED', 'PENDING', 'RUNNING') AND base_report_error_code IS NULL AND base_report_input_sha256 IS NULL AND base_report_id IS NULL AND base_report_completed_at_us IS NULL)",
            name="base_report_state_fields_matrix",
        ),
        CheckConstraint("created_at_us >= 0 AND updated_at_us >= created_at_us", name="time_order"),
        CheckConstraint("findings_snapshot_sha256 IS NULL OR (length(findings_snapshot_sha256) = 64 AND findings_snapshot_sha256 NOT GLOB '*[^0-9a-f]*')", name="findings_snapshot_sha256_format"),
        CheckConstraint("base_report_input_sha256 IS NULL OR (length(base_report_input_sha256) = 64 AND base_report_input_sha256 NOT GLOB '*[^0-9a-f]*')", name="base_report_input_sha256_format"),
        CheckConstraint("base_report_id IS NULL OR (length(base_report_id) = 39 AND substr(base_report_id, 1, 7) = 'report_' AND substr(base_report_id, 8) NOT GLOB '*[^0-9a-f]*')", name="base_report_id_format"),
        CheckConstraint("findings_completed_at_us IS NULL OR findings_completed_at_us >= 0", name="findings_completed_at_nonnegative"),
        CheckConstraint("base_report_completed_at_us IS NULL OR base_report_completed_at_us >= 0", name="base_report_completed_at_nonnegative"),
        ForeignKeyConstraint(["run_id"], ["runs.run_id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["blocked_by_run_id"], ["runs.run_id"], ondelete="RESTRICT"),
        Index("ix_run_finalizations_findings_state", "findings_state", "updated_at_us"),
        Index("ix_run_finalizations_base_report_state", "base_report_state", "updated_at_us"),
    )

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    publication_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    findings_state: Mapped[str] = mapped_column(String(16), nullable=False)
    findings_attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    findings_error_code: Mapped[str | None] = mapped_column(String(64))
    findings_snapshot_sha256: Mapped[str | None] = mapped_column(String(64))
    findings_completed_at_us: Mapped[int | None] = mapped_column(BigInteger)
    blocked_by_run_id: Mapped[str | None] = mapped_column(String(36))
    base_report_state: Mapped[str] = mapped_column(String(16), nullable=False)
    base_report_attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    base_report_error_code: Mapped[str | None] = mapped_column(String(64))
    base_report_input_sha256: Mapped[str | None] = mapped_column(String(64))
    base_report_id: Mapped[str | None] = mapped_column(String(39))
    base_report_completed_at_us: Mapped[int | None] = mapped_column(BigInteger)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class RunFinalizationRecord(StorageRecord):
    run_id: str = Field(pattern=RUN_ID_PATTERN)
    publication_sha256: str = Field(pattern=SHA256_PATTERN)
    findings_state: FindingFinalizationState
    findings_attempt: int = Field(ge=0)
    findings_error_code: str | None = Field(default=None, min_length=1, max_length=64)
    findings_snapshot_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    findings_completed_at_us: int | None = Field(default=None, ge=0)
    blocked_by_run_id: str | None = Field(default=None, pattern=RUN_ID_PATTERN)
    base_report_state: BaseReportFinalizationState
    base_report_attempt: int = Field(ge=0)
    base_report_error_code: str | None = Field(default=None, min_length=1, max_length=64)
    base_report_input_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    base_report_id: str | None = Field(default=None, pattern=r"^report_[0-9a-f]{32}$")
    base_report_completed_at_us: int | None = Field(default=None, ge=0)
    created_at_us: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_state_fields(self) -> RunFinalizationRecord:
        if self.updated_at_us < self.created_at_us:
            raise ValueError("finalization time order is invalid")
        if self.findings_state is FindingFinalizationState.COMPLETE:
            if self.findings_error_code or self.blocked_by_run_id or self.findings_snapshot_sha256 is None or self.findings_completed_at_us is None:
                raise ValueError("complete findings state fields are inconsistent")
        elif self.findings_state is FindingFinalizationState.FAILED:
            if not self.findings_error_code or self.findings_snapshot_sha256 is not None or self.findings_completed_at_us is not None or self.blocked_by_run_id is not None:
                raise ValueError("failed findings state fields are inconsistent")
        elif self.findings_state is FindingFinalizationState.BLOCKED:
            if self.blocked_by_run_id is None or self.findings_error_code != ErrorCode.RESULT_FINALIZATION_BLOCKED.value or self.findings_snapshot_sha256 is not None or self.findings_completed_at_us is not None:
                raise ValueError("blocked findings state fields are inconsistent")
        elif self.findings_error_code or self.findings_snapshot_sha256 is not None or self.findings_completed_at_us is not None or self.blocked_by_run_id is not None:
            raise ValueError("active findings state fields are inconsistent")
        if self.base_report_state is BaseReportFinalizationState.COMPLETE:
            if self.base_report_error_code or self.base_report_input_sha256 is None or self.base_report_id is None or self.base_report_completed_at_us is None:
                raise ValueError("complete report state fields are inconsistent")
        elif self.base_report_state is BaseReportFinalizationState.FAILED:
            if not self.base_report_error_code or self.base_report_input_sha256 is not None or self.base_report_id is not None or self.base_report_completed_at_us is not None:
                raise ValueError("failed report state fields are inconsistent")
        elif self.base_report_error_code or self.base_report_input_sha256 is not None or self.base_report_id is not None or self.base_report_completed_at_us is not None:
            raise ValueError("active report state fields are inconsistent")
        return self


class RunFinalizationRepository:
    def __init__(self, session: Session, known_secrets: tuple[str, ...] = ()) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def add(self, record: RunFinalizationRecord) -> None:
        ensure_storage_payload_safe(record.model_dump(mode="json"), self._known_secrets)
        self._session.add(RunFinalizationRow(**record.model_dump(mode="python")))
        _flush(self._session)

    def get(self, run_id: str) -> RunFinalizationRecord | None:
        row = _scalar(self._session, select(RunFinalizationRow).where(RunFinalizationRow.run_id == run_id))
        return None if row is None else _record(row)

    def list_for_runs(self, run_ids: tuple[str, ...]) -> tuple[RunFinalizationRecord, ...]:
        if not run_ids:
            return ()
        rows = _scalars(self._session, select(RunFinalizationRow).where(RunFinalizationRow.run_id.in_(run_ids)))
        return tuple(_record(row) for row in rows)

    def save(self, record: RunFinalizationRecord) -> None:
        ensure_storage_payload_safe(record.model_dump(mode="json"), self._known_secrets)
        row = _scalar(self._session, select(RunFinalizationRow).where(RunFinalizationRow.run_id == record.run_id))
        if row is None:
            raise JiejianError(ErrorCode.RESULT_FINALIZATION_NOT_FOUND, "结果最终化记录不存在")
        for key, value in record.model_dump(mode="python").items():
            setattr(row, key, value)
        _flush(self._session)

    def ensure_initial(self, run_id: str, publication_sha256: str, now_us: int) -> RunFinalizationRecord:
        current = self.get(run_id)
        if current is not None:
            if current.publication_sha256 != publication_sha256:
                raise JiejianError(ErrorCode.RESULT_FINALIZATION_CONFLICT, "publication 摘要与最终化记录不一致")
            return current
        record = RunFinalizationRecord(
            run_id=run_id,
            publication_sha256=publication_sha256,
            findings_state=FindingFinalizationState.PENDING,
            findings_attempt=0,
            base_report_state=BaseReportFinalizationState.BLOCKED,
            base_report_attempt=0,
            created_at_us=now_us,
            updated_at_us=now_us,
        )
        self.add(record)
        return record


def _record(row: RunFinalizationRow) -> RunFinalizationRecord:
    return RunFinalizationRecord(
        run_id=row.run_id,
        publication_sha256=row.publication_sha256,
        findings_state=FindingFinalizationState(row.findings_state),
        findings_attempt=row.findings_attempt,
        findings_error_code=row.findings_error_code,
        findings_snapshot_sha256=row.findings_snapshot_sha256,
        findings_completed_at_us=row.findings_completed_at_us,
        blocked_by_run_id=row.blocked_by_run_id,
        base_report_state=BaseReportFinalizationState(row.base_report_state),
        base_report_attempt=row.base_report_attempt,
        base_report_error_code=row.base_report_error_code,
        base_report_input_sha256=row.base_report_input_sha256,
        base_report_id=row.base_report_id,
        base_report_completed_at_us=row.base_report_completed_at_us,
        created_at_us=row.created_at_us,
        updated_at_us=row.updated_at_us,
    )
