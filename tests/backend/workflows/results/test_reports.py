# 验证结果工作流中的报告生成。

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import RunLifecycle, RunVerdict
from product.backend.core.repair import (
    RepairContractReference,
    RepairRequirementView,
    RepairVerification,
    RepairVerificationStatus,
)
from product.backend.core.verification.breakpoints import (
    BreakpointPrecision,
    BreakpointType,
)
from product.backend.core.verification.continuity import AuthorizationContinuityState
from product.backend.core.verification.facts import ExecutionOutcome, ObservedEffect
from product.backend.core.verification.trace import TraceEventKind
from product.backend.core.reporting import render_html, render_junit, render_sarif
from product.backend.infra.artifacts.report_store import ReportStore
from product.backend.infra.artifacts import report_store as report_store_module
from product.backend.workflows.results.reporting import ReportBuilder
from product.backend.workflows.results.presentation import (
    PresentedCaseVerdict,
    ResultClaimBoundary,
    ResultConfirmedImpact,
    ResultDiagnosis,
    ResultEvidenceSource,
    ResultPresentation,
    ResultPresentationIssue,
    ResultRelevantIntent,
    ResultWitnessItem,
)
from product.protocols import ObserverType
from product.protocols.artifacts import (
    ArtifactCheckRequest,
    ArtifactResultFile,
    ArtifactResultManifest,
    ArtifactScanResult,
    ArtifactScanStatus,
    ArtifactVerdict,
)
from product.protocols.report import (
    ArtifactSummary,
    ArtifactSummaryStatus,
    BaseRunReport,
    GateRunReport,
    ReportGate,
    ReportConfirmedImpact,
    ReportDiagnosis,
    ReportPackageManifest,
    ReportPresentation,
    ReportPresentationIssue,
    ReportRun,
    ReportRuntime,
    ReportVersions,
    ReportWitnessItem,
    base_semantic_input_sha256,
    gate_semantic_input_sha256,
    parse_report_document,
    report_json_schema,
    report_id_for,
)


RUN_ID = "run_" + "a" * 32
PROJECT_ID = "report-project"
GATE_ID = "gate_" + "b" * 32
EVIDENCE_ID = "ev_" + "d" * 20


def _result_diagnosis() -> ResultDiagnosis:
    witness = tuple(
        ResultWitnessItem(
            kind=kind,
            label=label,
            detail=detail,
            event_id=(f"event-{index}" if index > 1 else None),
            evidence_refs=(EVIDENCE_ID,),
        )
        for index, (kind, label, detail) in enumerate(
            (
                ("PERMISSION_REQUIREMENT", "权限要求", "不应允许导出"),
                ("ACTUAL_IDENTITY", "实际身份", "普通成员"),
                ("PROTECTED_EFFECT", "本不该发生的业务后果", "归档已经生成"),
                ("AUTHORIZATION_CONTINUITY", "合法授权来源", "找不到符合原权限要求的合法授权来源"),
                ("BREAKPOINT", "首个可证明断裂", "权限决定发生过晚"),
                ("AMPLIFIERS", "后续扩大影响的行为", "后台任务继续执行"),
                ("CONFIRMED_IMPACT", "最终业务影响", "归档已经生成"),
            ),
            start=1,
        )
    )
    return ResultDiagnosis(
        case_id="case-diagnosis",
        action_id="export-package",
        breakpoint_type=BreakpointType.AUTHORIZATION_LATE,
        precision=BreakpointPrecision.EXACT,
        continuity_state=AuthorizationContinuityState.ORPHAN_EFFECT_CONFIRMED,
        first_violation_event_id="event-5",
        amplifier_types=(BreakpointType.AUTHORITY_EXPANSION,),
        summary="首个可证明断裂：权限决定发生过晚",
        minimal_witness=witness,
        confirmed_impacts=(
            ResultConfirmedImpact(
                event_id="event-impact",
                parent_event_ids=("event-4",),
                kind=TraceEventKind.FINAL_EFFECT,
                semantic_key="archive_generated",
                effect_id="archive-created",
                summary="已确认：最终后果",
                evidence_refs=(EVIDENCE_ID,),
            ),
        ),
        evidence_refs=(EVIDENCE_ID,),
    )


