# 验证 API 到 Worker、Runner、publication、Report 与 CLI 的完整闭环。

from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from fastapi.testclient import TestClient as RawTestClient
import pytest
from typer.testing import CliRunner
from product.backend.infra.runtime.serve_lock import ServeLock
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.cli.app import app as cli_app
from product.backend.core.contracts.models import ContractStatus
from product.backend.core.application_understanding import ActionCandidate, ApplicationUnderstanding, CandidateConfidence, CandidateDecision, CandidateOrigin, RoleCandidate, candidate_id
from product.backend.core.lifecycle import ProjectStatus
from product.backend.core.test_identity import TestIdentityAuthMethod, TestIdentityCookie
from product.backend.core.errors import JiejianError
from product.backend.core.verification.permissions import PermissionContract
from product.backend.infra.runtime.jobs.requests import ExecutionRequestStore
from product.backend.infra.runtime.jobs.models import (
    ClaimJob,
    FatalFailure,
    FatalFailureCode,
)
from product.backend.infra.recording.request_store import RecordingRequestStore
from product.backend.infra.secrets import credential_ref
from product.backend.infra.storage import ProjectRecord
from product.backend.workflows.test_identities import PreparedLoginState
from product.backend.cli.commands.system import ServeReadinessStatus, _wait_for_ready
from product.protocols import (
    CleanupIssueCode,
    RunnerFailurePhase,
    canonical_web_execution_profile_json_bytes,
    parse_web_execution_profile,
)
from tests.fixtures.runtime_environment import runtime_identity_environment
from tests.fixtures.control_plane import (
    TEST_CONTROL_ORIGIN,
    TestClient,
    create_app,
)
pytestmark = [pytest.mark.database, pytest.mark.process, pytest.mark.slow]
PROFILE_SOURCE = Path("samples/web/fixed/profile.json").resolve()
CONTRACT_SOURCE = Path("samples/web/fixed/contract.json").resolve()

def _write_profile(tmp_path: Path, *, port: int | None = None) -> Path:
    profile = parse_web_execution_profile(PROFILE_SOURCE.read_bytes())
    if port is not None:
        scope = profile.target.scope.model_copy(
            update={
                "base_url": f"http://127.0.0.1:{port}",
                "allowed_origins": (f"http://127.0.0.1:{port}",),
                "allowed_ports": (port,),
            }
        )
        profile = profile.model_copy(update={"target": profile.target.model_copy(update={"scope": scope})})
    path = tmp_path / "profile.json"
    path.write_bytes(canonical_web_execution_profile_json_bytes(profile))
    return path

def _register_project(client: TestClient, profile_path: Path) -> dict[str, object]:
    response = client.post(
        "/api/projects",
        json={"schema_version": "1", "profile_path": str(profile_path)},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]

def _activate_contract(app, project_id: str) -> PermissionContract:
    contract = PermissionContract.model_validate_json(CONTRACT_SOURCE.read_text(encoding="utf-8"), strict=True)
    draft = app.state.context.contracts.create_draft(
        project_id,
        contract.contract_id,
        snapshot=contract,
        actor="test",
    )
    review = app.state.context.contracts.submit_review(
        project_id, draft.contract_id, draft.version, actor="reviewer"
    )
    active = app.state.context.contracts.activate_review(
        project_id, review.contract_id, review.version, actor="approver"
    )
    return active.snapshot

def _register_active_profile(app, client: TestClient, profile_path: Path) -> tuple[dict[str, object], PermissionContract, dict[str, object]]:
    project = _register_project(client, profile_path)
    contract = _activate_contract(app, str(project["project_id"]))
    response = client.post(
        "/api/execution-profiles",
        json={"schema_version": "1", "profile_path": str(profile_path)},
    )
    assert response.status_code == 201, response.text
    return project, contract, response.json()["data"]

