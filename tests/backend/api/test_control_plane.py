# 验证控制面 health、ready、LocalControl、serve 与启动接线。

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
from product.backend import __version__
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
from tests.fixtures.runner import seed_project_from_generated_profile, write_web_test_profile

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
        assert status.json()["data"]["version"] == __version__
        assert status.json()["data"]["api"] == "available"
        assert status.json()["data"]["worker"] == "unavailable"
        assert status.json()["data"]["browser"] in {"available", "unavailable", "unknown"}
        assert status.json()["data"]["environment"]["python"]["executable"]
        assert status.json()["data"]["recovered_jobs"] == 0
        openapi = client.get("/openapi.json")
        assert openapi.status_code == 200
        assert "ApiResponse" in openapi.json()["components"]["schemas"]
        project_path, _ = write_web_test_profile(tmp_path / "inputs")
        project_id = str(seed_project_from_generated_profile(app, project_path)["project_id"])
        assert client.get(f"/api/projects/{project_id}").status_code == 200

    restarted = create_app(var_dir, start_worker=False)
    with TestClient(restarted) as client:
        assert client.get(f"/api/projects/{project_id}").status_code == 200

def test_system_maintenance_api_previews_and_preserves_product_data(tmp_path: Path) -> None:
    var_dir = tmp_path / "var"
    app = create_app(var_dir, start_worker=False)
    data_marker = app.state.context.paths.data / "keep.txt"
    cache_marker = app.state.context.paths.assistant_cache / "rebuild.bin"
    data_marker.write_text("keep", encoding="utf-8")
    cache_marker.write_bytes(b"cache")
    # 此用例只验证显式 API；后台维护的并发与失败由相邻两项独立覆盖。
    app.state.context.maintenance.startup_maintenance = lambda: {"status": "completed"}

    with TestClient(app) as client:
        status = client.get("/api/system/maintenance")
        preview = client.post(
            "/api/system/maintenance/clear-assistant-cache",
            json={"schema_version": "1", "confirmed": False, "dry_run": True},
        )
        plan_id = preview.json()["data"]["plan_id"]
        applied = client.post(
            "/api/system/maintenance/clear-assistant-cache",
            json={
                "schema_version": "1",
                "confirmed": True,
                "dry_run": False,
                "plan_id": plan_id,
            },
        )

    assert status.status_code == 200
    assert status.json()["data"]["protected"]["data"] == str(
        app.state.context.paths.data
    )
    assert preview.json()["data"]["estimated_bytes"] >= len(b"cache")
    assert applied.status_code == 200
    assert data_marker.read_text(encoding="utf-8") == "keep"
    assert not cache_marker.exists()


def test_system_maintenance_unexpected_error_keeps_redacted_json_envelope(
    tmp_path: Path,
) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    app.state.context.maintenance.startup_maintenance = lambda: {"status": "completed"}

    def failed_preview(operation: str):
        raise OSError(r"C:\private\operator\secret.txt")

    app.state.context.maintenance.preview = failed_preview
    with TestClient(app) as client:
        response = client.post(
            "/api/system/maintenance/clear-temporary",
            json={"schema_version": "1", "confirmed": False, "dry_run": True},
        )

    payload = response.json()
    assert response.status_code == 503
    assert payload["schema_version"] == "1"
    assert payload["error"]["code"] == "LOCAL_MAINTENANCE_FAILED"
    assert "private" not in str(payload)

