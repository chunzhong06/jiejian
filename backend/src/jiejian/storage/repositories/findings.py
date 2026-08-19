# =============================================================================
# Finding/Occurrence 仓储
#
# 定位
#   保存跨 Run 稳定问题和已发布 Evidence 引用，不保存 Evidence 正文
#
# 职责
#   幂等写入 Finding｜按 Run 读取 Occurrence｜提供状态转换所需历史
#
# 调用链
#   FindingApplicationService → FindingRepository → SQLAlchemy rows
# =============================================================================

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...errors import ErrorCode, JiejianError
from ..models import FindingOccurrenceRow, FindingRow
from .base import StorageRecord, _flush, _scalar, _scalars, ensure_storage_payload_safe


class FindingRecord(StorageRecord):
    finding_id: str
    project_id: str
    identity_json: str
    created_at_us: int
    updated_at_us: int


class FindingOccurrenceRecord(StorageRecord):
    occurrence_id: str
    finding_id: str
    project_id: str
    run_id: str
    status: str
    verdict: str
    severity: str
    evidence_refs_json: str
    object_context_json: str
    coverage_context_json: str
    created_at_us: int


class FindingRepository:
    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def add(self, record: FindingRecord) -> None:
        ensure_storage_payload_safe(record.model_dump(mode="json"), self._known_secrets)
        self._session.add(
            FindingRow(
                finding_id=record.finding_id,
                schema_version=record.schema_version,
                project_id=record.project_id,
                identity_json=record.identity_json,
                created_at_us=record.created_at_us,
                updated_at_us=record.updated_at_us,
            )
        )
        _flush(self._session)

    def get(self, finding_id: str) -> FindingRecord | None:
        row = _scalar(self._session, select(FindingRow).where(FindingRow.finding_id == finding_id))
        return None if row is None else _finding_record(row)

    def list_for_project(self, project_id: str) -> tuple[FindingRecord, ...]:
        rows = _scalars(
            self._session,
            select(FindingRow)
            .where(FindingRow.project_id == project_id)
            .order_by(FindingRow.created_at_us, FindingRow.finding_id),
        )
        return tuple(_finding_record(row) for row in rows)

    def touch(self, finding_id: str, updated_at_us: int) -> None:
        row = _scalar(self._session, select(FindingRow).where(FindingRow.finding_id == finding_id))
        if row is None:
            raise JiejianError(ErrorCode.STORAGE_CONSTRAINT, "Finding 不存在")
        if updated_at_us < row.updated_at_us:
            raise JiejianError(ErrorCode.STORAGE_CONSTRAINT, "Finding 时间不能回退")
        row.updated_at_us = updated_at_us
        _flush(self._session)

    def add_occurrence(self, record: FindingOccurrenceRecord) -> None:
        ensure_storage_payload_safe(record.model_dump(mode="json"), self._known_secrets)
        self._session.add(
            FindingOccurrenceRow(
                occurrence_id=record.occurrence_id,
                schema_version=record.schema_version,
                finding_id=record.finding_id,
                project_id=record.project_id,
                run_id=record.run_id,
                status=record.status,
                verdict=record.verdict,
                severity=record.severity,
                evidence_refs_json=record.evidence_refs_json,
                object_context_json=record.object_context_json,
                coverage_context_json=record.coverage_context_json,
                created_at_us=record.created_at_us,
            )
        )
        _flush(self._session)

    def get_occurrence(self, finding_id: str, run_id: str) -> FindingOccurrenceRecord | None:
        row = _scalar(
            self._session,
            select(FindingOccurrenceRow).where(
                FindingOccurrenceRow.finding_id == finding_id,
                FindingOccurrenceRow.run_id == run_id,
            ),
        )
        return None if row is None else _occurrence_record(row)

    def latest_occurrence(self, finding_id: str) -> FindingOccurrenceRecord | None:
        row = _scalar(
            self._session,
            select(FindingOccurrenceRow)
            .where(FindingOccurrenceRow.finding_id == finding_id)
            .order_by(FindingOccurrenceRow.created_at_us.desc(), FindingOccurrenceRow.occurrence_id.desc())
            .limit(1),
        )
        return None if row is None else _occurrence_record(row)

    def list_occurrences_for_run(self, run_id: str) -> tuple[FindingOccurrenceRecord, ...]:
        rows = _scalars(
            self._session,
            select(FindingOccurrenceRow)
            .where(FindingOccurrenceRow.run_id == run_id)
            .order_by(FindingOccurrenceRow.created_at_us, FindingOccurrenceRow.finding_id),
        )
        return tuple(_occurrence_record(row) for row in rows)


def _finding_record(row: FindingRow) -> FindingRecord:
    return FindingRecord(
        finding_id=row.finding_id,
        project_id=row.project_id,
        identity_json=row.identity_json,
        created_at_us=row.created_at_us,
        updated_at_us=row.updated_at_us,
    )


def _occurrence_record(row: FindingOccurrenceRow) -> FindingOccurrenceRecord:
    return FindingOccurrenceRecord(
        occurrence_id=row.occurrence_id,
        finding_id=row.finding_id,
        project_id=row.project_id,
        run_id=row.run_id,
        status=row.status,
        verdict=row.verdict,
        severity=row.severity,
        evidence_refs_json=row.evidence_refs_json,
        object_context_json=row.object_context_json,
        coverage_context_json=row.coverage_context_json,
        created_at_us=row.created_at_us,
    )