@pytest.mark.essential
def test_api_worker_runner_publication_matches_cli_report(
    sample_server_factory,
    monkeypatch,
    tmp_path: Path,
) -> None:
    sample = sample_server_factory("fixed")
    profile_path = _write_profile(tmp_path, port=sample.port)
    for key, value in sample.environ.items():
        monkeypatch.setenv(key, value)
    var_dir = tmp_path / "api-real"
    for key, value in runtime_identity_environment(var_dir).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("PYTHONNOUSERSITE", "1")
    app = create_app(var_dir, start_worker=True)
    with TestClient(app) as client:
        project, _, profile = _register_active_profile(app, client, profile_path)
        submitted = client.post(
            f"/api/projects/{project['project_id']}/runs",
            json={"schema_version": "1", "profile_id": profile["profile_id"], "idempotency_key": "api-real-closure"},
        )
        assert submitted.status_code == 202
        run_id = submitted.json()["data"]["run"]["run_id"]
        deadline = time.monotonic() + 45
        detail = None
        while time.monotonic() < deadline:
            response = client.get(f"/api/runs/{run_id}")
            if response.status_code == 200:
                detail = response.json()["data"]
                finalization = detail.get("finalization", {})
                if (
                    detail["lifecycle"] in {"FAILED", "CANCELLED"}
                    or finalization.get("base_report_state") == "COMPLETE"
                ):
                    break
            time.sleep(0.1)
        assert detail is not None and detail["lifecycle"] == "COMPLETED", detail
        assert detail["result_integrity"] == "VERIFIED"
        report = client.get(f"/api/runs/{run_id}").json()["data"]
        findings_response = client.get(f"/api/runs/{run_id}/findings")
        assert findings_response.status_code == 200, findings_response.text
        findings = findings_response.json()["data"]
        assert findings == []
        assert report["finding_count"] == 0
        assert report["finding_count"] == len(findings)
        assert report["target_scope"]["base_url"] == f"http://127.0.0.1:{sample.port}"
        assert report["target_scope"]["max_requests"] == 64
        assert report["budget"]["max_requests"] == report["target_scope"]["max_requests"]
        assert report["observer_health"]["resource_state"]["configured"] is True
        assert report["case_progress"]["status"] == "PUBLISHED"
        assert report["case_progress"]["completed"] == report["case_progress"]["total"]
        assert report["case_progress"]["total"] > 0
        assert report["safety_context"] is None
        assert report["finalization"]["findings_state"] == "COMPLETE"
        assert report["finalization"]["base_report_state"] == "COMPLETE"
        base_report_id = report["finalization"]["base_report_id"]
        assert base_report_id
        evidence = client.get(f"/api/runs/{run_id}/evidence").json()["data"]
        assert evidence
        evidence_detail = client.get(f"/api/runs/{run_id}/evidence/{evidence[0]['evidence_id']}")
        assert evidence_detail.status_code == 200
        evidence_payload = evidence_detail.json()["data"]
        assert evidence_payload.get("evidence_id") == evidence[0]["evidence_id"], evidence_detail.text
        assert evidence_payload.get("execution_fact") is not None
        assert evidence_payload.get("observation_facts")
        available = client.get(f"/api/runs/{run_id}/reports")
        assert available.status_code == 200, available.text
        listed_reports = available.json()["data"]
        assert len(listed_reports) == 1
        assert "schema_version" not in listed_reports[0]
        assert listed_reports[0]["report_id"] == base_report_id
        assert listed_reports[0]["run_id"] == run_id
        assert listed_reports[0]["report_type"] == "BASE"
        api_report_response = client.get(f"/api/runs/{run_id}/reports/{base_report_id}")
        assert api_report_response.status_code == 200, api_report_response.text
        api_report = api_report_response.json()["data"]
        assert api_report["report_type"] == "BASE"
        assert api_report["artifact_summary"]["status"] == "NOT_REQUESTED"
        for output_format in ("json", "html", "sarif", "junit"):
            projection = client.get(
                f"/api/runs/{run_id}/reports/{base_report_id}/formats/{output_format}"
            )
            assert projection.status_code == 200, projection.text
        baseline_response = client.post(
            f"/api/projects/{project['project_id']}/baselines",
            json={
                "schema_version": "1",
                "accepted_run_id": run_id,
                "actor": "test",
                "reason": "current publication baseline",
            },
        )
        assert baseline_response.status_code == 200, baseline_response.text
        baseline_id = baseline_response.json()["data"]["baseline_id"]
        gate_response = client.post(
            f"/api/baselines/{baseline_id}/runs/{run_id}/gate",
            json={"schema_version": "1", "minimum_severity": "low"},
        )
        assert gate_response.status_code == 200, gate_response.text
        gate_result_id = gate_response.json()["data"]["gate_result_id"]
        gate_report_response = client.post(
            f"/api/runs/{run_id}/reports/gate",
            json={"schema_version": "1", "gate_result_id": gate_result_id},
        )
        assert gate_report_response.status_code == 200, gate_report_response.text
        gate_report = gate_report_response.json()["data"]
        assert gate_report["report_type"] == "GATE"
        assert gate_report["base_report_id"] == base_report_id
        assert gate_report["base_report_sha256"] == api_report["canonical_sha256"]
        for copied_field in (
            "run",
            "runtime",
            "artifact_summary",
            "versions",
            "limitations",
        ):
            assert gate_report[copied_field] == api_report[copied_field]
        assert len(client.get(f"/api/runs/{run_id}/reports").json()["data"]) == 2
        runner_process_ids = tuple(sample.server.runner_process_ids)
    assert runner_process_ids and set(runner_process_ids) != {os.getpid()}
    cli_report = CliRunner().invoke(
        cli_app,
        ["--var-dir", str(var_dir), "report", run_id, "--format", "json"],
        env=sample.environ,
    )
    assert cli_report.exit_code == 0, cli_report.output
    cli_payload = json.loads(cli_report.stdout)
    assert cli_payload["run_id"] == run_id
    assert cli_payload["report_id"] == base_report_id
    assert cli_payload == api_report
    cli_repair = CliRunner().invoke(
        cli_app,
        ["--var-dir", str(var_dir), "result-repair", run_id],
        env=sample.environ,
    )
    assert cli_repair.exit_code == 0, cli_repair.output
    assert json.loads(cli_repair.stdout)["base_report_state"] == "COMPLETE"
    assert tuple(sample.server.runner_process_ids) == runner_process_ids
    with TestClient(create_app(var_dir, start_worker=False)) as client:
        available = client.get(f"/api/runs/{run_id}/reports")
        assert available.status_code == 200
        api_report_response = client.get(f"/api/runs/{run_id}/reports/{base_report_id}")
        assert api_report_response.status_code == 200, api_report_response.text
        assert api_report_response.json()["data"] == cli_payload

    report_path = var_dir / "data" / "reports" / "runs" / run_id / base_report_id / "report.json"
    report_path.write_text('{"tampered":true}', encoding="utf-8")
    with TestClient(create_app(var_dir, start_worker=False)) as client:
        tampered = client.get(f"/api/runs/{run_id}/reports/{base_report_id}")
    assert tampered.status_code != 200
    assert tampered.json()["error"]["code"] in {"ARTIFACT_HASH_MISMATCH", "ARTIFACT_MANIFEST", "REPORT_INTEGRITY"}
