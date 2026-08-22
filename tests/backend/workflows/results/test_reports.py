from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.reporting import render_junit, render_sarif
from product.backend.infra.artifacts.report_store import ReportStore
from product.backend.infra.artifacts import report_store as report_store_module
from product.backend.workflows.results.reporting import ReportBuilder
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
    ReportPackageManifest,
    ReportRun,
    ReportRuntime,
    ReportVersions,
    base_semantic_input_sha256,
    gate_semantic_input_sha256,
    parse_report_document,
    report_json_schema,
    report_id_for,
)


RUN_ID = "run_" + "a" * 32
PROJECT_ID = "report-project"
GATE_ID = "gate_" + "b" * 32


def _versions() -> ReportVersions:
    return ReportVersions(
        contract_id="contract",
        contract_version=1,
        engine_version="engine-v1",
        runner_schema_version="3",
        evidence_schema_version="3",
        observer_schema_version="2",
        artifact_schema_version="1",
    )


def _base(status: ArtifactSummaryStatus = ArtifactSummaryStatus.NOT_REQUESTED) -> BaseRunReport:
    versions = _versions()
    summary = ArtifactSummary.create(status)
    run = ReportRun(run_id=RUN_ID, project_id=PROJECT_ID, lifecycle="COMPLETED", created_at_us=1, finished_at_us=2)
    runtime = ReportRuntime(lifecycle="COMPLETED", evidence_refs=(), findings=(), observer_statuses=())
    semantic = base_semantic_input_sha256(RUN_ID, "a" * 64, "b" * 64, summary.snapshot_sha256, versions)
    return BaseRunReport.create(
        report_type="BASE",
        report_id=report_id_for("BASE", semantic),
        run_id=RUN_ID,
        project_id=PROJECT_ID,
        semantic_input_sha256=semantic,
        run=run,
        runtime=runtime,
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


def test_report_v3_discriminator_and_versions_fail_closed() -> None:
    base = _base()
    encoded = base.model_dump(mode="json")
    assert parse_report_document(encoded).report_type == "BASE"
    for invalid in (
        {**encoded, "schema_version": "2"},
        {key: value for key, value in encoded.items() if key != "schema_version"},
        {**encoded, "unexpected": True},
        {**encoded, "gate_result_id": GATE_ID},
    ):
        with pytest.raises(ValueError):
            parse_report_document(invalid)
    with pytest.raises(ValueError):
        ReportVersions(
            contract_id="contract", contract_version=1, engine_version="engine-v1",
            runner_schema_version="2", evidence_schema_version="3", observer_schema_version="2", artifact_schema_version="1",
        )


def test_report_v3_checked_in_schema_matches_runtime_union() -> None:
    schema_path = Path("product/protocols/schemas/reports/report.schema.json")
    assert json.loads(schema_path.read_text(encoding="utf-8")) == report_json_schema()
    manifest_path = Path(
        "product/protocols/schemas/reports/report-package-manifest.schema.json"
    )
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == (
        ReportPackageManifest.model_json_schema()
    )


def test_base_and_gate_ids_and_bytes_are_deterministic(tmp_path: Path) -> None:
    base = _base()
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
    assert json.loads(store.read_format(RUN_ID, base.report_id, "sarif"))["runs"][0]["invocations"][0]["executionSuccessful"] is True


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
