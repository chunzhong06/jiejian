from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import time

from fastapi.testclient import TestClient
import pytest
from typer.testing import CliRunner

from jiejian.api import create_app
from jiejian.runtime.serve_lock import ServeLock
from jiejian.cli.app import app as cli_app
from jiejian.contracts.models import ContractSourceType, SourceReference
from jiejian.errors import JiejianError
from jiejian.execution.request_store import ExecutionRequestStore
from jiejian.cli.commands.system import _wait_for_ready

pytestmark = [pytest.mark.database, pytest.mark.process, pytest.mark.slow]


def _set_governed_binding(app, project_id: str, contract_id: str, version: int) -> None:
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


def test_control_plane_health_ready_openapi_and_project_restart(tmp_path: Path) -> None:
    var_dir = tmp_path / "var"
    app = create_app(var_dir, start_worker=False)
    with TestClient(app) as client:
        assert client.get("/health").json() == {"schema_version": "1", "status": "ok"}
        assert client.get("/ready").json()["status"] == "ready"
        status = client.get("/api/v1/system/status")
        assert status.status_code == 200
        assert status.json()["schema_version"] == "1"
        assert status.json()["data"]["api"] == "available"
        assert status.json()["data"]["worker"] == "stopped"
        assert status.json()["data"]["browser"] in {"available", "unavailable", "unknown"}
        openapi = client.get("/openapi.json")
        assert openapi.status_code == 200
        assert "ApiResponse" in openapi.json()["components"]["schemas"]
        assert "202" in openapi.json()["paths"]["/api/v1/projects/{project_id}/runs"]["post"]["responses"]
        project_path = Path("samples/fixed_apps/ownership/project.yaml").resolve()
        response = client.post(
            "/api/v1/projects",
            json={"schema_version": "1", "path": str(project_path)},
        )
        assert response.status_code == 200
        project_id = response.json()["data"]["project_id"]
        assert client.get(f"/api/v1/projects/{project_id}").status_code == 200

    restarted = create_app(var_dir, start_worker=False)
    with TestClient(restarted) as client:
        assert client.get(f"/api/v1/projects/{project_id}").status_code == 200


def test_control_plane_rejects_invalid_binding_and_redacts_trace(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/projects",
            headers={"X-Trace-ID": "trace-safe"},
            json={"schema_version": "1", "path": "missing.yaml"},
        )
        assert response.status_code == 400
        assert response.json()["trace_id"] == "trace-safe"
        assert response.json()["error"]["schema_version"] == "1"


