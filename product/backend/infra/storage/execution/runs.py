# Storage 的 SQLAlchemy typed declarative 映射。

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from product.backend.infra.storage.base import Base

class RunRow(Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(
            "length(run_id) = 36 AND substr(run_id, 1, 4) = 'run_' "
            "AND substr(run_id, 5) NOT GLOB '*[^0-9a-f]*'",
            name="run_id_format",
        ),
        CheckConstraint(
            "lifecycle IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED', "
            "'SAFETY_STOPPED')",
            name="lifecycle_value",
        ),
        CheckConstraint(
            "verdict IS NULL OR verdict IN ('PASS', 'BLOCK', 'INCONCLUSIVE')",
            name="verdict_value",
        ),
        CheckConstraint(
            "(lifecycle = 'COMPLETED' AND verdict IS NOT NULL) OR "
            "(lifecycle = 'SAFETY_STOPPED' AND (verdict IS NULL OR verdict IN ('BLOCK', 'INCONCLUSIVE'))) OR "
            "(lifecycle NOT IN ('COMPLETED', 'SAFETY_STOPPED') AND verdict IS NULL)",
            name="lifecycle_verdict_matrix",
        ),
        CheckConstraint("policy_epoch >= 0", name="policy_epoch_nonnegative"),
        CheckConstraint("length(engine_version) BETWEEN 1 AND 64", name="engine_version_length"),
        *(CheckConstraint(f"length({name}) = 64 AND {name} NOT GLOB '*[^0-9a-f]*'", name=f"{name}_format")
          for name in ("request_hash", "plan_fingerprint", "source_fingerprint")),
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
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(24), nullable=False)
    verdict: Mapped[str | None] = mapped_column(String(16))
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    finished_at_us: Mapped[int | None] = mapped_column(BigInteger)

# 本聚合的 Repository 与持久化记录边界。

# =============================================================================
# Verification Run 仓储
#
# 定位
#   Run 生命周期、冻结快照和 Verdict 的持久化适配器
#
# 职责
#   保存 Run 记录｜保持生命周期与结论分离｜提供结果和恢复读取
#
# 调用链
#   Execution / Results → RunRepository → Run ORM rows
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
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from product.backend.core.identifiers import EVIDENCE_ID_PATTERN, JOB_ID_PATTERN, PROJECT_ID_PATTERN, RECORDING_ID_PATTERN, RUN_ID_PATTERN, SHA256_PATTERN
from product.backend.core.lifecycle import JobState, ProjectStatus, RunLifecycle, RunVerdict
from product.backend.core.lifecycle import ContractStatus
from product.backend.core.verification.permissions import PermissionContract
from product.backend.core.recording import Recording, RecordingState, RecordingStateEvent, RecordingTerminalState
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import STAGED_ARTIFACT_MAX_BYTES, FlowDraft, RecordingEventKind, RecordingEvent, RecordingHeader, StagedArtifact, canonical_flow_draft_json_bytes
from product.backend.infra.storage.base import MetadataValue, StorageRecord, _METADATA_KEY, _SENSITIVE_METADATA_KEY, _canonical_json, _flush, _scalar, _scalars, ensure_storage_payload_safe

