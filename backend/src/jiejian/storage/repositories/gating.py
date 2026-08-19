# =============================================================================
# 阶段 7.2 基线/门禁仓储
#
# 只保存版本化摘要和不可变引用；重复 Gate 求值命中相同输入时只读历史行。
# =============================================================================

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import GateResultRow, RegressionBaselineRow
from .base import StorageRecord, _flush, _scalar, ensure_storage_payload_safe


class RegressionBaselineRecord(StorageRecord):
    baseline_id: str
    project_id: str
    accepted_run_id: str
    finding_refs_json: str
    coverage_ids_json: str
    coverage_digest: str
    request_snapshot_sha256: str
    engine_version: str
    protocol_versions_json: str
    actor: str
    reason: str
    accepted_at_us: int


class GateResultRecord(StorageRecord):
    gate_result_id: str
    baseline_id: str
    project_id: str
    run_id: str
    policy_version: str
    input_hash: str
    reasons_json: str
    decision: str
    evaluated_at_us: int


class GatingRepository:
    def __init__(self, session: Session, known_secrets: Sequence[str]) -> None:
        self._session = session
        self._known_secrets = known_secrets

    def add_baseline(self, record: RegressionBaselineRecord) -> None:
        ensure_storage_payload_safe(record.model_dump(mode="json"), self._known_secrets)
        self._session.add(RegressionBaselineRow(**record.model_dump(mode="python")))
        _flush(self._session)

    def get_baseline(self, baseline_id: str) -> RegressionBaselineRecord | None:
        row = _scalar(self._session, select(RegressionBaselineRow).where(RegressionBaselineRow.baseline_id == baseline_id))
        return None if row is None else _baseline_record(row)

    def get_baseline_for_run(self, project_id: str, accepted_run_id: str) -> RegressionBaselineRecord | None:
        row = _scalar(
            self._session,
            select(RegressionBaselineRow)
            .where(RegressionBaselineRow.project_id == project_id, RegressionBaselineRow.accepted_run_id == accepted_run_id)
            .order_by(RegressionBaselineRow.accepted_at_us.desc(), RegressionBaselineRow.baseline_id)
            .limit(1),
        )
        return None if row is None else _baseline_record(row)

    def add_gate_result(self, record: GateResultRecord) -> None:
        ensure_storage_payload_safe(record.model_dump(mode="json"), self._known_secrets)
        self._session.add(GateResultRow(**record.model_dump(mode="python")))
        _flush(self._session)

    def get_gate_result(self, gate_result_id: str) -> GateResultRecord | None:
        row = _scalar(self._session, select(GateResultRow).where(GateResultRow.gate_result_id == gate_result_id))
        return None if row is None else _gate_result_record(row)

    def get_gate_result_for_input(self, baseline_id: str, run_id: str, policy_version: str, input_hash: str) -> GateResultRecord | None:
        row = _scalar(
            self._session,
            select(GateResultRow).where(
                GateResultRow.baseline_id == baseline_id,
                GateResultRow.run_id == run_id,
                GateResultRow.policy_version == policy_version,
                GateResultRow.input_hash == input_hash,
            ),
        )
        return None if row is None else _gate_result_record(row)

    def latest_gate_result(self, baseline_id: str, run_id: str) -> GateResultRecord | None:
        row = _scalar(
            self._session,
            select(GateResultRow)
            .where(GateResultRow.baseline_id == baseline_id, GateResultRow.run_id == run_id)
            .order_by(GateResultRow.evaluated_at_us.desc(), GateResultRow.gate_result_id.desc())
            .limit(1),
        )
        return None if row is None else _gate_result_record(row)


def _baseline_record(row: RegressionBaselineRow) -> RegressionBaselineRecord:
    return RegressionBaselineRecord(
        baseline_id=row.baseline_id,
        project_id=row.project_id,
        accepted_run_id=row.accepted_run_id,
        finding_refs_json=row.finding_refs_json,
        coverage_ids_json=row.coverage_ids_json,
        coverage_digest=row.coverage_digest,
        request_snapshot_sha256=row.request_snapshot_sha256,
        engine_version=row.engine_version,
        protocol_versions_json=row.protocol_versions_json,
        actor=row.actor,
        reason=row.reason,
        accepted_at_us=row.accepted_at_us,
    )


def _gate_result_record(row: GateResultRow) -> GateResultRecord:
    return GateResultRecord(
        gate_result_id=row.gate_result_id,
        baseline_id=row.baseline_id,
        project_id=row.project_id,
        run_id=row.run_id,
        policy_version=row.policy_version,
        input_hash=row.input_hash,
        reasons_json=row.reasons_json,
        decision=row.decision,
        evaluated_at_us=row.evaluated_at_us,
    )
