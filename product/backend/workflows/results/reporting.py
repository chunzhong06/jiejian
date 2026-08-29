# =============================================================================
# 统一报告应用服务
#
# 定位
#   从可信 PublishedRunView、已完成 Finding、确定性展示快照、Artifact 快照
#   和明确 GateResult 构造不可变 Base/Gate Report。
#
# 边界
#   只读已发布事实；不物化 Finding、不重新读取 Target、不改变 Verdict。
# =============================================================================

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import RunLifecycle
from product.backend.core.verification.gating import GateResult
from product.backend.infra.artifacts.report_reader import ArtifactResultReader
from product.backend.infra.artifacts.report_store import ReportStore
from product.backend.infra.storage import BaseReportFinalizationState
from product.backend.workflows.results.published import PublishedResultReader
from product.protocols import RunnerResult
from product.protocols.report import (
    ArtifactSummary,
    ArtifactSummaryStatus,
    BaseRunReport,
    GateRunReport,
    REPORT_RULESET_VERSION,
    ReportArtifact,
    ReportEvidenceRef,
    ReportFinding,
    ReportGate,
    ReportObserverStatus,
    ReportPresentation,
    ReportPresentationIssue,
    ReportRun,
    ReportRuntime,
    ReportVersions,
    base_semantic_input_sha256,
    gate_semantic_input_sha256,
    report_id_for,
)