def test_ready_does_not_wait_for_blocked_local_maintenance(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    started = threading.Event()
    release = threading.Event()
    data = app.state.context.paths.data / "product-proof.txt"
    data.write_text("unchanged", encoding="utf-8")

    def blocked_maintenance():
        started.set()
        assert release.wait(timeout=5)
        return {"status": "completed"}

    app.state.context.maintenance.startup_maintenance = blocked_maintenance
    with TestClient(app) as client:
        assert started.wait(timeout=2)
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json() == {
            "schema_version": "1",
            "status": "ready",
            "worker": "unavailable",
        }
        assert not hasattr(app.state, "worker_supervisor")
        assert app.state.local_maintenance_task.done() is False
        release.set()

    assert data.read_text(encoding="utf-8") == "unchanged"

def test_local_maintenance_failure_does_not_revoke_ready(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)

    def failed_maintenance():
        raise RuntimeError("expected maintenance failure")

    app.state.context.maintenance.startup_maintenance = failed_maintenance
    with TestClient(app) as client:
        response = client.get("/ready")
        assert response.status_code == 200

    assert app.state.startup_maintenance == {"status": "failed"}

def test_local_control_guard_requires_host_session_and_same_origin_write(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("<html>界鉴</html>", encoding="utf-8")
    app = create_app(
        tmp_path / "var",
        frontend_dir=frontend,
        start_worker=False,
        shutdown_callback=lambda: calls.append("shutdown"),
    )
    with RawTestClient(app, base_url=TEST_CONTROL_ORIGIN) as client:
        missing_session = client.post(
            "/api/system/shutdown",
            headers={"Origin": TEST_CONTROL_ORIGIN},
        )
        page = client.get("/")
        cookie = page.headers["set-cookie"].casefold()
        assert "httponly" in cookie
        assert "samesite=strict" in cookie
        assert "path=/api" in cookie

        missing_origin = client.post("/api/system/shutdown")
        wrong_origin = client.post(
            "/api/system/shutdown",
            headers={"Origin": "https://evil.example"},
        )
        wrong_host = client.get(
            "/api/system/status",
            headers={"Host": "evil.example"},
        )
        accepted = client.post(
            "/api/system/shutdown",
            headers={
                "Origin": TEST_CONTROL_ORIGIN,
                "X-Forwarded-Host": "evil.example",
            },
        )

    assert missing_session.status_code == 403
    assert missing_origin.status_code == 403
    assert wrong_origin.status_code == 403
    assert wrong_host.status_code == 403
    assert wrong_origin.json()["error"]["code"] == "API_CONTROL_REJECTED"
    assert accepted.status_code == 202
    assert accepted.json()["data"]["status"] == "stopping"
    assert calls == ["shutdown"]

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

def test_serve_lock_reclaims_stale_owner(tmp_path: Path) -> None:
    lock_path = RuntimePaths(tmp_path / "var").locks / "serve.lock"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(
        json.dumps({"schema_version": "1", "pid": 2_147_483_647}),
        encoding="utf-8",
    )

    lock = ServeLock.acquire(tmp_path / "var")
    try:
        assert lock.acquired is True
    finally:
        lock.release()
    assert lock_path.is_file()

@pytest.mark.process
def test_serve_lock_is_released_by_process_exit(tmp_path: Path) -> None:
    var_dir = tmp_path / "var"
    child = subprocess.Popen(
        [
            sys.executable,
            "-B",
            "-c",
            (
                "import sys,time; from pathlib import Path; "
                "from product.backend.infra.runtime.serve_lock import ServeLock; "
                "lock=ServeLock.acquire(Path(sys.argv[1])); print('READY', flush=True); time.sleep(60)"
            ),
            str(var_dir),
        ],
        cwd=Path(__file__).parents[3],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "READY"
        with pytest.raises(JiejianError):
            ServeLock.acquire(var_dir)
    finally:
        child.kill()
        child.wait(timeout=10)

    lock = ServeLock.acquire(var_dir)
    lock.release()
    assert (RuntimePaths(var_dir).locks / "serve.lock").is_file()

def test_serve_requires_frontend_index_and_releases_lock(tmp_path: Path) -> None:
    missing = tmp_path / "missing-dist"
    result = CliRunner().invoke(
        cli_app,
        ["--var-dir", str(tmp_path / "var"), "serve", "--frontend-dir", str(missing)],
    )
    assert result.exit_code != 0
    assert "SERVE_FAILED" in result.output
    assert (RuntimePaths(tmp_path / "var").locks / "serve.lock").is_file()

@pytest.mark.parametrize("host", ["0.0.0.0", "::1"])
def test_serve_rejects_non_ipv4_control_host_before_frontend_and_releases_lock(
    tmp_path: Path,
    host: str,
) -> None:
    result = CliRunner().invoke(
        cli_app,
        [
            "--json",
            "--var-dir",
            str(tmp_path / "var"),
            "serve",
            "--host",
            host,
            "--frontend-dir",
            str(tmp_path / "missing-dist"),
        ],
    )
    assert result.exit_code != 0
    assert json.loads(result.stdout)["error"]["error_code"] == "API_BINDING_REJECTED"
    assert not (RuntimePaths(tmp_path / "var").locks / "serve.lock").exists()

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
        should_exit = False

    class Client:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def get(self, url, headers):
            assert url.endswith("/ready")
            assert headers["Accept"] == "application/json"
            Server.should_exit = True
            return type("HttpResponse", (), {"status_code": status, "json": lambda self: payload})()

    def client_factory(): return Client()

    opened: list[str] = []
    assert _wait_for_ready(
        Server(), "127.0.0.1", 8765,
        client_factory=client_factory, open_browser=lambda url: opened.append(url) or True,
        poll_interval_seconds=0,
    ) is ServeReadinessStatus.SERVER_STOPPED_BEFORE_READY
    assert opened == []

def test_browser_wait_opens_once_only_after_ready() -> None:
    class Server:
        started = True
        should_exit = False

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
    ) is ServeReadinessStatus.READY_BROWSER_OPENED
    assert opened == ["http://127.0.0.1:8765/"]

def test_browser_wait_soft_threshold_only_reports_still_starting() -> None:
    class Server:
        started = False
        should_exit = False

    class Client:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def get(self, *_args, **_kwargs):
            return type("HttpResponse", (), {"status_code": 200, "json": lambda self: {"schema_version": "1", "status": "ready"}})()

    server = Server()
    statuses: list[ServeReadinessStatus] = []
    opened: list[str] = []

    result = _wait_for_ready(
        server,
        "127.0.0.1",
        8765,
        client_factory=lambda: Client(),
        open_browser=lambda url: opened.append(url) or True,
        soft_wait_seconds=1,
        poll_interval_seconds=0,
        status_callback=statuses.append,
        monotonic=iter((0.0, 2.0, 2.0, 2.0)).__next__,
        sleeper=lambda _seconds: setattr(server, "started", True),
    )

    assert statuses == [ServeReadinessStatus.STARTUP_STILL_WAITING]
    assert result is ServeReadinessStatus.READY_BROWSER_OPENED
    assert opened == ["http://127.0.0.1:8765/"]

def test_browser_open_failure_is_only_returned_after_exact_ready() -> None:
    class Server:
        started = True
        should_exit = False

    class Client:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def get(self, *_args, **_kwargs):
            return type("HttpResponse", (), {"status_code": 200, "json": lambda self: {"schema_version": "1", "status": "ready"}})()

    assert _wait_for_ready(
        Server(),
        "127.0.0.1",
        8765,
        client_factory=lambda: Client(),
        open_browser=lambda _url: False,
    ) is ServeReadinessStatus.READY_BROWSER_OPEN_FAILED

def test_create_app_serves_a_readable_frontend_index(tmp_path: Path) -> None:
    frontend = tmp_path / "dist"
    frontend.mkdir()
    (frontend / "index.html").write_text("<html>frontend-shell</html>", encoding="utf-8")
    with TestClient(create_app(tmp_path / "var", frontend_dir=frontend, start_worker=False)) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "frontend-shell" in response.text
