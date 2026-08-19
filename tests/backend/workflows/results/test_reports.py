from __future__ import annotations

import hashlib
import json
import shutil
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from product.backend.api.routers.results import build_results_router
from product.backend.cli.app import app as cli_app
from product.backend.core.lifecycle import CaseVerdict, JobState, ProjectStatus, RunLifecycle, RunVerdict
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import CleanupResult, CleanupStatus, RunnerResultType, RunnerResult
from product.protocols.artifacts import stable_artifact_ids
from product.protocols.report import canonical_sha256
from product.backend.infra.artifacts.report_reader import ArtifactResultReader
from product.backend.infra.artifacts.report_store import ReportStore
from product.backend.workflows.results.reporting import ReportBuilder
from product.backend.infra.storage import (
    GateResultRecord,
    ProjectRecord,
    RegressionBaselineRecord,
    RunRecord,
    StorageUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
    upgrade_database,
)
from product.backend.core.verification.findings import FindingIdentity
from tests.fixtures.runner import evidence


PROJECT_ID = "report-project"
RUN_ID = "run_" + "a" * 32
GATE_ID = "gate_" + "2" * 32
BASELINE_ID = "baseline_" + "3" * 32
EVIDENCE_ID = "ev_" + "4" * 20
FINDING_ID = "finding_" + "5" * 32
OCCURRENCE_ID = "occ_" + "6" * 32
ARTIFACT_ID = "build-1"


def _runtime_result() -> RunnerResult:
    return RunnerResult(
        schema_version="2",
        run_id=RUN_ID,
        job_id="job_" + "7" * 32,
        attempt=1,
        lease_owner="report-test",
        fencing_token=1,
        finished_at_us=20,
        result_type=RunnerResultType.SUCCESS,
        run_lifecycle=RunLifecycle.COMPLETED,
        job_state=JobState.SUCCEEDED,
        verdict=RunVerdict.BLOCK,
        reason_codes=(),
        plan_fingerprint="a" * 64,
        coverage_record_count=0,
        coverage_gap_count=0,
        evidence=(evidence(verdict=CaseVerdict.VULNERABLE),),
        cleanup=CleanupResult(schema_version="2", status=CleanupStatus.SUCCEEDED, reason_codes=()),
        error=None,
        artifacts=(),
    )


def _stored_gate(tmp_path: Path):
    database = tmp_path / "state.db"
    upgrade_database(database)
    engine = create_sqlite_engine(database)
    factory = create_session_factory(engine)
    with StorageUnitOfWork(factory) as work:
        work.projects.add(ProjectRecord(project_id=PROJECT_ID, name="Report", status=ProjectStatus.READY, created_at_us=1, updated_at_us=1))
        work.runs.add(RunRecord(run_id=RUN_ID, project_id=PROJECT_ID, contract_id="contract", contract_version=1, engine_version="engine-v1", lifecycle=RunLifecycle.COMPLETED, verdict=RunVerdict.BLOCK, created_at_us=1, updated_at_us=20, finished_at_us=20))
        work.gating.add_baseline(RegressionBaselineRecord(
            baseline_id=BASELINE_ID,
            project_id=PROJECT_ID,
            accepted_run_id=RUN_ID,
            finding_refs_json="[]",
            coverage_ids_json="[]",
            coverage_digest=canonical_sha256(()),
            request_snapshot_sha256="a" * 64,
            engine_version="engine-v1",
            protocol_versions_json='["runner-result-2"]',
            actor="operator",
            reason="report test",
            accepted_at_us=10,
        ))
        work.gating.add_gate_result(GateResultRecord(
            gate_result_id=GATE_ID,
            baseline_id=BASELINE_ID,
            project_id=PROJECT_ID,
            run_id=RUN_ID,
            policy_version="gate-v1",
            input_hash="b" * 64,
            reasons_json='[{"code":"NEW_VULNERABLE_FINDING","subject":"finding_test"}]',
            decision="BLOCK",
            evaluated_at_us=30,
        ))
        work.commit()
    return engine, factory


