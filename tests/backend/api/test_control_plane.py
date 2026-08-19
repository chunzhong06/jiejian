from __future__ import annotations

import json
import os
from pathlib import Path
import time

from fastapi.testclient import TestClient
import pytest
from typer.testing import CliRunner

from product.backend.api import create_app
from product.backend.infra.runtime.serve_lock import ServeLock
from product.backend.cli.app import app as cli_app
from product.backend.core.contracts.models import ContractStatus
from product.backend.core.errors import JiejianError
from product.backend.core.verification.permissions import PermissionContract
from product.backend.infra.runtime.job_requests import ExecutionRequestStore
from product.backend.infra.recording.request_store import RecordingRequestStore
from product.backend.cli.commands.system import _wait_for_ready
from product.protocols import canonical_execution_profile_json_bytes, parse_execution_profile

pytestmark = [pytest.mark.database, pytest.mark.process, pytest.mark.slow]

PROFILE_SOURCE = Path("samples/http/fixed/profile.json").resolve()
CONTRACT_SOURCE = Path("samples/http/fixed/contract.json").resolve()


def _write_profile(tmp_path: Path, *, port: int | None = None) -> Path:
    profile = parse_execution_profile(PROFILE_SOURCE.read_bytes())
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
    path.write_bytes(canonical_execution_profile_json_bytes(profile))
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


@pytest.mark.essential
def test_control_plane_health_ready_openapi_and_project_restart(tmp_path: Path) -> None:
    var_dir = tmp_path / "var"
    app = create_app(var_dir, start_worker=False)
    with TestClient(app) as client:
        assert client.get("/health").json() == {"schema_version": "1", "status": "ok"}
        assert client.get("/ready").json()["status"] == "ready"
        status = client.get("/api/system/status")
        assert status.status_code == 200
        assert status.json()["schema_version"] == "1"
        assert status.json()["data"]["api"] == "available"
        assert status.json()["data"]["worker"] == "stopped"
        assert status.json()["data"]["browser"] in {"available", "unavailable", "unknown"}
        openapi = client.get("/openapi.json")
        assert openapi.status_code == 200
        assert "ApiResponse" in openapi.json()["components"]["schemas"]
        assert "202" in openapi.json()["paths"]["/api/projects/{project_id}/runs"]["post"]["responses"]
        project_path = Path("samples/http/fixed/profile.json").resolve()
        response = client.post(
            "/api/projects",
                json={"schema_version": "1", "profile_path": str(project_path)},
        )
        assert response.status_code == 200
        project_id = response.json()["data"]["project_id"]
        assert client.get(f"/api/projects/{project_id}").status_code == 200

    restarted = create_app(var_dir, start_worker=False)
    with TestClient(restarted) as client:
        assert client.get(f"/api/projects/{project_id}").status_code == 200


