# 阶段 7.2 基线与门禁的 SQLAlchemy 映射；只保存引用、摘要和确定性结果。

from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class RegressionBaselineRow(Base):
    __tablename__ = "regression_baselines"
    __table_args__ = (
        CheckConstraint("schema_version = '1'", name="baseline_schema_version_value"),
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
    schema_version: Mapped[str] = mapped_column(String(8), nullable=False)
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
        CheckConstraint("schema_version = '1'", name="gate_result_schema_version_value"),
        CheckConstraint("length(gate_result_id) = 37 AND substr(gate_result_id, 1, 5) = 'gate_' AND substr(gate_result_id, 6) NOT GLOB '*[^0-9a-f]*'", name="gate_result_id_format"),
        CheckConstraint("policy_version = 'gate-v1'", name="gate_result_policy_version_value"),
        CheckConstraint("decision IN ('PASS', 'BLOCK', 'ERROR')", name="gate_result_decision_value"),
        CheckConstraint("length(reasons_json) BETWEEN 2 AND 524288", name="gate_result_reasons_length"),
        CheckConstraint("evaluated_at_us >= 0", name="gate_result_evaluated_nonnegative"),
        CheckConstraint("length(input_hash) = 64 AND input_hash NOT GLOB '*[^0-9a-f]*'", name="gate_result_input_hash_format"),
        Index("ix_gate_results_baseline_run", "baseline_id", "run_id", "evaluated_at_us"),
    )

    gate_result_id: Mapped[str] = mapped_column(String(37), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(8), nullable=False)
    baseline_id: Mapped[str] = mapped_column(ForeignKey("regression_baselines.baseline_id", ondelete="RESTRICT"), nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id", ondelete="RESTRICT"), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(16), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reasons_json: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(String(8), nullable=False)
    evaluated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