def _report_diagnosis() -> ReportDiagnosis:
    value = _result_diagnosis().model_dump(mode="json")
    value = {
        key: item
        for key, item in value.items()
        if key in ReportDiagnosis.model_fields
    }
    return ReportDiagnosis.model_validate_json(
        json.dumps(value, ensure_ascii=False),
        strict=True,
    )


def _versions() -> ReportVersions:
    return ReportVersions(
        contract_id="contract",
        contract_version=1,
        engine_version="engine-v1",
        runner_schema_version="1",
        evidence_schema_version="1",
        observer_schema_version="1",
        artifact_schema_version="1",
    )


def _presentation(*, verdict: str | None = None) -> ReportPresentation:
    return ReportPresentation(
        run_id=RUN_ID,
        project_id=PROJECT_ID,
        project_name="报告测试项目",
        run_lifecycle="COMPLETED",
        verdict=verdict,
        policy_epoch=4,
        policy_fingerprint="e" * 64,
        headline="结果不可用" if verdict is None else "发现权限问题",
        scope_statement="当前运行没有形成可用安全结论。",
        checked_count=0,
        safe_count=0,
        problem_count=0,
        inconclusive_count=0,
        uncovered_count=0,
    )


def test_report_snapshot_omits_result_page_only_evidence_source_projection(
    tmp_path: Path,
) -> None:
    repair_reference = RepairContractReference(
        source_run_id=RUN_ID,
        source_finding_id="finding_" + "c" * 32,
        repair_fingerprint="9" * 64,
    )
    issue = ResultPresentationIssue(
        finding_id="finding_" + "c" * 32,
        title="成员账号不应导出项目资料",
        subject_group="成员账号",
        action_id="export-project-package",
        action="导出",
        resource="项目资料",
        relation="受权限规则约束",
        expectation="不应允许这次操作，资源也不应发生变化",
        surface_result="页面或接口显示已拒绝",
        actual_result="真实资源已经发生变化",
        conclusion="发现权限问题",
        explanation="可信观察确认发生了不应出现的真实变化。",
        planned_identity_id="member-account",
        planned_identity_label="成员账号",
        severity="critical",
        evidence_refs=("ev_" + "d" * 20,),
        evidence_sources=(
            ResultEvidenceSource(
                observer_type=ObserverType.OWNER_API,
                label="目标业务状态",
                role="KEY",
                status="FOUND",
                evidence_refs=("ev_" + "d" * 20,),
            ),
        ),
        verdict=PresentedCaseVerdict.VULNERABLE,
        occurrence_status="APPEARED",
        diagnosis=_result_diagnosis(),
        claim_boundary=ResultClaimBoundary(
            surface_response_status=ExecutionOutcome.DENIED,
            business_effect_status=ObservedEffect.CONFIRMED,
            actual_identity_status="UNAVAILABLE",
            breakpoint_precision=BreakpointPrecision.EXACT,
            supported_statement="计划使用成员账号凭据的实验中，项目资料已经导出。",
            unsupported_statements=("不能宣称服务器已经独立确认实际执行主体。",),
        ),
        repair_requirement=RepairRequirementView(
            reference=repair_reference,
            must_disappear="普通成员修改后，受保护文档变化必须消失。",
            must_remain="项目负责人仍能正常修改文档。",
            must_not_change=("原拒绝权限", "关键证据要求"),
        ),
    )
    result_view = ResultPresentation(
        run_id=RUN_ID,
        project_id=PROJECT_ID,
        project_name="报告测试项目",
        run_lifecycle=RunLifecycle.COMPLETED,
        verdict=RunVerdict.BLOCK,
        policy_epoch=4,
        policy_fingerprint="e" * 64,
        relevant_intents=(
            ResultRelevantIntent(
                intent_id="pin_" + "f" * 32,
                revision=2,
                intent_hash="a" * 64,
            ),
        ),
        headline="发现权限问题",
        scope_statement="当前检查确认存在权限问题。",
        checked_count=1,
        safe_count=0,
        problem_count=1,
        inconclusive_count=0,
        uncovered_count=0,
        issues=(issue,),
        repair_verification=RepairVerification(
            reference=repair_reference,
            verification_run_id=RUN_ID,
            status=RepairVerificationStatus.NOT_VERIFIED,
            message="原违规业务后果仍然存在。",
            reason_codes=("DENY_EFFECT_STILL_PRESENT",),
        ),
    )
    builder = ReportBuilder(
        tmp_path,
        None,
        None,
        None,
        presentation=SimpleNamespace(build=lambda _: result_view),
    )

    snapshot = builder._presentation_snapshot(RUN_ID, PROJECT_ID)

    assert snapshot.issues[0].evidence_refs == issue.evidence_refs
    assert snapshot.policy_epoch == 4
    assert snapshot.policy_fingerprint == "e" * 64
    assert snapshot.relevant_intents[0].intent_id == "pin_" + "f" * 32
    assert "evidence_sources" not in snapshot.issues[0].model_dump(mode="json")
    assert "planned_identity_id" not in snapshot.issues[0].model_dump(mode="json")
    assert snapshot.issues[0].diagnosis is not None
    assert snapshot.issues[0].diagnosis.breakpoint_type == "AUTHORIZATION_LATE"
    assert snapshot.issues[0].diagnosis.minimal_witness[4].kind == "BREAKPOINT"
    assert snapshot.issues[0].repair_requirement is not None
    assert snapshot.repair_verification is not None
    assert snapshot.repair_verification.status == "NOT_VERIFIED"
    rendered = render_html(_base(verdict="BLOCK", presentation=snapshot)).decode("utf-8")
    assert "修复要求未通过" in rendered
    assert "项目负责人仍能正常修改文档" in rendered


