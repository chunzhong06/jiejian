# 所属业务域的共享测试构造器；不导入测试用例。
from __future__ import annotations
from product.protocols.report import ArtifactSummary, ArtifactSummaryStatus, BaseRunReport, ReportPresentation, ReportRun, ReportRuntime, ReportVersions, base_semantic_input_sha256, report_id_for

RUN_ID = "run_" + "a" * 32

PROJECT_ID = "report-project"

GATE_ID = "gate_" + "b" * 32

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