def test_control_plane_rejects_invalid_binding_and_redacts_trace(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        response = client.post(
            "/api/projects",
            headers={"X-Trace-ID": "trace-safe"},
                json={"schema_version": "1", "profile_path": "missing.json"},
        )
        assert response.status_code == 400
        assert response.json()["trace_id"] == "trace-safe"
        assert response.json()["error"]["schema_version"] == "1"


def test_run_idempotency_cancel_and_sse_cursor(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("JIEJIAN_AUTHORIZATION_OWNER_TOKEN", "owner-test")
    monkeypatch.setenv("JIEJIAN_AUTHORIZATION_ATTACKER_TOKEN", "attacker-test")
    monkeypatch.setenv("JIEJIAN_AUTHORIZATION_PEER_TOKEN", "peer-test")
    monkeypatch.setenv("JIEJIAN_AUTHORIZATION_OWNER_OBSERVER", "owner-test")
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
    monkeypatch.setenv("JIEJIAN_AUTHORIZATION_OWNER_TOKEN", "owner-test")
    monkeypatch.setenv("JIEJIAN_AUTHORIZATION_ATTACKER_TOKEN", "attacker-test")
    monkeypatch.setenv("JIEJIAN_AUTHORIZATION_PEER_TOKEN", "peer-test")
    monkeypatch.setenv("JIEJIAN_AUTHORIZATION_OWNER_OBSERVER", "owner-test")
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
    monkeypatch.setenv("JIEJIAN_AUTHORIZATION_OWNER_TOKEN", "owner-test")
    monkeypatch.setenv("JIEJIAN_AUTHORIZATION_ATTACKER_TOKEN", "attacker-test")
    monkeypatch.setenv("JIEJIAN_AUTHORIZATION_PEER_TOKEN", "peer-test")
    monkeypatch.setenv("JIEJIAN_AUTHORIZATION_OWNER_OBSERVER", "owner-test")
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
    monkeypatch.setenv("JIEJIAN_AUTHORIZATION_OWNER_TOKEN", "owner-test")
    monkeypatch.setenv("JIEJIAN_AUTHORIZATION_ATTACKER_TOKEN", "attacker-test")
    monkeypatch.setenv("JIEJIAN_AUTHORIZATION_PEER_TOKEN", "peer-test")
    monkeypatch.setenv("JIEJIAN_AUTHORIZATION_OWNER_OBSERVER", "owner-test")
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


def test_profile_reregistration_preserves_explicit_active_contract(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    profile_path = _write_profile(tmp_path)
    with TestClient(app) as client:
        project, active, _ = _register_active_profile(app, client, profile_path)
        response = client.post(
            "/api/projects",
            json={"schema_version": "1", "profile_path": str(profile_path)},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["governed_contract_id"] == active.contract_id
        assert data["governed_contract_version"] == active.version


@pytest.mark.essential
def test_recording_api_uses_registered_profile_and_single_identity(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    profile_path = _write_profile(tmp_path)
    with TestClient(app) as client:
        project, _, profile = _register_active_profile(app, client, profile_path)
        setup = client.get(
            f"/api/projects/{project['project_id']}/recordings/setup",
            params={"profile_id": profile["profile_id"]},
        )
        assert setup.status_code == 200, setup.text
        assert setup.json()["data"]["identity_options"]
        assert "secret_ref" not in json.dumps(setup.json()["data"])
        schema = client.get("/openapi.json").json()["components"]["schemas"][
            "RecordingCreateRequest"
        ]["properties"]
        assert set(schema) == {
            "schema_version",
            "profile_id",
            "identity_id",
            "duration_seconds",
            "idempotency_key",
        }
        valid = client.post(
            f"/api/projects/{project['project_id']}/recordings",
            json={
                "schema_version": "1",
                "profile_id": profile["profile_id"],
                "identity_id": "owner",
                "duration_seconds": 60,
                "idempotency_key": "single-owner",
            },
        )
        assert valid.status_code == 202, valid.text
        data = valid.json()["data"]
        assert data["identity_options"] == [
            {"identity_id": "owner", "role": "user"},
            {"identity_id": "attacker", "role": "user"},
            {"identity_id": "peer", "role": "guest"},
        ]
        request = RecordingRequestStore(tmp_path / "var").load(
            data["job"]["job_id"], expected_hash=data["job"]["request_hash"]
        )
        assert request.headless is False
        assert tuple(item.identity_id for item in request.sessions) == ("owner",)
        detail = client.get(f"/api/recordings/{data['recording']['recording_id']}")
        assert detail.status_code == 200
        assert detail.json()["data"]["capture_phase"] == "PREPARING_BROWSER"
        assert client.post(f"/api/jobs/{data['job']['job_id']}/cancel").status_code == 200
        cancelled = client.get(f"/api/recordings/{data['recording']['recording_id']}")
        assert cancelled.json()["data"]["recording"]["state"] == "CANCELLED"
        assert cancelled.json()["data"]["capture_phase"] == "FINISHED"
        assert cancelled.json()["data"]["draft"] is None
        rejected = client.post(
            f"/api/projects/{project['project_id']}/recordings",
            json={
                "schema_version": "1",
                "profile_path": str(profile_path),
                "identities": ["owner"],
                "headless": True,
                "idempotency_key": "legacy-fields",
            },
        )
        assert rejected.status_code == 422, rejected.text


def test_serve_lock_releases_normally_and_diagnoses_existing_lock(tmp_path: Path) -> None:
    lock = ServeLock.acquire(tmp_path / "var")
    try:
        try:
            ServeLock.acquire(tmp_path / "var")
        except JiejianError as exc:
            assert exc.code == "SERVE_FAILED"
        else:
            raise AssertionError("expected existing serve lock rejection")
    finally:
        lock.release()
    assert ServeLock.acquire(tmp_path / "var").release() is None


def test_serve_requires_frontend_index_and_releases_lock(tmp_path: Path) -> None:
    missing = tmp_path / "missing-dist"
    result = CliRunner().invoke(
        cli_app,
        ["--var-dir", str(tmp_path / "var"), "serve", "--frontend-dir", str(missing)],
    )
    assert result.exit_code != 0
    assert "SERVE_FAILED" in result.output
    assert not (tmp_path / "var" / ".serve.lock").exists()


def test_serve_rejects_non_loopback_before_frontend_and_releases_lock(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli_app,
        [
            "--var-dir",
            str(tmp_path / "var"),
            "serve",
            "--host",
            "0.0.0.0",
            "--frontend-dir",
            str(tmp_path / "missing-dist"),
        ],
    )
    assert result.exit_code != 0
    assert json.loads(result.stderr)["error"]["code"] == "API_BINDING_REJECTED"
    assert not (tmp_path / "var" / ".serve.lock").exists()


@pytest.mark.parametrize(
    "payload,status",
    [
        ({"schema_version": "1", "status": "ready"}, 500),
        ({"schema_version": "2", "status": "ready"}, 200),
        ({"schema_version": "1", "status": "starting"}, 200),
    ],
)
def test_browser_wait_requires_exact_ready_payload(payload: dict[str, str], status: int) -> None:
    class Server:
        started = True

    class Client:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def get(self, url, headers):
            assert url.endswith("/ready")
            assert headers["Accept"] == "application/json"
            return type("HttpResponse", (), {"status_code": status, "json": lambda self: payload})()

    def client_factory(): return Client()

    opened: list[str] = []
    assert _wait_for_ready(
        Server(), "127.0.0.1", 8765,
        client_factory=client_factory, open_browser=lambda url: opened.append(url) or True,
        timeout_seconds=0.01,
    ) is False
    assert opened == []


def test_browser_wait_opens_once_only_after_ready() -> None:
    class Server:
        started = True

    class Client:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def get(self, url, headers):
            assert url == "http://127.0.0.1:8765/ready"
            assert "Authorization" not in headers
            return type("HttpResponse", (), {"status_code": 200, "json": lambda self: {"schema_version": "1", "status": "ready"}})()

    def client_factory(): return Client()

    opened: list[str] = []
    assert _wait_for_ready(
        Server(), "127.0.0.1", 8765,
        client_factory=client_factory, open_browser=lambda url: opened.append(url) or True,
    ) is True
    assert opened == ["http://127.0.0.1:8765/"]


def test_create_app_serves_a_readable_frontend_index(tmp_path: Path) -> None:
    frontend = tmp_path / "dist"
    frontend.mkdir()
    (frontend / "index.html").write_text("<html>stage4</html>", encoding="utf-8")
    with TestClient(create_app(tmp_path / "var", frontend_dir=frontend, start_worker=False)) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "stage4" in response.text


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
                if detail["lifecycle"] in {"COMPLETED", "FAILED", "CANCELLED", "SAFETY_STOPPED"}:
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
        evidence = client.get(f"/api/runs/{run_id}/evidence").json()["data"]
        assert evidence
        evidence_detail = client.get(f"/api/runs/{run_id}/evidence/{evidence[0]['evidence_id']}")
        assert evidence_detail.status_code == 200
        evidence_payload = evidence_detail.json()["data"]
        assert evidence_payload.get("evidence_id") == evidence[0]["evidence_id"], evidence_detail.text
        assert evidence_payload.get("execution_fact") is not None
        assert evidence_payload.get("observation_facts")
        baseline_response = client.post(
            f"/api/projects/{project['project_id']}/baselines",
            json={"schema_version": "1", "accepted_run_id": run_id, "actor": "test", "reason": "current publication baseline"},
        )
        assert baseline_response.status_code == 200, baseline_response.text
        baseline_id = baseline_response.json()["data"]["baseline_id"]
        gate_response = client.post(
            f"/api/baselines/{baseline_id}/runs/{run_id}/gate",
            json={"schema_version": "1", "minimum_severity": "low"},
        )
        assert gate_response.status_code == 200, gate_response.text
        gate_result_id = gate_response.json()["data"]["gate_result_id"]
        runner_process_ids = tuple(sample.server.runner_process_ids)
    assert runner_process_ids and set(runner_process_ids) != {os.getpid()}
    cli_report = CliRunner().invoke(
        cli_app,
        ["--var-dir", str(var_dir), "report", run_id, "--format", "json", "--gate-result-id", gate_result_id],
        env=sample.environ,
    )
    assert cli_report.exit_code == 0, cli_report.output
    cli_payload = json.loads(cli_report.stdout)
    assert cli_payload["run_id"] == run_id
    with TestClient(create_app(var_dir, start_worker=False)) as client:
        available = client.get(f"/api/runs/{run_id}/reports")
        assert available.status_code == 200
        report_id = cli_payload["report_id"]
        api_report_response = client.get(f"/api/runs/{run_id}/reports/{report_id}")
        assert api_report_response.status_code == 200, api_report_response.text
        api_report = api_report_response.json()["data"]
    assert api_report == cli_payload

    report_path = var_dir / "reports" / "runs" / run_id / report_id / "report.json"
    report_path.write_text('{"tampered":true}', encoding="utf-8")
    with TestClient(create_app(var_dir, start_worker=False)) as client:
        tampered = client.get(f"/api/runs/{run_id}/reports/{report_id}")
    assert tampered.status_code != 200
    assert tampered.json()["error"]["code"] in {"ARTIFACT_HASH_MISMATCH", "ARTIFACT_MANIFEST", "REPORT_INTEGRITY"}