def _base(
    status: ArtifactSummaryStatus = ArtifactSummaryStatus.NOT_REQUESTED,
    *,
    verdict: str | None = None,
    presentation: ReportPresentation | None = None,
) -> BaseRunReport:
    versions = _versions()
    summary = ArtifactSummary.create(status)
    run = ReportRun(
        run_id=RUN_ID,
        project_id=PROJECT_ID,
        lifecycle="COMPLETED",
        verdict=verdict,
        created_at_us=1,
        finished_at_us=2,
    )
    runtime = ReportRuntime(
        lifecycle="COMPLETED",
        verdict=verdict,
        evidence_refs=(),
        findings=(),
        observer_statuses=(),
    )
    semantic = base_semantic_input_sha256(RUN_ID, "a" * 64, "b" * 64, summary.snapshot_sha256, versions)
    return BaseRunReport.create(
        report_type="BASE",
        report_id=report_id_for("BASE", semantic),
        run_id=RUN_ID,
        project_id=PROJECT_ID,
        semantic_input_sha256=semantic,
        run=run,
        runtime=runtime,
        presentation=presentation or _presentation(verdict=verdict),
        artifact_summary=summary,
        versions=versions,
    )


def _write_artifact_request(
    var_dir: Path,
    *,
    result: ArtifactScanResult | None = None,
) -> Path:
    job_dir = var_dir / "data" / "artifact-checks" / "jobs" / "artifact-report-job"
    job_dir.mkdir(parents=True)
    request = ArtifactCheckRequest(
        project_id=PROJECT_ID,
        artifact_id="build-1",
        run_id=RUN_ID,
        artifact_root=str((var_dir / "artifact-root").resolve()),
        manifest_path=str((var_dir / "publication-manifest.json").resolve()),
    )
    (job_dir / "request.json").write_bytes(
        json.dumps(
            request.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    if result is None:
        return job_dir
    published = job_dir / "published"
    published.mkdir()
    result_raw = json.dumps(
        result.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    result_sha256 = hashlib.sha256(result_raw).hexdigest()
    manifest = ArtifactResultManifest(
        artifact_id=result.artifact_id,
        project_id=result.project_id,
        result_sha256=result_sha256,
        input_manifest_sha256=result.manifest_sha256,
        files=(
            ArtifactResultFile(
                path="artifact-result.json",
                byte_count=len(result_raw),
                sha256=result_sha256,
            ),
        ),
    )
    (published / "artifact-result.json").write_bytes(result_raw)
    (published / "artifact-check-manifest.json").write_bytes(
        json.dumps(
            manifest.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return job_dir


def test_current_report_discriminator_and_versions_fail_closed() -> None:
    base = _base()
    encoded = base.model_dump(mode="json")
    assert parse_report_document(encoded).report_type == "BASE"
    for invalid in (
        {**encoded, "schema_version": "1"},
        {key: value for key, value in encoded.items() if key != "schema_version"},
        {**encoded, "unexpected": True},
        {**encoded, "gate_result_id": GATE_ID},
    ):
        with pytest.raises(ValueError):
            parse_report_document(invalid)
    with pytest.raises(ValueError):
        ReportVersions(
            contract_id="contract", contract_version=1, engine_version="engine-v1",
            runner_schema_version="2", evidence_schema_version="1", observer_schema_version="1", artifact_schema_version="1",
        )


def test_current_report_checked_in_schema_matches_runtime_union() -> None:
    schema_path = Path("product/protocols/schemas/reports/report.schema.json")
    assert json.loads(schema_path.read_text(encoding="utf-8")) == report_json_schema()
    manifest_path = Path(
        "product/protocols/schemas/reports/report-package-manifest.schema.json"
    )
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == (
        ReportPackageManifest.model_json_schema()
    )


def test_base_and_gate_ids_and_bytes_are_deterministic(tmp_path: Path) -> None:
    base = _base(verdict="BLOCK")
    gate_input = gate_semantic_input_sha256(base.report_id, base.canonical_sha256, GATE_ID, "c" * 64)
    gate = GateRunReport.create(
        report_type="GATE",
        report_id=report_id_for("GATE", gate_input),
        run_id=RUN_ID,
        project_id=PROJECT_ID,
        base_report_id=base.report_id,
        base_report_sha256=base.canonical_sha256,
        gate_result_id=GATE_ID,
        semantic_input_sha256=gate_input,
        run=base.run,
        runtime=base.runtime,
        presentation=base.presentation,
        artifact_summary=base.artifact_summary,
        versions=base.versions,
        limitations=base.limitations,
        gate=ReportGate(
            gate_result_id=GATE_ID, baseline_id="baseline_" + "c" * 32, run_id=RUN_ID,
            policy_version="gate-v1", input_hash="c" * 64, decision="PASS", reasons=(), evaluated_at_us=3,
        ),
    )
    store = ReportStore(tmp_path / "var")
    base_manifest = store.publish(base)
    gate_manifest = store.publish(gate)
    assert store.publish(base) == base_manifest
    assert store.publish(gate) == gate_manifest
    assert store.read(RUN_ID, base.report_id).model_dump(mode="json") == base.model_dump(mode="json")
    assert store.read(RUN_ID, gate.report_id).model_dump(mode="json") == gate.model_dump(mode="json")
    assert render_html(base) == render_html(base)
    assert b"Gate decision" not in render_html(base)
    assert b"Gate decision" in render_html(gate)
    gate_html = render_html(gate).decode("utf-8")
    assert "Gate decision：PASS" in gate_html
    assert "安全结论：BLOCK" in gate_html
    assert json.loads(store.read_format(RUN_ID, base.report_id, "sarif"))["runs"][0]["invocations"][0]["executionSuccessful"] is True


def test_html_uses_presentation_snapshot_and_escapes_dynamic_content() -> None:
    injected = '<script>alert("x")</script> & "quoted"'
    issue = ReportPresentationIssue(
        finding_id="finding_" + "c" * 32,
        title="权限问题 & <script>",
        subject_group="普通用户",
        action=injected,
        resource="资源 & \"R\"",
        relation="自己的资源",
        expectation="不应允许",
        surface_result="页面返回拒绝",
        actual_result="数据已经变化",
        conclusion="权限限制未生效",
        explanation=injected,
        severity="high",
        evidence_refs=("ev_" + "d" * 20,),
        verdict="VULNERABLE",
        diagnosis=_report_diagnosis(),
    )
    presentation = ReportPresentation(
        run_id=RUN_ID,
        project_id=PROJECT_ID,
        project_name=injected,
        run_lifecycle="COMPLETED",
        verdict="BLOCK",
        policy_epoch=4,
        policy_fingerprint="e" * 64,
        headline="发现权限问题",
        scope_statement="本次只覆盖已确认范围 & <限制>",
        checked_count=1,
        safe_count=0,
        problem_count=1,
        inconclusive_count=0,
        uncovered_count=2,
        issues=(issue,),
        limitations=("业务限制 & <script>",),
    )
    document = render_html(_base(verdict="BLOCK", presentation=presentation)).decode("utf-8")
    assert "界鉴 · 权限安全检查报告" in document
    assert '<html lang="zh-CN" id="dark-theme">' in document
    assert ":root:target{color-scheme:dark" in document
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; &quot;quoted&quot;" in document
    assert '<div class="summary-item"><span>检查项</span><strong>1</strong>' in document
    assert '<div class="summary-item"><span>未覆盖</span><strong>2</strong>' in document
    assert "权限版本 <strong>4</strong>" in document
    assert "权限策略指纹" in document
    assert '<article class="issue-card">' in document
    assert "可信观察到的真实结果" in document
    assert "权限断裂诊断" in document
    assert "权限决定发生过晚" in document
    assert "已确认：最终后果" in document
    assert 'severity-high">高风险' in document
    assert "<th>标题</th>" not in document
    assert "本次只覆盖已确认范围 &amp; &lt;限制&gt;" in document
    assert "<script" not in document
    assert "<form" not in document
    assert "http://" not in document and "https://" not in document
    assert "src=" not in document and "url(" not in document


def test_presentation_is_canonical_and_gate_copies_base_safety_facts() -> None:
    issue = ReportPresentationIssue(
        finding_id="finding_" + "c" * 32,
        title="权限问题",
        subject_group="普通用户",
        action="导出",
        resource="项目资料",
        relation="受权限规则约束",
        expectation="不应允许",
        surface_result="页面返回拒绝",
        actual_result="归档已经生成",
        conclusion="发现权限问题",
        explanation="已发布事实确认越权后果。",
        severity="high",
        evidence_refs=(EVIDENCE_ID,),
        verdict="VULNERABLE",
        diagnosis=_report_diagnosis(),
    )
    presentation = ReportPresentation(
        run_id=RUN_ID,
        project_id=PROJECT_ID,
        project_name="报告测试项目",
        run_lifecycle="COMPLETED",
        verdict="BLOCK",
        policy_epoch=4,
        policy_fingerprint="e" * 64,
        headline="发现权限问题",
        scope_statement="本次确认权限断裂。",
        checked_count=1,
        safe_count=0,
        problem_count=1,
        inconclusive_count=0,
        uncovered_count=0,
        issues=(issue,),
    )
    base = _base(verdict="BLOCK", presentation=presentation)
    tampered = base.model_dump(mode="json")
    tampered["presentation"]["issues"][0]["diagnosis"]["precision"] = "RANGE"
    with pytest.raises(ValueError, match="canonical hash"):
        parse_report_document(tampered)

    gate_input = gate_semantic_input_sha256(
        base.report_id,
        base.canonical_sha256,
        GATE_ID,
        "c" * 64,
    )
    gate = GateRunReport.create(
        report_type="GATE",
        report_id=report_id_for("GATE", gate_input),
        run_id=RUN_ID,
        project_id=PROJECT_ID,
        base_report_id=base.report_id,
        base_report_sha256=base.canonical_sha256,
        gate_result_id=GATE_ID,
        semantic_input_sha256=gate_input,
        run=base.run,
        runtime=base.runtime,
        presentation=base.presentation,
        artifact_summary=base.artifact_summary,
        versions=base.versions,
        limitations=base.limitations,
        gate=ReportGate(
            gate_result_id=GATE_ID,
            baseline_id="baseline_" + "c" * 32,
            run_id=RUN_ID,
            policy_version="gate-v1",
            input_hash="c" * 64,
            decision="PASS",
            reasons=(),
            evaluated_at_us=3,
        ),
    )
    assert gate.presentation == base.presentation
    assert gate.runtime.verdict == "BLOCK"
    assert gate.presentation.verdict == "BLOCK"
    assert gate.gate.decision == "PASS"


def test_report_store_detects_projection_tamper_and_same_id_conflict(tmp_path: Path) -> None:
    base = _base()
    store = ReportStore(tmp_path / "var")
    store.publish(base)
    report_dir = tmp_path / "var" / "data" / "reports" / "runs" / RUN_ID / base.report_id
    original = (report_dir / "report.html").read_bytes()
    (report_dir / "report.html").write_bytes(original + b"tamper")
    with pytest.raises(JiejianError) as captured:
        store.read(RUN_ID, base.report_id)
    assert captured.value.code == ErrorCode.REPORT_INTEGRITY.value
    (report_dir / "report.html").write_bytes(original)
    with pytest.raises(JiejianError) as conflict:
        store.publish(base.model_copy(update={"limitations": ("CHANGED",)}))
    assert conflict.value.code == ErrorCode.REPORT_PUBLISH_FAILED.value


def test_report_store_atomic_failure_leaves_no_partial_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = _base()
    store = ReportStore(tmp_path / "var")

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("injected publish failure")

    monkeypatch.setattr(report_store_module.os, "replace", fail_replace)
    with pytest.raises(JiejianError) as captured:
        store.publish(base)
    assert captured.value.code == ErrorCode.REPORT_PUBLISH_FAILED.value
    run_dir = tmp_path / "var" / "data" / "reports" / "runs" / RUN_ID
    assert not (run_dir / base.report_id).exists()
    assert not list(run_dir.glob(".*.tmp-*"))


def test_not_requested_is_neutral_and_inconclusive_is_explicit() -> None:
    base = _base()
    assert "NO_ARTIFACT_RESULT" not in base.limitations
    assert b"NO_ARTIFACT_RESULT" not in render_junit(base)
    assert json.loads(render_sarif(base))["runs"][0]["invocations"][0]["executionSuccessful"] is True
    summary = ArtifactSummary.create(ArtifactSummaryStatus.INCONCLUSIVE, reason_codes=("ARTIFACT_RESULT_NOT_PUBLISHED",))
    assert summary.status is ArtifactSummaryStatus.INCONCLUSIVE


def test_artifact_summary_covers_not_requested_complete_inconclusive_and_tamper(
    tmp_path: Path,
) -> None:
    not_requested = ReportBuilder(tmp_path / "not-requested", None, None, None)
    assert not_requested._artifact_summary(RUN_ID, PROJECT_ID).status is ArtifactSummaryStatus.NOT_REQUESTED

    pending_var = tmp_path / "pending"
    _write_artifact_request(pending_var)
    pending = ReportBuilder(pending_var, None, None, None)._artifact_summary(
        RUN_ID,
        PROJECT_ID,
    )
    assert pending.status is ArtifactSummaryStatus.INCONCLUSIVE
    assert pending.reason_codes == ("ARTIFACT_RESULT_NOT_PUBLISHED",)

    result = ArtifactScanResult(
        project_id=PROJECT_ID,
        artifact_id="build-1",
        run_id=RUN_ID,
        status=ArtifactScanStatus.COMPLETE,
        verdict=ArtifactVerdict.SAFE,
        manifest_sha256="d" * 64,
        scanned_file_count=1,
        scanned_byte_count=1,
    )
    complete_var = tmp_path / "complete"
    complete_job = _write_artifact_request(complete_var, result=result)
    complete = ReportBuilder(complete_var, None, None, None)._artifact_summary(
        RUN_ID,
        PROJECT_ID,
    )
    assert complete.status is ArtifactSummaryStatus.COMPLETE
    assert [item.artifact_id for item in complete.results] == ["build-1"]

    result_path = complete_job / "published" / "artifact-result.json"
    result_path.write_bytes(result_path.read_bytes() + b"tamper")
    with pytest.raises(JiejianError) as captured:
        ReportBuilder(complete_var, None, None, None)._artifact_summary(
            RUN_ID,
            PROJECT_ID,
        )
    assert captured.value.code == ErrorCode.REPORT_INTEGRITY.value
