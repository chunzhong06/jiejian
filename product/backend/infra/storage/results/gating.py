# 历史表与只读记录形状保留用于无损升级；当前产品已退出这组仓储写入。
# Regression Gate 基线与门禁的 SQLAlchemy 映射；只保存引用、摘要和确定性结果。

from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from product.backend.infra.storage.base import Base


class RegressionBaselineRow(Base):
    __tablename__ = "regression_baselines"
    __table_args__ = (
        CheckConstraint("length(baseline_id) = 41 AND substr(baseline_id, 1, 9) = 'baseline_' AND substr(baseline_id, 10) NOT GLOB '*[^0-9a-f]*'", name="baseline_id_format"),
        CheckConstraint("length(finding_refs_json) BETWEEN 2 AND 524288", name="baseline_finding_refs_length"),
        CheckConstraint("length(coverage_ids_json) BETWEEN 2 AND 524288", name="baseline_coverage_ids_length"),
        CheckConstraint("length(protocol_versions_json) BETWEEN 3 AND 4096", name="baseline_protocol_versions_length"),
        CheckConstraint("length(actor) BETWEEN 1 AND 128", name="baseline_actor_length"),
        CheckConstraint("length(reason) BETWEEN 1 AND 1024", name="baseline_reason_length"),
        CheckConstraint("accepted_at_us >= 0", name="baseline_accepted_nonnegative"),
        CheckConstraint("length(coverage_digest) = 64 AND coverage_digest NOT GLOB '*[^0-9a-f]*'", name="baseline_coverage_digest_format"),
        CheckConstraint("length(request_snapshot_sha256) = 64 AND request_snapshot_sha256 NOT GLOB '*[^0-9a-f]*'", name="baseline_snapshot_hash_format"),
        Index("ix_regression_baselines_project_accepted", "project_id", "accepted_at_us"),
    )
    baseline_id: Mapped[str] = mapped_column(String(41), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False)
    accepted_run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id", ondelete="RESTRICT"), nullable=False)
    finding_refs_json: Mapped[str] = mapped_column(Text, nullable=False)
    coverage_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    coverage_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    protocol_versions_json: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(String(1024), nullable=False)
    accepted_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)


class GateResultRow(Base):
    __tablename__ = "gate_results"
    __table_args__ = (
        UniqueConstraint("baseline_id", "run_id", "policy_version", "input_hash", name="uq_gate_result_input"),
        CheckConstraint("length(gate_result_id) = 37 AND substr(gate_result_id, 1, 5) = 'gate_' AND substr(gate_result_id, 6) NOT GLOB '*[^0-9a-f]*'", name="gate_result_id_format"),
        CheckConstraint("policy_version = 'gate-v1'", name="gate_result_policy_version_value"),
        CheckConstraint("decision IN ('PASS', 'BLOCK', 'ERROR')", name="gate_result_decision_value"),
        CheckConstraint("length(reasons_json) BETWEEN 2 AND 524288", name="gate_result_reasons_length"),
        CheckConstraint("evaluated_at_us >= 0", name="gate_result_evaluated_nonnegative"),
        CheckConstraint("length(input_hash) = 64 AND input_hash NOT GLOB '*[^0-9a-f]*'", name="gate_result_input_hash_format"),
        Index("ix_gate_results_baseline_run", "baseline_id", "run_id", "evaluated_at_us"),
    )

    gate_result_id: Mapped[str] = mapped_column(String(37), primary_key=True)
    baseline_id: Mapped[str] = mapped_column(ForeignKey("regression_baselines.baseline_id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id", ondelete="RESTRICT"), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(16), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reasons_json: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(String(8), nullable=False)
    evaluated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)

# 本聚合的 Repository 与持久化记录边界。

# =============================================================================
# Regression Gate 基线/门禁仓储
#
# 只保存版本化摘要和不可变引用；重复 Gate 求值命中相同输入时只读历史行。
# =============================================================================

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session


from product.backend.infra.storage.base import StorageRecord, _flush, _scalar, ensure_storage_payload_safe


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
