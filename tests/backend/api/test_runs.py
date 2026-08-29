# 验证 Run API 的幂等、取消、SSE 与受治理执行绑定接线。

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
from tests.fixtures.runner import write_web_test_profile

def _write_profile(tmp_path: Path, *, port: int | None = None) -> Path:
    path, _ = write_web_test_profile(tmp_path, port=port or 8765)
    return path

def _register_project(app, profile_path: Path) -> dict[str, object]:
    return app.state.context.projects.register(profile_path)[0].model_dump(mode="json")

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
    contract = _activate_contract(app, str(project["project_id"]), profile_path)
    profile = app.state.context.execution.register(profile_path)
    return project, contract, profile.model_dump(mode="json")

def _set_governed_binding(app, project_id: str, contract_id: str | None, version: int | None) -> None:
    record = app.state.context.projects.get(project_id)
    with app.state.context.uow_factory() as work:
        work.projects.replace(
            record.model_copy(
                update={
                    "governed_contract_id": contract_id,
                    "governed_contract_version": version,
                }
            )
        )
        work.commit()

def test_failed_worker_run_returns_copyable_user_diagnostic(
    web_test_target_factory,
    monkeypatch,
    tmp_path: Path,
) -> None:
    sample = web_test_target_factory()
    profile_path = _write_profile(tmp_path, port=sample.port)
    for key, value in sample.environ.items():
        monkeypatch.setenv(key, value)
    app = create_app(tmp_path / "failed-run", start_worker=False)

    with TestClient(app) as client:
        project, _, profile = _register_active_profile(app, client, profile_path)
        submitted = client.post(
            f"/api/projects/{project['project_id']}/runs",
            json={
                "schema_version": "1",
                "profile_id": profile["profile_id"],
                "idempotency_key": "failed-worker-diagnostic",
            },
        ).json()["data"]
        job_id = submitted["job"]["job_id"]
        now_us = time.time_ns() // 1_000
        claimed = app.state.context.job_attempts.claim(
            ClaimJob(
                job_id=job_id,
                lease_owner="diagnostic-worker",
                now_us=now_us,
                lease_duration_us=30_000_000,
            )
        )
        assert claimed is not None
        app.state.context.job_attempts.record_fatal_failure(
            FatalFailure(
                job_id=job_id,
                lease_owner="diagnostic-worker",
                fencing_token=claimed.job.fencing_token,
                now_us=now_us + 1,
                reason_code=FatalFailureCode.RUNNER_FATAL,
                error_code="PREPARE_RECOVERY_FAILED",
                phase=RunnerFailurePhase.PREPARE_RECOVERY,
                cause_code="TARGET_UNREACHABLE",
                cleanup_issue_codes=(
                    CleanupIssueCode.POST_CASE_RECOVERY_FAILED,
                ),
            )
        )
        detail = client.get(f"/api/runs/{submitted['run']['run_id']}")

    assert detail.status_code == 200
    error = detail.json()["data"]["execution_errors"][0]
    assert error["stage"] == "执行前恢复"
    assert error["code"] == "PREPARE_RECOVERY_FAILED"
    assert error["phase"] == "PREPARE_RECOVERY"
    assert error["cause_code"] == "TARGET_UNREACHABLE"
    assert error["cleanup_issues"] == ["POST_CASE_RECOVERY_FAILED"]
    assert error["diagnosis"]["headline"] == "检查前无法恢复测试现场"
    assert "恢复步骤和测试资源当前状态" in error["diagnosis"]["short_message"]
    assert error["diagnosis"]["route"] == "/flows"
    assert error["diagnosis"]["cleanup_warnings"] == [
        "业务检查结束后，测试现场没有完全恢复。"
    ]
    assert error["job_id"] == job_id
    assert job_id in error["copy_text"]
    assert error["log_path"].endswith(f"{job_id}.log")