class RunRecord(StorageRecord):
    run_id: str = Field(pattern=RUN_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    request_hash: str = Field(pattern=SHA256_PATTERN)
    plan_fingerprint: str = Field(pattern=SHA256_PATTERN)
    source_fingerprint: str = Field(pattern=SHA256_PATTERN)
    policy_epoch: int = Field(ge=0)
    engine_version: str = Field(min_length=1, max_length=64)
    lifecycle: RunLifecycle
    verdict: RunVerdict | None = None
    created_at_us: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)
    finished_at_us: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_run_matrix(self) -> RunRecord:
        if self.lifecycle is RunLifecycle.SAFETY_STOPPED:
            valid = self.verdict in (None, RunVerdict.BLOCK, RunVerdict.INCONCLUSIVE)
        else:
            valid = (self.lifecycle is RunLifecycle.COMPLETED) == (self.verdict is not None)
        if not valid:
            raise ValueError("run lifecycle and verdict are inconsistent")
        if self.updated_at_us < self.created_at_us:
            raise ValueError("run update time precedes creation")
        if self.finished_at_us is not None and self.finished_at_us < self.created_at_us:
            raise ValueError("run finish time precedes creation")
        return self
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
                request_hash=record.request_hash,
                plan_fingerprint=record.plan_fingerprint,
                source_fingerprint=record.source_fingerprint,
                policy_epoch=record.policy_epoch,
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
            request_hash=row.request_hash,
            plan_fingerprint=row.plan_fingerprint,
            source_fingerprint=row.source_fingerprint,
            policy_epoch=row.policy_epoch,
            engine_version=row.engine_version,
            lifecycle=RunLifecycle(row.lifecycle),
            verdict=RunVerdict(row.verdict) if row.verdict is not None else None,
            created_at_us=row.created_at_us,
            updated_at_us=row.updated_at_us,
            finished_at_us=row.finished_at_us,
        )
    def list_for_project(self, project_id: str) -> tuple[RunRecord, ...]:
        rows = _scalars(
            self._session,
            select(RunRow)
            .where(RunRow.project_id == project_id)
            .order_by(RunRow.created_at_us.desc(), RunRow.run_id),
        )
        return tuple(
            RunRecord(
                run_id=row.run_id,
                project_id=row.project_id,
                request_hash=row.request_hash,
                plan_fingerprint=row.plan_fingerprint,
                source_fingerprint=row.source_fingerprint,
                policy_epoch=row.policy_epoch,
                engine_version=row.engine_version,
                lifecycle=RunLifecycle(row.lifecycle),
                verdict=RunVerdict(row.verdict) if row.verdict is not None else None,
                created_at_us=row.created_at_us,
                updated_at_us=row.updated_at_us,
                finished_at_us=row.finished_at_us,
            )
            for row in rows
        )

    @staticmethod
    def _page_statement(project_id, before_created_at_us=None, before_run_id=None):
        statement = select(RunRow).where(RunRow.project_id == project_id)
        if before_created_at_us is not None:
            statement = statement.where(or_(RunRow.created_at_us < before_created_at_us,
                and_(RunRow.created_at_us == before_created_at_us, RunRow.run_id > before_run_id)))
        return statement.order_by(RunRow.created_at_us.desc(), RunRow.run_id.asc())

    def page_for_project(self, project_id: str, *, limit: int,
                         before_created_at_us: int | None = None, before_run_id: str | None = None,
                         lifecycles: tuple[RunLifecycle, ...] | None = None) -> tuple[RunRecord, ...]:
        """只读有界候选；游标是排序位置，不跨项目查找游标对应记录。"""
        if not 1 <= limit <= 250 or (before_created_at_us is None) != (before_run_id is None):
            raise ValueError("invalid bounded run page")
        statement = self._page_statement(project_id, before_created_at_us, before_run_id)
        if lifecycles is not None:
            statement = statement.where(RunRow.lifecycle.in_(tuple(item.value for item in lifecycles)))
        rows = _scalars(self._session, statement.limit(limit))
        return tuple(RunRecord(run_id=row.run_id, project_id=row.project_id, request_hash=row.request_hash,
            plan_fingerprint=row.plan_fingerprint, source_fingerprint=row.source_fingerprint,
            policy_epoch=row.policy_epoch, engine_version=row.engine_version,
            lifecycle=RunLifecycle(row.lifecycle), verdict=RunVerdict(row.verdict) if row.verdict is not None else None,
            created_at_us=row.created_at_us, updated_at_us=row.updated_at_us, finished_at_us=row.finished_at_us)
            for row in rows)

    def has_after_for_project(self, project_id: str, created_at_us: int, run_id: str) -> bool:
        """仅探测后续键是否存在，不加载或校验第 251 个历史 Run。"""
        statement = self._page_statement(project_id, created_at_us, run_id).with_only_columns(RunRow.run_id).limit(1)
        return _scalar(self._session, statement) is not None

    def list_finished_for_project(self, project_id: str) -> tuple[RunRecord, ...]:
        """按冻结完成时间和 Run ID 返回可参与结果最终化的历史 Run。"""

        rows = _scalars(
            self._session,
            select(RunRow)
            .where(
                RunRow.project_id == project_id,
                RunRow.lifecycle.in_((RunLifecycle.COMPLETED.value, RunLifecycle.SAFETY_STOPPED.value)),
                RunRow.finished_at_us.is_not(None),
            )
            .order_by(RunRow.finished_at_us, RunRow.run_id),
        )
        return tuple(
            RunRecord(
                run_id=row.run_id,
                project_id=row.project_id,
                request_hash=row.request_hash,
                plan_fingerprint=row.plan_fingerprint,
                source_fingerprint=row.source_fingerprint,
                policy_epoch=row.policy_epoch,
                engine_version=row.engine_version,
                lifecycle=RunLifecycle(row.lifecycle),
                verdict=RunVerdict(row.verdict) if row.verdict is not None else None,
                created_at_us=row.created_at_us,
                updated_at_us=row.updated_at_us,
                finished_at_us=row.finished_at_us,
            )
            for row in rows
        )
