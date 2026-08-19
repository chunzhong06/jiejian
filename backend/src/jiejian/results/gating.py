# =============================================================================
# 阶段 7.2 回归基线与门禁应用服务
#
# 定位
#   API/CLI 共用的显式基线接受、已发布事实收集和 GateResult 持久化边界
#
# 约束
#   所有成功输入先经过 PublishedResultReader；Gate 只保存引用和摘要，
#   不执行 Verification、不修改 Run/Verdict、不自动选择最近 Run。
# =============================================================================

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from typing import Any

from ..domain.lifecycle import CaseVerdict, RunLifecycle
from ..errors import ErrorCode, JiejianError
from ..protocols import ObserverOutcomeStatus, RunnerResultV1, RunnerResultV2
from ..storage.repositories.gating import GateResultRecord, RegressionBaselineRecord
from ..verification.gating import (
    BaselineFindingRef,
    GateFacts,
    GateFinding,
    GatePolicy,
    GateResult,
    RegressionBaseline,
    baseline_id_for,
    canonical_sha256,
    evaluate_gate,
    gate_input_hash,
)
from .published import PublishedResultReader, PublishedRunView
from .stable_findings import FindingApplicationService


class GatingApplicationService:
    """基线和 Gate 的唯一应用编排；CLI 与 API 均调用此服务。"""

    def __init__(
        self,
        uow_factory,
        published_reader: PublishedResultReader,
        findings: FindingApplicationService,
        *,
        clock_us=None,
    ) -> None:
        self._uow_factory = uow_factory
        self._reader = published_reader
        self._findings = findings
        self._clock_us = clock_us or (lambda: time.time_ns() // 1_000)

    def accept_baseline(self, run_id: str, *, actor: str, reason: str, expected_project_id: str | None = None) -> dict[str, Any]:
        view = self._reader.read(run_id)
        if expected_project_id is not None and view.run.project_id != expected_project_id:
            raise JiejianError(ErrorCode.GATE_INPUT_INVALID, "基线与项目路径不匹配")
        if view.run.lifecycle is not RunLifecycle.COMPLETED:
            raise JiejianError(ErrorCode.BASELINE_INVALID, "只有 COMPLETED Run 可以接受为回归基线")
        findings = self._findings.findings_for_run(run_id)
        facts = _published_facts(self._reader, view, findings)
        baseline = _build_baseline(view, facts, findings, actor=actor, reason=reason, accepted_at_us=self._clock_us())
        with self._uow_factory() as work:
            existing = work.gating.get_baseline_for_run(view.run.project_id, run_id)
            if existing is not None:
                current = _baseline_from_record(existing)
                current_payload = current.model_dump(mode="json")
                baseline_payload = baseline.model_dump(mode="json")
                current_payload.pop("accepted_at_us")
                baseline_payload.pop("accepted_at_us")
                if current_payload != baseline_payload:
                    raise JiejianError(ErrorCode.BASELINE_IMMUTABLE, "该 Run 已存在不可变基线")
                return current.model_dump(mode="json")
            work.gating.add_baseline(_baseline_record(baseline))
            work.commit()
        return baseline.model_dump(mode="json")

    def get_baseline(self, baseline_id: str) -> dict[str, Any]:
        with self._uow_factory() as work:
            record = work.gating.get_baseline(baseline_id)
        if record is None:
            raise JiejianError(ErrorCode.BASELINE_NOT_FOUND, "回归基线不存在")
        return _baseline_from_record(record).model_dump(mode="json")

    def evaluate(self, baseline_id: str, run_id: str, *, policy: GatePolicy | None = None) -> dict[str, Any]:
        policy = policy or GatePolicy()
        with self._uow_factory() as work:
            baseline_record = work.gating.get_baseline(baseline_id)
        if baseline_record is None:
            raise JiejianError(ErrorCode.BASELINE_NOT_FOUND, "回归基线不存在")
        baseline = _baseline_from_record(baseline_record)

        try:
            view = self._reader.read(run_id)
        except (JiejianError, KeyError, TypeError, ValueError) as exc:
            facts = _error_facts(self._uow_factory, baseline, run_id, getattr(exc, "code", "PUBLICATION_READ_ERROR"))
        else:
            if view.run.project_id != baseline.project_id:
                raise JiejianError(ErrorCode.GATE_INPUT_INVALID, "基线与当前 Run 不属于同一项目")
            try:
                findings = self._findings.findings_for_run(run_id)
                facts = _published_facts(self._reader, view, findings)
            except (JiejianError, KeyError, TypeError, ValueError) as exc:
                facts = _error_facts(self._uow_factory, baseline, run_id, getattr(exc, "code", "PUBLICATION_READ_ERROR"))

        provisional = evaluate_gate(baseline, facts, policy)
        with self._uow_factory() as work:
            existing = work.gating.get_gate_result_for_input(
                baseline.baseline_id,
                run_id,
                policy.policy_version,
                provisional.input_hash,
            )
            if existing is not None:
                return _gate_result_from_record(existing).model_dump(mode="json")
            result = provisional.model_copy(update={"evaluated_at_us": self._clock_us()})
            work.gating.add_gate_result(_gate_result_record(result, baseline.project_id))
            work.commit()
        return result.model_dump(mode="json")

    def get_gate_result(self, gate_result_id: str) -> dict[str, Any]:
        with self._uow_factory() as work:
            record = work.gating.get_gate_result(gate_result_id)
        if record is None:
            raise JiejianError(ErrorCode.GATE_RESULT_NOT_FOUND, "GateResult 不存在")
        return _gate_result_from_record(record).model_dump(mode="json")

    def latest_gate_result(self, baseline_id: str, run_id: str) -> dict[str, Any]:
        with self._uow_factory() as work:
            record = work.gating.latest_gate_result(baseline_id, run_id)
        if record is None:
            raise JiejianError(ErrorCode.GATE_RESULT_NOT_FOUND, "该基线与 Run 尚无 GateResult")
        return _gate_result_from_record(record).model_dump(mode="json")


def _build_baseline(view: PublishedRunView, facts: GateFacts, findings: list[dict[str, Any]], *, actor: str, reason: str, accepted_at_us: int) -> RegressionBaseline:
    refs = tuple(
        BaselineFindingRef(
            finding_id=item["finding"]["finding_id"],
            occurrence_id=item["occurrence"]["occurrence_id"],
            evidence_ids=tuple(item["occurrence"]["evidence_refs"]),
        )
        for item in sorted(findings, key=lambda value: value["finding"]["finding_id"])
    )
    return RegressionBaseline(
        baseline_id=baseline_id_for(view.run.project_id, view.run.run_id, facts.request_snapshot_sha256 or canonical_sha256(view.run), canonical_sha256(facts.coverage_ids)),
        project_id=view.run.project_id,
        accepted_run_id=view.run.run_id,
        finding_refs=refs,
        coverage_ids=facts.coverage_ids,
        coverage_digest=canonical_sha256(facts.coverage_ids),
        request_snapshot_sha256=facts.request_snapshot_sha256 or canonical_sha256(view.run),
        engine_version=facts.engine_version or view.run.engine_version,
        protocol_versions=facts.protocol_versions or (f"runner-result-{view.publication.result.schema_version}",),
        actor=actor,
        reason=reason,
        accepted_at_us=accepted_at_us,
    )


def _published_facts(reader: PublishedResultReader, view: PublishedRunView, findings: list[dict[str, Any]]) -> GateFacts:
    result = view.publication.result
    snapshot = reader.request_snapshot(view)
    request_hash = canonical_sha256(snapshot)
    gate_findings = tuple(
        GateFinding(
            finding_id=item["finding"]["finding_id"],
            occurrence_id=item["occurrence"]["occurrence_id"],
            status=item["occurrence"]["status"],
            verdict=CaseVerdict(item["occurrence"]["verdict"]),
            severity=item["occurrence"]["severity"],
        )
        for item in findings
    )
    if isinstance(result, RunnerResultV2):
        case_map = {case.case_id: case for case in snapshot.plan.cases}
        coverage_ids = tuple(sorted(
            f"case:{evidence.case_snapshot.case_id}:{case_map[evidence.case_snapshot.case_id].fingerprint}"
            for evidence in result.evidence
            if evidence.case_snapshot.case_id in case_map
        ))
        required_issues: list[str] = []
        inconclusive: list[str] = []
        observer_errors: list[str] = []
        for evidence in result.evidence:
            for outcome in evidence.outcomes:
                if outcome.required and outcome.status.value != "AVAILABLE":
                    required_issues.append(f"{evidence.case_snapshot.case_id}:{outcome.observer_id}:{outcome.status.value}")
                if outcome.status is ObserverOutcomeStatus.EXECUTION_ERROR:
                    observer_errors.append(f"{evidence.case_snapshot.case_id}:{outcome.observer_id}:{outcome.status.value}")
            if evidence.verdict is CaseVerdict.INCONCLUSIVE:
                inconclusive.append(evidence.case_snapshot.case_id)
        if result.verdict is not None and result.verdict.value == "INCONCLUSIVE":
            inconclusive.append(view.run.run_id)
        errors = tuple(sorted(set(observer_errors + ([] if result.error is None else [str(result.error.code)]))))
        return GateFacts(
            run_id=view.run.run_id,
            project_id=view.run.project_id,
            lifecycle=view.run.lifecycle,
            verdict=view.run.verdict,
            publication_validated=True,
            findings=gate_findings,
            coverage_ids=coverage_ids,
            coverage_gap_count=result.coverage_gap_count,
            required_observer_issues=tuple(sorted(set(required_issues))),
            inconclusive_reasons=tuple(sorted(set(inconclusive))),
            execution_errors=errors,
            request_snapshot_sha256=request_hash,
            engine_version=view.run.engine_version,
            protocol_versions=("runner-result-v2", "observer-v2"),
        )
    if isinstance(result, RunnerResultV1):
        plan = reader.document(view, "artifacts/mutation-plan.json")
        cases = {item["case_id"]: item for item in plan.get("cases", ()) if isinstance(item, Mapping)}
        coverage_ids = tuple(sorted(
            f"case:{record.case_id}:{cases[record.case_id].get('fingerprint', record.case_id)}"
            for record in view.evidence
            if record.case_id in cases
        ))
        required_issues: list[str] = []
        inconclusive: list[str] = []
        for record in view.evidence:
            document = reader.evidence_document(view, record.evidence_id)
            if document.get("verdict") == "INCONCLUSIVE":
                inconclusive.append(record.case_id)
            case = cases.get(record.case_id, {})
            observations = document.get("observations", ())
            if case.get("required_observers") and not observations:
                required_issues.append(f"{record.case_id}:owner_api:MISSING")
        return GateFacts(
            run_id=view.run.run_id,
            project_id=view.run.project_id,
            lifecycle=view.run.lifecycle,
            verdict=view.run.verdict,
            publication_validated=True,
            findings=gate_findings,
            coverage_ids=coverage_ids,
            coverage_gap_count=0,
            required_observer_issues=tuple(sorted(set(required_issues))),
            inconclusive_reasons=tuple(sorted(set(inconclusive))),
            execution_errors=(),
            request_snapshot_sha256=request_hash,
            engine_version=view.run.engine_version,
            protocol_versions=("runner-result-v1",),
        )
    raise TypeError("unsupported published result version")


def _error_facts(uow_factory, baseline: RegressionBaseline, run_id: str, code: str) -> GateFacts:
    with uow_factory() as work:
        run = work.runs.get(run_id)
    lifecycle = run.lifecycle if run is not None else RunLifecycle.FAILED
    verdict = run.verdict if run is not None else None
    project_id = run.project_id if run is not None else baseline.project_id
    return GateFacts(
        run_id=run_id,
        project_id=project_id,
        lifecycle=lifecycle,
        verdict=verdict,
        publication_validated=False,
        findings=(),
        coverage_ids=(),
        coverage_gap_count=0,
        required_observer_issues=(),
        inconclusive_reasons=(),
        execution_errors=(code,),
    )


def _baseline_record(value: RegressionBaseline) -> RegressionBaselineRecord:
    return RegressionBaselineRecord(
        baseline_id=value.baseline_id,
        project_id=value.project_id,
        accepted_run_id=value.accepted_run_id,
        finding_refs_json=json.dumps([item.model_dump(mode="json") for item in value.finding_refs], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        coverage_ids_json=json.dumps(value.coverage_ids, ensure_ascii=False, separators=(",", ":")),
        coverage_digest=value.coverage_digest,
        request_snapshot_sha256=value.request_snapshot_sha256,
        engine_version=value.engine_version,
        protocol_versions_json=json.dumps(value.protocol_versions, ensure_ascii=False, separators=(",", ":")),
        actor=value.actor,
        reason=value.reason,
        accepted_at_us=value.accepted_at_us,
    )


def _baseline_from_record(value: RegressionBaselineRecord) -> RegressionBaseline:
    return RegressionBaseline(
        baseline_id=value.baseline_id,
        project_id=value.project_id,
        accepted_run_id=value.accepted_run_id,
        finding_refs=tuple(json.loads(value.finding_refs_json)),
        coverage_ids=tuple(json.loads(value.coverage_ids_json)),
        coverage_digest=value.coverage_digest,
        request_snapshot_sha256=value.request_snapshot_sha256,
        engine_version=value.engine_version,
        protocol_versions=tuple(json.loads(value.protocol_versions_json)),
        actor=value.actor,
        reason=value.reason,
        accepted_at_us=value.accepted_at_us,
    )


def _gate_result_record(value: GateResult, project_id: str) -> GateResultRecord:
    return GateResultRecord(
        gate_result_id=value.gate_result_id,
        baseline_id=value.baseline_id,
        project_id=project_id,
        run_id=value.run_id,
        policy_version=value.policy_version,
        input_hash=value.input_hash,
        reasons_json=json.dumps([item.model_dump(mode="json") for item in value.reasons], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        decision=value.decision.value,
        evaluated_at_us=value.evaluated_at_us,
    )


def _gate_result_from_record(value: GateResultRecord) -> GateResult:
    return GateResult(
        gate_result_id=value.gate_result_id,
        baseline_id=value.baseline_id,
        run_id=value.run_id,
        policy_version=value.policy_version,
        input_hash=value.input_hash,
        reasons=tuple(json.loads(value.reasons_json)),
        decision=value.decision,
        evaluated_at_us=value.evaluated_at_us,
    )