def test_run_idempotency_cancel_and_sse_cursor(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("JIEJIAN_WEB_TEST_MEMBER_TOKEN", "member-test")
    monkeypatch.setenv("JIEJIAN_WEB_TEST_READER_TOKEN", "reader-test")
    monkeypatch.setenv("JIEJIAN_WEB_TEST_OBSERVER_TOKEN", "observer-test")
    app = create_app(tmp_path / "var", start_worker=False)
    profile_path = _write_profile(tmp_path)
    with TestClient(app) as client:
        project, _, profile = _register_active_profile(app, client, profile_path)
        first = client.post(
            f"/api/projects/{project['project_id']}/runs",
            json={"schema_version": "1", "profile_id": profile["profile_id"], "idempotency_key": "api-sse-test"},
        )
        second = client.post(
            f"/api/projects/{project['project_id']}/runs",
            json={"schema_version": "1", "profile_id": profile["profile_id"], "idempotency_key": "api-sse-test"},
        )
        assert first.status_code == second.status_code == 202, (first.text, second.text)
        job = first.json()["data"]["job"]
        assert second.json()["data"]["run"]["run_id"] == first.json()["data"]["run"]["run_id"]
        assert client.post(f"/api/jobs/{job['job_id']}/cancel").status_code == 200
        events = client.get(f"/api/jobs/{job['job_id']}/events", headers={"Last-Event-ID": "0"})
        assert events.status_code == 200
        assert "id: 1" in events.text and "id: 2" in events.text
        resumed = client.get(f"/api/jobs/{job['job_id']}/events", headers={"Last-Event-ID": "1"})
        assert "id: 1" not in resumed.text and "id: 2" in resumed.text
        query_precedence = client.get(f"/api/jobs/{job['job_id']}/events?after=1", headers={"Last-Event-ID": "0"})
        assert "id: 1" not in query_precedence.text

def test_api_run_uses_explicit_governed_active_snapshot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("JIEJIAN_WEB_TEST_MEMBER_TOKEN", "member-test")
    monkeypatch.setenv("JIEJIAN_WEB_TEST_READER_TOKEN", "reader-test")
    monkeypatch.setenv("JIEJIAN_WEB_TEST_OBSERVER_TOKEN", "observer-test")
    var_dir = tmp_path / "var"
    app = create_app(var_dir, start_worker=False)
    profile_path = _write_profile(tmp_path)
    with TestClient(app) as client:
        project, contract, profile = _register_active_profile(app, client, profile_path)
        submitted = client.post(
            f"/api/projects/{project['project_id']}/runs",
            json={"schema_version": "1", "profile_id": profile["profile_id"], "idempotency_key": "governed-run"},
        )
        assert submitted.status_code == 202, submitted.text
        job = submitted.json()["data"]["job"]
        request = ExecutionRequestStore(var_dir).load(job["job_id"], expected_hash=job["request_hash"])
        assert request.project_snapshot.contract == contract
        assert request.project_snapshot.contract.contract_id == contract.contract_id
        assert request.project_snapshot.contract.version == contract.version
        version = app.state.context.contracts.list_versions(str(project["project_id"]), contract.contract_id)[0]
        assert version.status is ContractStatus.ACTIVE

def test_api_run_rejects_missing_governed_binding(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("JIEJIAN_WEB_TEST_MEMBER_TOKEN", "member-test")
    monkeypatch.setenv("JIEJIAN_WEB_TEST_READER_TOKEN", "reader-test")
    monkeypatch.setenv("JIEJIAN_WEB_TEST_OBSERVER_TOKEN", "observer-test")
    app = create_app(tmp_path / "var", start_worker=False)
    profile_path = _write_profile(tmp_path)
    with TestClient(app) as client:
        project, _, profile = _register_active_profile(app, client, profile_path)
        _set_governed_binding(app, str(project["project_id"]), None, None)
        response = client.post(
            f"/api/projects/{project['project_id']}/runs",
            json={"schema_version": "1", "profile_id": profile["profile_id"], "idempotency_key": "missing-governed"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "CONTRACT_NOT_ACTIVE"
        assert client.get(f"/api/projects/{project['project_id']}/runs").json()["data"] == []

def test_api_run_rejects_non_active_governed_binding(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("JIEJIAN_WEB_TEST_MEMBER_TOKEN", "member-test")
    monkeypatch.setenv("JIEJIAN_WEB_TEST_READER_TOKEN", "reader-test")
    monkeypatch.setenv("JIEJIAN_WEB_TEST_OBSERVER_TOKEN", "observer-test")
    app = create_app(tmp_path / "var", start_worker=False)
    profile_path = _write_profile(tmp_path)
    with TestClient(app) as client:
        project, contract, profile = _register_active_profile(app, client, profile_path)
        revision = app.state.context.contracts.revise_active(
            str(project["project_id"]),
            contract.contract_id,
            snapshot=contract.model_copy(update={"version": 2}),
            actor="reviser",
        )
        review = app.state.context.contracts.submit_review(
            str(project["project_id"]), revision.contract_id, revision.version, actor="reviewer"
        )
        app.state.context.contracts.activate_review(
            str(project["project_id"]), review.contract_id, review.version, actor="approver"
        )
        _set_governed_binding(app, str(project["project_id"]), contract.contract_id, contract.version)
        response = client.post(
            f"/api/projects/{project['project_id']}/runs",
            json={"schema_version": "1", "profile_id": profile["profile_id"], "idempotency_key": "draft-governed"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "CONTRACT_NOT_ACTIVE"
        assert client.get(f"/api/projects/{project['project_id']}/runs").json()["data"] == []