def test_run_idempotency_cancel_and_sse_cursor(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        project_path = Path("samples/fixed_apps/ownership/project.yaml").resolve()
        project = client.post(
            "/api/v1/projects",
            json={"schema_version": "1", "path": str(project_path)},
        ).json()["data"]
        first = client.post(
            f"/api/v1/projects/{project['project_id']}/runs",
            json={"schema_version": "1", "idempotency_key": "api-sse-test"},
        )
        second = client.post(
            f"/api/v1/projects/{project['project_id']}/runs",
            json={"schema_version": "1", "idempotency_key": "api-sse-test"},
        )
        assert first.status_code == second.status_code == 202
        job = first.json()["data"]["job"]
        assert second.json()["data"]["run"]["run_id"] == first.json()["data"]["run"]["run_id"]
        assert client.post(f"/api/v1/jobs/{job['job_id']}/cancel").status_code == 200
        events = client.get(
            f"/api/v1/jobs/{job['job_id']}/events",
            headers={"Last-Event-ID": "0"},
        )
        assert events.status_code == 200
        assert "id: 1" in events.text
        assert "id: 2" in events.text
        resumed = client.get(
            f"/api/v1/jobs/{job['job_id']}/events",
            headers={"Last-Event-ID": "1"},
        )
        assert "id: 1" not in resumed.text
        assert "id: 2" in resumed.text
        query_precedence = client.get(
            f"/api/v1/jobs/{job['job_id']}/events?after=1",
            headers={"Last-Event-ID": "0"},
        )
        assert "id: 1" not in query_precedence.text


def test_api_run_uses_governed_active_snapshot_and_yaml_fallback_clear(
    tmp_path: Path,
) -> None:
    var_dir = tmp_path / "var"
    app = create_app(var_dir, start_worker=False)
    with TestClient(app) as client:
        project_path = Path("samples/fixed_apps/ownership/project.yaml").resolve()
        project = client.post(
            "/api/v1/projects",
            json={"schema_version": "1", "path": str(project_path)},
        ).json()["data"]
        project_id = project["project_id"]
        _, bundle = app.state.context.projects.current_bundle(project_id)
        draft = app.state.context.contracts.create_draft(
            project_id,
            "governed-api-contract",
            rules=bundle.contract.rules,
            sources=(
                SourceReference(
                    source_type=ContractSourceType.PROJECT_CONFIG,
                    locator="governed-test",
                    content_sha256="c" * 64,
                ),
            ),
            actor="test",
        )
        review = app.state.context.contracts.submit_review(
            project_id, draft.contract_id, draft.version, actor="reviewer"
        )
        active = app.state.context.contracts.activate_review(
            project_id, review.contract_id, review.version, actor="approver"
        )
        preserved = client.post(f"/api/v1/projects/{project_id}/revalidate")
        assert preserved.status_code == 200
        assert preserved.json()["data"]["governed_contract_id"] == active.contract_id
        assert preserved.json()["data"]["governed_contract_version"] == active.version
        run = client.post(
            f"/api/v1/projects/{project_id}/runs",
            json={"schema_version": "1", "idempotency_key": "governed-run"},
        )
        assert run.status_code == 202
        job = run.json()["data"]["job"]
        request = ExecutionRequestStore(var_dir).load(
            job["job_id"], expected_hash=job["request_hash"]
        )
        assert request.project_snapshot.contract.id == active.contract_id
        assert request.project_snapshot.contract.version == active.version
        assert request.project_snapshot.contract.status.value == "ACTIVE"

        alternative = tmp_path / "alternative-contract.yaml"
        alternative.write_text(
            (project_path.parent / "contract.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        cleared = client.post(
            f"/api/v1/projects/{project_id}/contracts/activate",
            json={"schema_version": "1", "path": str(alternative)},
        )
        assert cleared.status_code == 200
        assert cleared.json()["data"]["governed_contract_id"] is None
        assert cleared.json()["data"]["governed_contract_version"] is None
        revalidated = client.post(f"/api/v1/projects/{project_id}/revalidate")
        assert revalidated.status_code == 200
        assert revalidated.json()["data"]["governed_contract_id"] is None


def test_api_run_rejects_missing_governed_binding_without_yaml_fallback(
    tmp_path: Path,
) -> None:
    var_dir = tmp_path / "var"
    app = create_app(var_dir, start_worker=False)
    with TestClient(app) as client:
        project_path = Path("samples/fixed_apps/ownership/project.yaml").resolve()
        project = client.post(
            "/api/v1/projects",
            json={"schema_version": "1", "path": str(project_path)},
        ).json()["data"]
        project_id = project["project_id"]
        _set_governed_binding(app, project_id, "missing-governed-contract", 9)

        response = client.post(
            f"/api/v1/projects/{project_id}/runs",
            json={"schema_version": "1", "idempotency_key": "missing-governed"},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CONTRACT_NOT_FOUND"
        assert client.get(f"/api/v1/projects/{project_id}/runs").json()["data"] == []


def test_api_run_rejects_non_active_governed_binding_without_yaml_fallback(
    tmp_path: Path,
) -> None:
    var_dir = tmp_path / "var"
    app = create_app(var_dir, start_worker=False)
    with TestClient(app) as client:
        project_path = Path("samples/fixed_apps/ownership/project.yaml").resolve()
        project = client.post(
            "/api/v1/projects",
            json={"schema_version": "1", "path": str(project_path)},
        ).json()["data"]
        project_id = project["project_id"]
        _, bundle = app.state.context.projects.current_bundle(project_id)
        draft = app.state.context.contracts.create_draft(
            project_id,
            "draft-governed-contract",
            rules=bundle.contract.rules,
            sources=(
                SourceReference(
                    source_type=ContractSourceType.PROJECT_CONFIG,
                    locator="draft-governed-test",
                    content_sha256="d" * 64,
                ),
            ),
            actor="test",
        )
        _set_governed_binding(app, project_id, draft.contract_id, draft.version)

        response = client.post(
            f"/api/v1/projects/{project_id}/runs",
            json={"schema_version": "1", "idempotency_key": "draft-governed"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "CONTRACT_NOT_ACTIVE"
        assert client.get(f"/api/v1/projects/{project_id}/runs").json()["data"] == []


def test_run_rejects_changed_source_until_revalidated(tmp_path: Path) -> None:
    copied = tmp_path / "ownership"
    shutil.copytree(Path("samples/fixed_apps/ownership"), copied)
    source = copied / "project.yaml"
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        project = client.post(
            "/api/v1/projects",
            json={"schema_version": "1", "path": str(source)},
        ).json()["data"]
        source.write_text(source.read_text(encoding="utf-8") + "\n# source drift\n", encoding="utf-8")
        response = client.post(
            f"/api/v1/projects/{project['project_id']}/runs",
            json={"schema_version": "1", "idempotency_key": "must-revalidate"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "PROJECT_SOURCE_DRIFT"


def test_flow_source_drift_blocks_run_and_recording_until_revalidated(tmp_path: Path) -> None:
    copied = tmp_path / "ownership"
    shutil.copytree(Path("samples/fixed_apps/ownership"), copied)
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        project = client.post(
            "/api/v1/projects",
            json={"schema_version": "1", "path": str(copied / "project.yaml")},
        ).json()["data"]
        flow = copied / "flow.yaml"
        flow.write_text(flow.read_text(encoding="utf-8") + "\n# flow source drift\n", encoding="utf-8")
        run = client.post(
            f"/api/v1/projects/{project['project_id']}/runs",
            json={"schema_version": "1", "idempotency_key": "flow-drift-run"},
        )
        recording = client.post(
            f"/api/v1/projects/{project['project_id']}/recordings",
            json={"schema_version": "1", "identities": [], "duration_seconds": 60, "headless": True, "idempotency_key": "flow-drift-recording"},
        )
        assert run.status_code == recording.status_code == 409
        assert run.json()["error"]["code"] == recording.json()["error"]["code"] == "PROJECT_SOURCE_DRIFT"
        assert client.post(f"/api/v1/projects/{project['project_id']}/revalidate").status_code == 200
        assert client.post(
            f"/api/v1/projects/{project['project_id']}/runs",
            json={"schema_version": "1", "idempotency_key": "flow-drift-restored"},
        ).status_code == 202


def test_recording_json_array_schema_keeps_identity_validation(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        project_path = Path("samples/fixed_apps/ownership/project.yaml").resolve()
        project = client.post(
            "/api/v1/projects",
            json={"schema_version": "1", "path": str(project_path)},
        ).json()["data"]
        valid = client.post(
            f"/api/v1/projects/{project['project_id']}/recordings",
            json={"schema_version": "1", "identities": ["owner"], "duration_seconds": 60, "headless": True, "idempotency_key": "array-owner"},
        )
        duplicate = client.post(
            f"/api/v1/projects/{project['project_id']}/recordings",
            json={"schema_version": "1", "identities": ["owner", "owner"], "duration_seconds": 60, "headless": True, "idempotency_key": "array-duplicate"},
        )
        unknown = client.post(
            f"/api/v1/projects/{project['project_id']}/recordings",
            json={"schema_version": "1", "identities": ["not-a-project-identity"], "duration_seconds": 60, "headless": True, "idempotency_key": "array-unknown"},
        )
        assert valid.status_code == 202
        assert duplicate.status_code == 400
        assert duplicate.json()["error"]["code"] == "INPUT_INVALID"
        assert unknown.status_code == 400
        assert unknown.json()["error"]["code"] == "INPUT_INVALID"


def test_revalidation_preserves_explicit_active_contract(tmp_path: Path) -> None:
    copied = tmp_path / "ownership"
    shutil.copytree(Path("samples/fixed_apps/ownership"), copied)
    alternative = copied / "alternative-contract.yaml"
    alternative.write_text((copied / "contract.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        project = client.post(
            "/api/v1/projects",
            json={"schema_version": "1", "path": str(copied / "project.yaml")},
        ).json()["data"]
        activated = client.post(
            f"/api/v1/projects/{project['project_id']}/contracts/activate",
            json={"schema_version": "1", "path": str(alternative)},
        )
        assert activated.status_code == 200
        revalidated = client.post(
            f"/api/v1/projects/{project['project_id']}/revalidate",
        )
        assert revalidated.status_code == 200
        assert revalidated.json()["data"]["active_contract_path"] == str(alternative.resolve())


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


def test_api_worker_runner_publication_matches_cli_report(
    sample_server_factory,
    stage1_project_factory,
    monkeypatch,
    tmp_path: Path,
) -> None:
    sample = sample_server_factory("safe")
    project_path = stage1_project_factory(sample.port)
    for key, value in sample.environ.items():
        monkeypatch.setenv(key, value)
    var_dir = tmp_path / "api-real"
    app = create_app(var_dir, start_worker=True)
    with TestClient(app) as client:
        project = client.post(
            "/api/v1/projects",
            json={"schema_version": "1", "path": str(project_path)},
        ).json()["data"]
        submitted = client.post(
            f"/api/v1/projects/{project['project_id']}/runs",
            json={"schema_version": "1", "idempotency_key": "api-real-closure"},
        )
        assert submitted.status_code == 202
        run_id = submitted.json()["data"]["run"]["run_id"]
        deadline = time.monotonic() + 45
        detail = None
        while time.monotonic() < deadline:
            response = client.get(f"/api/v1/runs/{run_id}")
            if response.status_code == 200:
                detail = response.json()["data"]
                if detail["lifecycle"] in {"COMPLETED", "FAILED", "CANCELLED", "SAFETY_STOPPED"}:
                    break
            time.sleep(0.1)
        assert detail is not None and detail["lifecycle"] == "COMPLETED", detail
        assert detail["result_integrity"] == "VERIFIED"
        report = client.get(f"/api/v1/runs/{run_id}").json()["data"]
        api_report = client.get(f"/api/v1/runs/{run_id}/report").json()["data"]
        findings = client.get(f"/api/v1/runs/{run_id}/findings").json()["data"]
        assert api_report["run_id"] == run_id
        assert api_report["verdict"] == report["verdict"]
        assert findings == []
        assert report["finding_count"] == 0
        assert report["finding_count"] == len(findings)
        assert report["target_scope"]["base_url"] == f"http://127.0.0.1:{sample.port}"
        assert report["target_scope"]["max_requests"] == 64
        assert report["budget"]["max_requests"] == report["target_scope"]["max_requests"]
        assert report["observer_health"]["http"]["configured"] is True
        assert report["observer_health"]["owner_api"]["configured"] is True
        assert "http" in report["observer_health"]["required_observers"]
        assert "owner_api" in report["observer_health"]["required_observers"]
        assert report["case_progress"]["status"] == "PUBLISHED"
        assert report["case_progress"]["completed"] == report["case_progress"]["total"]
        assert report["case_progress"]["total"] > 0
        assert report["safety_context"] is None
        evidence = client.get(f"/api/v1/runs/{run_id}/evidence").json()["data"]
        assert evidence
        evidence_detail = client.get(
            f"/api/v1/runs/{run_id}/evidence/{evidence[0]['evidence_id']}"
        )
        assert evidence_detail.status_code == 200
        difference = evidence_detail.json()["data"]["difference"]
        assert {"baseline_request", "mutation_request", "side_effect_observations"} <= difference.keys()
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
    assert cli_payload["verdict"] == api_report["verdict"]

    report_path = (
        var_dir
        / "projects"
        / project["project_id"]
        / "runs"
        / run_id
        / "artifacts"
        / "report"
        / "report.json"
    )
    report_path.write_text('{"tampered":true}', encoding="utf-8")
    with TestClient(create_app(var_dir, start_worker=False)) as client:
        tampered = client.get(f"/api/v1/runs/{run_id}")
    assert tampered.status_code != 200
    assert tampered.json()["error"]["code"] == "ARTIFACT_MANIFEST"
