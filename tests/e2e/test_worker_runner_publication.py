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
from tests.fixtures.runner import (
    register_test_generated_profile,
    seed_project_from_generated_profile,
    write_web_test_profile,
)
pytestmark = [pytest.mark.database, pytest.mark.process, pytest.mark.slow]

def _write_profile(tmp_path: Path, *, port: int | None = None) -> Path:
    path, _ = write_web_test_profile(tmp_path, port=port or 8765)
    return path

def _register_project(app, profile_path: Path) -> dict[str, object]:
    return seed_project_from_generated_profile(app, profile_path)


def _register_understanding(app, profile_path: Path) -> None:
    """补齐 Run 冻结权限策略所需的已确认应用理解事实。"""

    profile = parse_web_execution_profile(profile_path.read_bytes())
    now_us = time.time_ns() // 1_000
    with app.state.context.uow_factory() as work:
        work.application_understanding.add(
            ApplicationUnderstanding(
                project_id=profile.project_id,
                source_root=str(profile_path.parent.resolve()),
                confirmed_endpoint=profile.target.scope.base_url,
                endpoint_source_fingerprint="a" * 64,
                endpoint_confirmed_at_us=now_us,
                endpoint_last_checked_at_us=now_us,
                endpoint_reachable=True,
                role_candidates=(
                    RoleCandidate(
                        candidate_id=candidate_id("role", "member"),
                        canonical_key="member",
                        display_name="普通成员",
                        confidence=CandidateConfidence.HIGH,
                        decision=CandidateDecision.CONFIRMED,
                        origin=CandidateOrigin.MANUAL,
                    ),
                ),
                action_candidates=(
                    ActionCandidate(
                        candidate_id=candidate_id("action", "modify"),
                        canonical_key="modify",
                        display_name="修改资源",
                        confidence=CandidateConfidence.HIGH,
                        decision=CandidateDecision.CONFIRMED,
                        origin=CandidateOrigin.MANUAL,
                    ),
                ),
                revision=1,
                created_at_us=now_us,
                updated_at_us=now_us,
            )
        )
        work.commit()


def _activate_contract(app, project_id: str, profile_path: Path) -> PermissionContract:
    contract = PermissionContract.model_validate_json(profile_path.with_name("contract.json").read_text(encoding="utf-8"), strict=True)
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
    project = _register_project(app, profile_path)
    _register_understanding(app, profile_path)
    contract = _activate_contract(app, str(project["project_id"]), profile_path)
    profile = register_test_generated_profile(app, profile_path)
    return project, contract, profile.model_dump(mode="json")

@pytest.mark.essential
def test_api_worker_runner_publication_matches_cli_report(
    web_test_target_factory,
    monkeypatch,
    tmp_path: Path,
) -> None:
    sample = web_test_target_factory()
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
        assert submitted.status_code == 202, submitted.text
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
        presentation_response = client.get(f"/api/runs/{run_id}/presentation")
        assert presentation_response.status_code == 200, presentation_response.text
        api_presentation = presentation_response.json()["data"]
        runner_process_ids = tuple(sample.server.runner_process_ids)
    assert runner_process_ids and set(runner_process_ids) != {os.getpid()}
    cli_report = CliRunner().invoke(
        cli_app,
        [
            "--var-dir",
            str(var_dir),
            "--json",
            "result",
            "report",
            "--run",
            run_id,
            "--report",
            base_report_id,
        ],
        env=sample.environ,
    )
    assert cli_report.exit_code == 0, cli_report.output
    cli_envelope = json.loads(cli_report.stdout)
    assert cli_envelope["kind"] == "report"
    cli_payload = cli_envelope["data"]
    assert cli_payload == api_report
    cli_result = CliRunner().invoke(
        cli_app,
        ["--var-dir", str(var_dir), "--json", "result", "show", "--run", run_id],
        env=sample.environ,
    )
    assert cli_result.exit_code == 0, cli_result.output
    result_envelope = json.loads(cli_result.stdout)
    assert result_envelope["kind"] == "result"
    assert result_envelope["data"] == api_presentation
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
