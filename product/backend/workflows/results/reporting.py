# =============================================================================
# 统一报告应用服务
#
# 定位
# 已发布 Run、稳定 Finding、GateResult 与 Artifact Result 的只读报告组合边界。
#
# 职责
# 核对报告输入｜构造统一 Report｜持久化格式投影｜读取既有报告 publication
#
# 边界
# 只消费已发布事实，不调用 Verification、Gate evaluate 或扫描器，也不修改任何 Verdict。
#
# 调用链
# CLI / API → ReportBuilder → PublishedResultReader / Finding / Gate / Artifact stores
# =============================================================================

from __future__ import annotations

from collections.abc import Iterable
import json
from typing import Any

from product.backend.core.lifecycle import RunLifecycle
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import RunnerResult
from product.backend.core.verification.gating import GateResult
from product.backend.infra.artifacts.report_reader import ArtifactResultReader
from product.protocols.report import ReportArtifact, ReportEvidenceRef, ReportFinding, ReportGate, ReportObserverStatus, ReportRun, ReportRuntime, Report, ReportVersions, REPORT_RULESET_VERSION, canonical_sha256, report_id_for
from product.backend.infra.artifacts.report_store import ReportStore


class ReportBuilder:
    """生成、读取和列举独立报告 publication。"""

    def __init__(self, var_dir, results, findings, gating) -> None:
        self._results = results
        self._findings = findings
        self._gating = gating
        self._artifacts = ArtifactResultReader(var_dir)
        self._publication = ReportStore(var_dir)

    def generate(self, run_id: str, gate_result_id: str) -> dict[str, Any]:
        """核对同一 Run 的发布事实与 GateResult，生成一次不可变报告 publication。"""

        # --- 阶段：读取并交叉核对已发布输入 ---
        view = self._results.read(run_id)
        gate_payload = self._gating.get_gate_result(gate_result_id)
        gate = GateResult.model_validate_json(json.dumps(gate_payload, ensure_ascii=False), strict=True)
        baseline = self._gating.get_baseline(gate.baseline_id)
        if gate.run_id != run_id or baseline["project_id"] != view.run.project_id:
            raise JiejianError(ErrorCode.REPORT_INPUT_INVALID, "报告与明确 GateResult 关联不一致")

        stored_findings = self._stored_findings(run_id)
        artifacts = self._artifacts.for_run(run_id, view.run.project_id)
        runtime = self._runtime(view, stored_findings)
        artifact_models = tuple(self._artifact(item.result) for item in artifacts)
        limitations = self._limitations(view, runtime, artifact_models)
        result = view.publication.result
        runner_version = result.schema_version
        observer_version = "2"
        semantic_input = canonical_sha256(
            {
                "run_publication_sha256": view.publication.manifest.result_sha256,
                "runtime": runtime.model_dump(mode="json"),
                "artifacts": [item.model_dump(mode="json") for item in artifact_models],
                "gate": gate.model_dump(mode="json"),
                "versions": {
                    "contract_id": view.run.contract_id,
                    "contract_version": view.run.contract_version,
                    "engine_version": view.run.engine_version,
                    "runner_schema_version": runner_version,
                    "observer_schema_version": observer_version,
                    "report_schema_version": "2",
                    "ruleset_versions": sorted({REPORT_RULESET_VERSION, *(item.ruleset_version for item in artifact_models)}),
                },
            }
        )
        # --- 阶段：构造统一领域报告 ---
        report = Report.create(
            report_id=report_id_for(run_id, gate_result_id, semantic_input),
            run_id=run_id,
            project_id=view.run.project_id,
            gate_result_id=gate_result_id,
            semantic_input_sha256=semantic_input,
            run=ReportRun(
                run_id=run_id,
                project_id=view.run.project_id,
                lifecycle=view.run.lifecycle.value,
                verdict=view.run.verdict.value if view.run.verdict is not None else None,
                created_at_us=view.run.created_at_us,
                finished_at_us=view.run.finished_at_us,
            ),
            runtime=runtime,
            artifacts=artifact_models,
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
            versions=ReportVersions(
                contract_id=view.run.contract_id,
                contract_version=view.run.contract_version,
                engine_version=view.run.engine_version,
                runner_schema_version=runner_version,
                observer_schema_version=observer_version,
                ruleset_versions=tuple(sorted({REPORT_RULESET_VERSION, *(item.ruleset_version for item in artifact_models)})),
            ),
            limitations=limitations,
        )
        # --- 阶段：原子发布 canonical 与格式投影 ---
        self._publication.publish(report)
        return report.model_dump(mode="json")

    def read(self, run_id: str, report_id: str) -> dict[str, Any]:
        return self._publication.read(run_id, report_id).model_dump(mode="json")

    def read_format(self, run_id: str, report_id: str, output_format: str) -> bytes:
        return self._publication.read_format(run_id, report_id, output_format)

    def list(self, run_id: str) -> list[dict[str, str]]:
        return self._publication.list(run_id)

    def _stored_findings(self, run_id: str) -> list[dict[str, Any]]:
        method = getattr(self._findings, "stored_findings_for_run", None)
        if method is None:
            raise JiejianError(ErrorCode.REPORT_INPUT_INVALID, "Finding 持久化读取能力不可用")
        return method(run_id)

    @staticmethod
    def _runtime(view, stored_findings: list[dict[str, Any]]) -> ReportRuntime:
        result = view.publication.result
        evidence_refs = tuple(
            ReportEvidenceRef(evidence_id=item.evidence_id, source_type="RUNTIME")
            for item in view.evidence
        )
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
        observer_statuses: list[ReportObserverStatus] = []
        execution_errors: list[str] = []
        if isinstance(result, RunnerResult):
            for evidence in result.evidence:
                for outcome in evidence.outcomes:
                    observer_statuses.append(
                        ReportObserverStatus(
                            observer_id=outcome.observer_id,
                            required=outcome.required,
                            status=outcome.status.value,
                            reason_codes=outcome.reason_codes,
                        )
                    )
            if result.error is not None:
                execution_errors.append(result.error.code)
        elif result.error is not None:
            execution_errors.append(result.error.code)
        return ReportRuntime(
            lifecycle=view.run.lifecycle.value,
            verdict=view.run.verdict.value if view.run.verdict is not None else None,
            evidence_refs=evidence_refs,
            findings=findings,
            observer_statuses=tuple(sorted(observer_statuses, key=lambda item: item.observer_id)),
            execution_errors=tuple(sorted(set(execution_errors))),
        )

    @staticmethod
    def _artifact(result) -> ReportArtifact:
        evidence = tuple(
            ReportEvidenceRef(evidence_id=item.evidence_id, source_type="ARTIFACT")
            for item in result.evidence
        )
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
    def _limitations(view, runtime: ReportRuntime, artifacts: Iterable[ReportArtifact]) -> tuple[str, ...]:
        artifacts = tuple(artifacts)
        values = set(runtime.execution_errors)
        if view.run.lifecycle is not RunLifecycle.COMPLETED:
            values.add("RUN_NOT_COMPLETED")
        if runtime.verdict == "INCONCLUSIVE":
            values.add("RUNTIME_INCONCLUSIVE")
        if any(item.required and item.status != "AVAILABLE" for item in runtime.observer_statuses):
            values.add("REQUIRED_OBSERVER_NOT_AVAILABLE")
        if not artifacts:
            values.add("NO_ARTIFACT_RESULT")
        for artifact in artifacts:
            if artifact.status == "INCONCLUSIVE":
                values.add("ARTIFACT_INCONCLUSIVE")
            if artifact.error_code is not None:
                values.add("ARTIFACT_ERROR")
        return tuple(sorted(values))