class ReportBuilder:
    """生成、读取和列举唯一 ReportStore 中的不可变报告。"""

    def __init__(
        self,
        var_dir: Path,
        results: PublishedResultReader,
        findings,
        gating,
        uow_factory=None,
        *,
        presentation=None,
    ) -> None:
        self._results = results
        self._findings = findings
        self._gating = gating
        self._presentation = presentation
        self._uow_factory = uow_factory
        self._artifacts = ArtifactResultReader(var_dir)
        self._publication = ReportStore(var_dir)

    def generate_base(self, run_id: str) -> BaseRunReport:
        view = self._results.read(run_id)
        finalization = self._finalization(run_id)
        if finalization.findings_state.value != "COMPLETE":
            raise JiejianError(ErrorCode.RESULT_FINALIZATION_NOT_READY, "Finding 尚未完成最终化")
        if finalization.findings_snapshot_sha256 is None:
            raise JiejianError(ErrorCode.RESULT_FINALIZATION_NOT_READY, "Finding 快照缺失")
        stored_findings = self._findings.findings_for_run(run_id)
        runtime = self._runtime(view, stored_findings)
        artifact_summary = self._artifact_summary(run_id, view.run.project_id)
        versions = self._versions(view, artifact_summary)
        presentation = self._presentation_snapshot(run_id, view.run.project_id)
        semantic_input = base_semantic_input_sha256(
            run_id,
            finalization.publication_sha256,
            finalization.findings_snapshot_sha256,
            artifact_summary.snapshot_sha256,
            versions,
        )
        report_id = report_id_for("BASE", semantic_input)
        limitations = self._limitations(view, runtime, artifact_summary)
        report = BaseRunReport.create(
            report_id=report_id,
            report_type="BASE",
            run_id=run_id,
            project_id=view.run.project_id,
            semantic_input_sha256=semantic_input,
            run=self._run(view),
            runtime=runtime,
            presentation=presentation,
            artifact_summary=artifact_summary,
            versions=versions,
            limitations=limitations,
        )
        self._publication.publish(report)
        return report

    def generate_gate(self, run_id: str, gate_result_id: str) -> GateRunReport:
        finalization = self._finalization(run_id)
        if finalization.base_report_state is not BaseReportFinalizationState.COMPLETE or finalization.base_report_id is None:
            raise JiejianError(ErrorCode.RESULT_FINALIZATION_NOT_READY, "基础报告尚未完成")
        base = self._publication.read(run_id, finalization.base_report_id)
        if not isinstance(base, BaseRunReport):
            raise JiejianError(ErrorCode.REPORT_INTEGRITY, "基础报告类型无效")
        if finalization.base_report_input_sha256 != base.semantic_input_sha256:
            raise JiejianError(ErrorCode.REPORT_INTEGRITY, "基础报告身份已漂移")
        gate_payload = self._gating.get_gate_result(gate_result_id)
        gate = GateResult.model_validate_json(json.dumps(gate_payload, ensure_ascii=False), strict=True)
        baseline = self._gating.get_baseline(gate.baseline_id)
        if gate.run_id != run_id or baseline.get("project_id") != base.project_id:
            raise JiejianError(ErrorCode.REPORT_INPUT_INVALID, "GateResult 与 Run 关联不一致")
        semantic_input = gate_semantic_input_sha256(base.report_id, base.canonical_sha256, gate.gate_result_id, gate.input_hash)
        report = GateRunReport.create(
            report_id=report_id_for("GATE", semantic_input),
            report_type="GATE",
            run_id=base.run_id,
            project_id=base.project_id,
            base_report_id=base.report_id,
            base_report_sha256=base.canonical_sha256,
            gate_result_id=gate.gate_result_id,
            semantic_input_sha256=semantic_input,
            run=base.run,
            runtime=base.runtime,
            presentation=base.presentation,
            artifact_summary=base.artifact_summary,
            versions=base.versions,
            limitations=base.limitations,
            gate=ReportGate(
                gate_result_id=gate.gate_result_id,
                baseline_id=gate.baseline_id,
                run_id=gate.run_id,
                policy_version=gate.policy_version,
                input_hash=gate.input_hash,
                decision=gate.decision.value,
                reasons=tuple(item.model_dump(mode="json") for item in gate.reasons),
                evaluated_at_us=gate.evaluated_at_us,
            ),
        )
        self._publication.publish(report)
        return report

    def read(self, run_id: str, report_id: str) -> dict[str, Any]:
        return self._publication.read(run_id, report_id).model_dump(mode="json")

    def read_format(self, run_id: str, report_id: str, output_format: str) -> bytes:
        return self._publication.read_format(run_id, report_id, output_format)

    def list(self, run_id: str) -> list[dict[str, str]]:
        return self._publication.list(run_id)

    def _finalization(self, run_id: str):
        if self._uow_factory is None:
            raise JiejianError(ErrorCode.RESULT_FINALIZATION_NOT_READY, "结果最终化仓储未装配")
        with self._uow_factory() as work:
            record = work.finalizations.get(run_id)
        if record is None:
            raise JiejianError(ErrorCode.RESULT_FINALIZATION_NOT_FOUND, "结果最终化记录不存在")
        return record

    def _presentation_snapshot(self, run_id: str, project_id: str) -> ReportPresentation:
        """把确定性结果投影冻结进 BASE；不在后续读取或 Gate 处理中重算。"""

        if self._presentation is None:
            raise JiejianError(ErrorCode.REPORT_INPUT_INVALID, "报告展示投影未装配")
        presentation = self._presentation.build(run_id).model_dump(mode="json")
        # diagnosis 是 v2 机器事实；身份标签与 Evidence 来源角色仍只属于即时结果页。
        report_fields = set(ReportPresentation.model_fields)
        issue_fields = set(ReportPresentationIssue.model_fields)
        presentation = {
            key: value
            for key, value in presentation.items()
            if key in report_fields
        }
        presentation["issues"] = [
            {key: value for key, value in issue.items() if key in issue_fields}
            for issue in presentation.get("issues", [])
        ]
        snapshot = ReportPresentation.model_validate_json(
            json.dumps(
                presentation,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            strict=True,
        )
        if snapshot.run_id != run_id or snapshot.project_id != project_id:
            raise JiejianError(ErrorCode.REPORT_INPUT_INVALID, "报告展示快照与 Run 关联不一致")
        return snapshot

    @staticmethod
    def _run(view) -> ReportRun:
        return ReportRun(
            run_id=view.run.run_id,
            project_id=view.run.project_id,
            lifecycle=view.run.lifecycle.value,
            verdict=view.run.verdict.value if view.run.verdict is not None else None,
            created_at_us=view.run.created_at_us,
            finished_at_us=view.run.finished_at_us,
        )

    def _versions(self, view, artifact_summary: ArtifactSummary) -> ReportVersions:
        return ReportVersions(
            contract_id=view.run.contract_id,
            contract_version=view.run.contract_version,
            engine_version=view.run.engine_version,
            runner_schema_version=view.publication.result.schema_version,
            evidence_schema_version="1",
            observer_schema_version="1",
            artifact_schema_version="1",
            ruleset_versions=tuple(sorted({REPORT_RULESET_VERSION, *(item.ruleset_version for item in artifact_summary.results)})),
        )

    def _artifact_summary(self, run_id: str, project_id: str) -> ArtifactSummary:
        published = self._artifacts.for_run(run_id, project_id)
        if not published:
            return ArtifactSummary.create(ArtifactSummaryStatus.NOT_REQUESTED)
        if any(item.result is None for item in published):
            return ArtifactSummary.create(ArtifactSummaryStatus.INCONCLUSIVE, reason_codes=("ARTIFACT_RESULT_NOT_PUBLISHED",))
        artifacts = tuple(self._artifact(item.result) for item in published if item.result is not None)
        inconclusive = tuple(item.error_code for item in artifacts if item.status == "INCONCLUSIVE" and item.error_code)
        if inconclusive:
            return ArtifactSummary.create(ArtifactSummaryStatus.INCONCLUSIVE, artifacts, inconclusive)
        return ArtifactSummary.create(ArtifactSummaryStatus.COMPLETE, artifacts)

    @staticmethod
    def _runtime(view, stored_findings: list[dict[str, Any]]) -> ReportRuntime:
        result = view.publication.result
        evidence_refs = tuple(ReportEvidenceRef(evidence_id=item.evidence_id, source_type="RUNTIME") for item in view.evidence)
        findings = tuple(
            ReportFinding(
                finding_id=item["finding"]["finding_id"],
                source_type="RUNTIME",
                occurrence_id=item["occurrence"]["occurrence_id"],
                verdict=item["occurrence"]["verdict"],
                severity=item["occurrence"]["severity"],
                evidence_refs=tuple(ReportEvidenceRef(evidence_id=value, source_type="RUNTIME") for value in item["occurrence"]["evidence_refs"]),
            )
            for item in stored_findings
        )
        statuses: list[ReportObserverStatus] = []
        errors: list[str] = []
        if isinstance(result, RunnerResult):
            for evidence in result.evidence:
                statuses.extend(
                    ReportObserverStatus(observer_id=outcome.observer_id, required=outcome.required, status=outcome.status.value, reason_codes=outcome.reason_codes)
                    for outcome in evidence.outcomes
                )
            if result.error is not None:
                errors.append(result.error.code)
        elif result.error is not None:
            errors.append(result.error.code)
        return ReportRuntime(
            lifecycle=view.run.lifecycle.value,
            verdict=view.run.verdict.value if view.run.verdict is not None else None,
            evidence_refs=evidence_refs,
            findings=findings,
            observer_statuses=tuple(sorted(statuses, key=lambda item: item.observer_id)),
            execution_errors=tuple(sorted(set(errors))),
        )

    @staticmethod
    def _artifact(result) -> ReportArtifact:
        evidence = tuple(ReportEvidenceRef(evidence_id=item.evidence_id, source_type="ARTIFACT") for item in result.evidence)
        findings = tuple(
            ReportFinding(
                finding_id=item.finding_id,
                source_type="ARTIFACT",
                verdict="VULNERABLE",
                severity=item.severity,
                evidence_refs=(ReportEvidenceRef(evidence_id=item.evidence_id, source_type="ARTIFACT"),),
                rule_id=item.rule_id,
                category=item.category,
                path=item.path,
                message=item.message,
            )
            for item in result.findings
        )
        return ReportArtifact(
            artifact_id=result.artifact_id,
            status=result.status.value,
            verdict=result.verdict.value,
            error_code=result.error_code,
            manifest_sha256=result.manifest_sha256,
            ruleset_version=result.ruleset_version,
            evidence_refs=evidence,
            findings=findings,
        )

    @staticmethod
    def _limitations(view, runtime: ReportRuntime, artifact_summary: ArtifactSummary) -> tuple[str, ...]:
        values = set(runtime.execution_errors)
        if view.run.lifecycle is not RunLifecycle.COMPLETED:
            values.add("RUN_NOT_COMPLETED")
        if runtime.verdict == "INCONCLUSIVE":
            values.add("RUNTIME_INCONCLUSIVE")
        if any(item.required and item.status != "AVAILABLE" for item in runtime.observer_statuses):
            values.add("REQUIRED_OBSERVER_NOT_AVAILABLE")
        if artifact_summary.status is ArtifactSummaryStatus.INCONCLUSIVE:
            values.update(artifact_summary.reason_codes)
        return tuple(sorted(values))