def _write_artifact_result(var_dir: Path) -> None:
    job_dir = var_dir / "artifact-checks" / "jobs" / "artifact-job-1"
    published = job_dir / "published"
    published.mkdir(parents=True)
    request = {
        "schema_version": "1",
        "project_id": PROJECT_ID,
        "artifact_id": ARTIFACT_ID,
        "run_id": RUN_ID,
        "artifact_root": str(var_dir / "projects" / PROJECT_ID / "runs" / RUN_ID / "artifacts"),
        "manifest_path": str(var_dir / "projects" / PROJECT_ID / "runs" / RUN_ID / "publication-manifest.json"),
        "ruleset_version": "artifact-local-2026.08.18",
        "budget": {"schema_version": "1", "max_parallel_files": 1, "max_files": 4096, "max_file_bytes": 16777216, "max_total_bytes": 536870912, "max_results": 4096, "max_duration_us": 30000000, "max_compressed_layers": 0},
    }
    job_dir.joinpath("request.json").write_text(json.dumps(request, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    finding_id, evidence_id = stable_artifact_ids(ARTIFACT_ID, "SECRET_CANDIDATE", "app.js", "d" * 64)
    result = {
        "schema_version": "1",
        "project_id": PROJECT_ID,
        "artifact_id": ARTIFACT_ID,
        "run_id": RUN_ID,
        "source_type": "ARTIFACT",
        "ruleset_version": "artifact-local-2026.08.18",
        "status": "COMPLETE",
        "verdict": "VULNERABLE",
        "error_code": None,
        "manifest_sha256": "c" * 64,
        "scanned_file_count": 1,
        "scanned_byte_count": 10,
        "findings": [{
            "schema_version": "1", "finding_id": finding_id, "source_type": "ARTIFACT", "artifact_id": ARTIFACT_ID,
            "rule_id": "SECRET_CANDIDATE", "category": "SECRET_CANDIDATE", "severity": "critical", "path": "app.js",
            "evidence_id": evidence_id, "message": "检测到秘密候选",
        }],
        "evidence": [{
            "schema_version": "1", "evidence_id": evidence_id, "source_type": "ARTIFACT", "artifact_id": ARTIFACT_ID,
            "manifest_sha256": "c" * 64, "rule_id": "SECRET_CANDIDATE", "path": "app.js", "fingerprint": "d" * 64,
            "line": 1, "reason_code": "SECRET_CANDIDATE",
        }],
    }
    result_raw = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    published.joinpath("artifact-result.json").write_bytes(result_raw)
    manifest = {
        "schema_version": "1",
        "artifact_id": ARTIFACT_ID,
        "project_id": PROJECT_ID,
        "result_sha256": hashlib.sha256(result_raw).hexdigest(),
        "input_manifest_sha256": "c" * 64,
        "files": [{"schema_version": "1", "path": "artifact-result.json", "byte_count": len(result_raw), "sha256": hashlib.sha256(result_raw).hexdigest()}],
    }
    published.joinpath("artifact-check-manifest.json").write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def _service(tmp_path: Path):
    engine, factory = _stored_gate(tmp_path)
    var_dir = tmp_path / "var"
    _write_artifact_result(var_dir)
    run = RunRecord(run_id=RUN_ID, project_id=PROJECT_ID, contract_id="contract", contract_version=1, engine_version="engine-v1", lifecycle=RunLifecycle.COMPLETED, verdict=RunVerdict.BLOCK, created_at_us=1, updated_at_us=20, finished_at_us=20)
    view = SimpleNamespace(
        run=run,
        job=SimpleNamespace(job_id="job_" + "7" * 32),
        publication=SimpleNamespace(result=_runtime_result(), manifest=SimpleNamespace(result_sha256="e" * 64)),
        evidence=(SimpleNamespace(evidence_id=EVIDENCE_ID),),
    )
    identity = FindingIdentity(
        project_id=PROJECT_ID,
        permission_intent=("rule:report",),
        subject_class=("role:user",),
        action="read",
        resource_class=("type:item",),
        resource_relation=("kind:direct",),
        problem_category="report-test",
    )
    findings = [{
        "schema_version": "2",
        "finding": {"schema_version": "1", "finding_id": FINDING_ID, "project_id": PROJECT_ID, "identity": identity.model_dump(mode="json"), "first_seen_at_us": 1, "last_seen_at_us": 20},
        "occurrence": {"schema_version": "1", "occurrence_id": OCCURRENCE_ID, "finding_id": FINDING_ID, "project_id": PROJECT_ID, "run_id": RUN_ID, "status": "APPEARED", "verdict": "VULNERABLE", "severity": "high", "evidence_refs": [EVIDENCE_ID], "object_context": {}, "coverage_context": {}, "created_at_us": 20},
    }]

    class Results:
        def read(self, run_id):
            assert run_id == RUN_ID
            return view

    class Findings:
        def stored_findings_for_run(self, run_id):
            assert run_id == RUN_ID
            return findings

    class Gating:
        def get_gate_result(self, gate_result_id):
            assert gate_result_id == GATE_ID
            with StorageUnitOfWork(factory) as work:
                row = work.gating.get_gate_result(gate_result_id)
            return {"schema_version": "1", "gate_result_id": row.gate_result_id, "baseline_id": row.baseline_id, "run_id": row.run_id, "policy_version": row.policy_version, "input_hash": row.input_hash, "reasons": json.loads(row.reasons_json), "decision": row.decision, "evaluated_at_us": row.evaluated_at_us}

        def get_baseline(self, baseline_id):
            assert baseline_id == BASELINE_ID
            return {"schema_version": "1", "baseline_id": BASELINE_ID, "project_id": PROJECT_ID}

    return ReportBuilder(var_dir, Results(), Findings(), Gating()), engine, var_dir


def test_report_json_is_deterministic_and_four_formats_share_ids_gate_and_evidence(tmp_path: Path) -> None:
    service, engine, var_dir = _service(tmp_path)
    try:
        first = service.generate(RUN_ID, GATE_ID)
        second = service.generate(RUN_ID, GATE_ID)
        assert first == second
        assert first["gate_result_id"] == GATE_ID
        assert first["runtime"]["evidence_refs"][0]["source_type"] == "RUNTIME"
        assert first["artifacts"][0]["evidence_refs"][0]["source_type"] == "ARTIFACT"
        report_id = first["report_id"]
        assert service.read(RUN_ID, report_id) == first
        assert b"<script>" not in service.read_format(RUN_ID, report_id, "html")
        sarif = json.loads(service.read_format(RUN_ID, report_id, "sarif"))
        assert sarif["runs"][0]["results"][0]["properties"]["gate_result_id"] == GATE_ID
        junit = service.read_format(RUN_ID, report_id, "junit").decode("utf-8")
        assert EVIDENCE_ID in junit
        assert "NO_ARTIFACT_RESULT" not in junit
        sarif_payload = json.loads(service.read_format(RUN_ID, report_id, "sarif"))
        assert sarif_payload["runs"][0]["invocations"][0]["executionSuccessful"] is True
        assert (var_dir / "reports" / "runs" / RUN_ID / report_id / "report.json").is_file()
    finally:
        engine.dispose()


def test_tampered_projection_is_rejected_without_overwriting_report(tmp_path: Path) -> None:
    service, engine, var_dir = _service(tmp_path)
    try:
        report = service.generate(RUN_ID, GATE_ID)
        report_dir = var_dir / "reports" / "runs" / RUN_ID / report["report_id"]
        original = (report_dir / "report.html").read_bytes()
        (report_dir / "report.html").write_bytes(original + b"tampered")
        with pytest.raises(JiejianError) as captured:
            service.read(RUN_ID, report["report_id"])
        assert captured.value.code == ErrorCode.REPORT_INTEGRITY.value
        (report_dir / "report.html").write_bytes(original)
        assert service.read(RUN_ID, report["report_id"])["canonical_sha256"] == report["canonical_sha256"]
    finally:
        engine.dispose()


def test_artifact_manifest_file_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    service, engine, var_dir = _service(tmp_path)
    try:
        manifest_path = var_dir / "artifact-checks" / "jobs" / "artifact-job-1" / "published" / "artifact-check-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"][0]["sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        with pytest.raises(JiejianError) as captured:
            service.generate(RUN_ID, GATE_ID)
        assert captured.value.code == ErrorCode.REPORT_INTEGRITY.value
    finally:
        engine.dispose()


def test_inconclusive_and_missing_artifact_facts_are_visible_in_projections(tmp_path: Path) -> None:
    service, engine, var_dir = _service(tmp_path)
    try:
        shutil.rmtree(var_dir / "artifact-checks")
        report = service.generate(RUN_ID, GATE_ID)
        assert report["limitations"] == ["NO_ARTIFACT_RESULT"]
        sarif = json.loads(service.read_format(RUN_ID, report["report_id"], "sarif"))
        invocation = sarif["runs"][0]["invocations"][0]
        assert invocation["executionSuccessful"] is False
        assert invocation["toolExecutionNotifications"][0]["message"]["text"] == "NO_ARTIFACT_RESULT"
        junit = service.read_format(RUN_ID, report["report_id"], "junit").decode("utf-8")
        assert 'classname="LIMITATION"' in junit
        assert 'name="NO_ARTIFACT_RESULT"' in junit
    finally:
        engine.dispose()


def test_reparse_attribute_is_rejected_for_report_and_artifact_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_metadata = SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
    monkeypatch.setattr("product.backend.infra.artifacts.report_store.os.lstat", lambda _path: fake_metadata)
    with pytest.raises(JiejianError):
        ReportStore(tmp_path)._regular_directory(tmp_path)
    monkeypatch.setattr("product.backend.infra.artifacts.report_reader.os.lstat", lambda _path: fake_metadata)
    with pytest.raises(JiejianError):
        ArtifactResultReader(tmp_path)._regular_directory(tmp_path)


def test_current_api_and_cli_read_the_same_explicit_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service, engine, var_dir = _service(tmp_path)
    try:
        generated = service.generate(RUN_ID, GATE_ID)
        fake_context = SimpleNamespace(reports=service, close=lambda: None)
        api = FastAPI()
        api.include_router(build_results_router(fake_context, SimpleNamespace()))
        with TestClient(api) as client:
            assert client.post(f"/api/runs/{RUN_ID}/reports", json={"gate_result_id": GATE_ID}).status_code == 405
            response = client.get(f"/api/runs/{RUN_ID}/reports/{generated['report_id']}")
        assert response.status_code == 200
        assert response.json()["data"]["gate_result_id"] == GATE_ID
        with TestClient(api) as client:
            download = client.get(f"/api/runs/{RUN_ID}/reports/{generated['report_id']}/formats/sarif")
        assert download.status_code == 200
        assert download.headers["content-type"].startswith("application/sarif+json")
        assert download.headers["content-disposition"] == 'attachment; filename="report.sarif.json"'

        from contextlib import contextmanager
        @contextmanager
        def scope(*_args, **_kwargs):
            yield fake_context
        monkeypatch.setattr("product.backend.cli.commands.results.application_scope", scope)
        cli = CliRunner().invoke(cli_app, ["--var-dir", str(var_dir), "report", RUN_ID, "--report-id", generated["report_id"]])
        assert cli.exit_code == 0, cli.output
        assert json.loads(cli.stdout)["gate_result_id"] == GATE_ID
        cli_projection = CliRunner().invoke(cli_app, ["--var-dir", str(var_dir), "report", RUN_ID, "--report-id", generated["report_id"], "--format", "html"])
        assert cli_projection.exit_code == 0, cli_projection.output
        assert cli_projection.stdout_bytes == service.read_format(RUN_ID, generated["report_id"], "html")
    finally:
        engine.dispose()
