from __future__ import annotations

import io
import json
import os
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from product.backend.api import create_app
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import JobState, RunLifecycle
from product.backend.infra.runtime.jobs.models import RequestCancellation, WaitingFatalFailure
from product.backend.infra.runtime.worker_supervisor import LocalWorkerSupervisor
from product.backend.infra.artifacts.run_packages import PUBLICATION_MANIFEST_NAME
import product.backend.workflows.onboarding.demo as demo_module
from product.backend.workflows.onboarding.demo import DemoRuntimeSupervisor
from product.backend.workflows.onboarding.demo_target import create_demo_target_server
from product.backend.workflows.onboarding.models import OnboardingDemoStatus, OnboardingSession
from product.backend.workflows.onboarding.session import OnboardingSessionStore
from product.backend.workflows.onboarding.workflow import OnboardingWorkflow


class FakeVault:
    def __init__(self) -> None:
        self.cleared: list[str] = []
        self.values: dict[str, dict[str, str]] = {}

    def put(self, session_id: str, values: dict[str, str]) -> None:
        self.values[session_id] = dict(values)

    def clear_session(self, session_id: str) -> None:
        self.cleared.append(session_id)


class FakeStatusReader:
    def __init__(self, reusable: bool = True) -> None:
        self.reusable = reusable

    def can_reuse(self, _status: OnboardingDemoStatus) -> bool:
        return self.reusable


class FakeOnboarding:
    def __init__(self) -> None:
        self.session = SimpleNamespace(
            session_id="onb_0123456789abcdef0123456789abcdef",
            revision=0,
            primary_secret_ref="env:JIEJIAN_ONB_DEMO_PRIMARY",
            comparison_secret_ref="env:JIEJIAN_ONB_DEMO_COMPARISON",
        )
        self.credentials: tuple[str, str] | None = None
        self.demo_credentials: tuple[str, str, str] | None = None
        self.updated = None
        self.demo_calls: list[str] = []

    def create_session(self, source: Path, project_name: str):
        assert source.name == "source"
        assert project_name == "界鉴内置演示"
        return self.session

    def put_credentials(self, session_id: str, primary: str, comparison: str):
        assert session_id == self.session.session_id
        self.credentials = (primary, comparison)
        self.session.revision = 1

    def put_demo_credentials(self, session_id: str, owner: str, attacker: str, peer: str):
        assert session_id == self.session.session_id
        assert owner != attacker
        assert owner != peer
        assert attacker != peer
        self.demo_credentials = (owner, attacker, peer)
        self.session.revision = 1

    def get_session(self, session_id: str):
        assert session_id == self.session.session_id
        return self.session

    def update_session(self, session_id: str, update):
        assert session_id == self.session.session_id
        self.updated = update
        return self.session

    def demo_check(self, session_id: str, variant: str):
        self.demo_calls.append(variant)
        return SimpleNamespace(
            session=self.session,
            project_id=f"onboarding_demo_{variant}",
            run_id=f"run_{'0' * 15}{len(self.demo_calls):x}",
            job_id=f"job_{'0' * 15}{len(self.demo_calls):x}",
        )


class FakeProcess:
    def __init__(self, output: str, *, stderr=None) -> None:
        self.stdout = io.StringIO(output)
        self.stderr = stderr
        self.terminated = False
        self.killed = False
        self.exit_code: int | None = None

    def poll(self):
        if self.exit_code is not None:
            return self.exit_code
        return 0 if self.terminated or self.killed else None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout: float):
        assert 0 < timeout <= 2
        return 0

    def kill(self):
        self.killed = True


def test_demo_fake_process_is_fixed_concurrent_and_secret_minimal(tmp_path: Path, monkeypatch) -> None:
    onboarding = FakeOnboarding()
    vault = FakeVault()
    calls: list[tuple[list[str], dict]] = []
    processes: list[FakeProcess] = []
    secret_values = ("owner-demo-sentinel", "attacker-demo-sentinel", "peer-demo-sentinel")
    generated = iter(secret_values)
    monkeypatch.setattr(demo_module.secrets, "token_urlsafe", lambda _size: next(generated))

    def popen(command, **kwargs):
        calls.append((command, kwargs))
        process = FakeProcess("http://127.0.0.1:43123\n")
        processes.append(process)
        return process

    manager = DemoRuntimeSupervisor(
        onboarding,
        var_dir=tmp_path / "var",
        base_environment={"PATH": "path", "JIEJIAN_OTHER_SECRET": "not-for-demo"},
        secret_vault=vault,
        status_reader=FakeStatusReader(),
        popen=popen,
    )
    results: list[OnboardingDemoStatus] = []
    threads = [threading.Thread(target=lambda: results.append(manager.start("fixed"))) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[:4] == [
        sys.executable,
        "-B",
        "-m",
        "product.backend.infra.runtime.process_bootstrap",
    ]
    assert command[4] == "--gate"
    assert command[6:] == [
        "--module",
        "product.backend.workflows.onboarding.demo_target",
        "--",
        "--variant",
        "fixed",
        "--port",
        "0",
    ]
    assert kwargs["shell"] is False
    assert kwargs["stdin"] is not None
    assert set(kwargs["env"]) == {
        "PATH",
        "TEMP",
        "TMP",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONNOUSERSITE",
        "PYTHONUTF8",
        "JIEJIAN_PYTHON_EXECUTABLE",
        "JIEJIAN_VAR_DIR",
        "JIEJIAN_DEMO_OWNER_TOKEN",
        "JIEJIAN_DEMO_ATTACKER_TOKEN",
        "JIEJIAN_DEMO_PEER_TOKEN",
    }
    assert kwargs["env"]["JIEJIAN_DEMO_ATTACKER_TOKEN"] != kwargs["env"]["JIEJIAN_DEMO_PEER_TOKEN"]
    assert onboarding.demo_credentials == secret_values
    assert "JIEJIAN_OTHER_SECRET" not in kwargs["env"]
    assert results[0].run_id == results[1].run_id
    demo_roots = list((tmp_path / "var" / "temp" / "onboarding-demo").iterdir())
    assert len(demo_roots) == 1
    assert (demo_roots[0] / "source" / "package.json").is_file()
    assert manager.stop().status == "stopped"
    assert not demo_roots[0].exists()
    assert (tmp_path / "var" / "logs" / "app" / "onboarding-demo.log").is_file()
    assert vault.cleared == [onboarding.session.session_id]
    assert processes[0].stdout.closed


def test_put_demo_credentials_rejects_duplicate_peer_without_writing_vault(tmp_path: Path) -> None:
    vault = FakeVault()
    var_dir = tmp_path / "var"
    workflow = OnboardingWorkflow(
        var_dir=var_dir,
        vault=vault,
        projects=object(),
        contracts=object(),
        execution=object(),
    )
    session = OnboardingSession(
        session_id="onb_0123456789abcdef0123456789abcdef",
        source_path=str(tmp_path),
        project_name="界鉴内置演示",
        primary_secret_ref="env:JIEJIAN_ONB_DEMO_PRIMARY",
        comparison_secret_ref="env:JIEJIAN_ONB_DEMO_COMPARISON",
        project_id="onboarding_0123456789abcdef0123456789abcdef",
    )
    OnboardingSessionStore(var_dir).create(session)

    with pytest.raises(JiejianError) as raised:
        workflow.put_demo_credentials(session.session_id, "owner", "attacker", "attacker")

    assert raised.value.code == ErrorCode.ONBOARDING_CREDENTIALS_INVALID
    assert vault.values == {}


def test_demo_unexpected_exit_becomes_failed_and_closes_stdout(tmp_path: Path) -> None:
    onboarding = FakeOnboarding()
    vault = FakeVault()
    process: FakeProcess | None = None

    def popen(command, **kwargs):
        nonlocal process
        process = FakeProcess("http://127.0.0.1:43123\n")
        return process

    manager = DemoRuntimeSupervisor(
        onboarding,
        var_dir=tmp_path / "var",
        base_environment={"PATH": "path"},
        secret_vault=vault,
        status_reader=FakeStatusReader(),
        popen=popen,
    )
    assert manager.start("fixed").status == "running"
    assert process is not None
    process.exit_code = 17

    status = manager.status()

    assert status.status == "failed"
    assert "var/logs/onboarding-demo.log" in status.message
    assert process.stdout.closed
    assert manager._process is None


def test_demo_api_status_does_not_report_exited_process_as_running(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    manager = app.state.context.demo
    process = FakeProcess("", stderr=io.BytesIO())
    process.exit_code = 9
    manager._process = process
    manager._status = OnboardingDemoStatus(
        status="running",
        session_id="onb_0123456789abcdef0123456789abcdef",
        project_id="onboarding_demo",
        run_id="run_0123456789abcdef0123456789abcdef",
        job_id="job_0123456789abcdef0123456789abcdef",
        message="演示数据，不代表真实项目；检查已排队。",
    )

    with TestClient(app) as client:
        response = client.get("/api/onboarding/demo")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "failed"
    assert "var/logs/onboarding-demo.log" in response.json()["data"]["message"]
    assert process.stdout.closed
    assert process.stderr.closed


def test_demo_fake_ready_timeout_is_stable_and_cleans_secret(tmp_path: Path) -> None:
    onboarding = FakeOnboarding()
    vault = FakeVault()

    def popen(command, **kwargs):
        return FakeProcess("")

    manager = DemoRuntimeSupervisor(
        onboarding,
        var_dir=tmp_path / "var",
        base_environment=dict(os.environ),
        secret_vault=vault,
        status_reader=FakeStatusReader(),
        popen=popen,
    )
    with pytest.raises(JiejianError) as raised:
        manager.start("fixed")
    assert raised.value.code == ErrorCode.ONBOARDING_DEMO_FAILED
    assert onboarding.session.session_id in vault.cleared
    assert manager.status().status == "failed"


def test_demo_real_sample_ready_and_stop_without_http(tmp_path: Path) -> None:
    onboarding = FakeOnboarding()
    manager = DemoRuntimeSupervisor(
        onboarding,
        var_dir=tmp_path / "var",
        base_environment=dict(os.environ),
        secret_vault=FakeVault(),
        status_reader=FakeStatusReader(),
    )
    started = manager.start("fixed")
    assert started.status == "running"
    assert started.message == "演示数据，不代表真实项目；检查已排队。"
    stopped = manager.stop()
    assert stopped.status == "stopped"
    assert manager.status().status == "stopped"


def test_demo_api_start_worker_false_only_queues_and_hides_process_details(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        response = client.post("/api/onboarding/demo/start", json={"schema_version": "1", "variant": "fixed"})
        assert response.status_code == 200, response.text
        payload = response.json()["data"]
        assert payload["status"] == "running"
        assert payload["demo_data"] is True
        assert payload["variant"] == "fixed"
        assert payload["message"] == "演示数据，不代表真实项目；检查已排队。"
        assert "pid" not in response.text.lower()
        assert "token" not in response.text.lower()
        assert "product.backend.workflows.onboarding.demo_target" not in response.text
        assert client.get("/api/onboarding/demo").json()["data"]["run_id"] == payload["run_id"]
        repeated = client.post("/api/onboarding/demo/start", json={"schema_version": "1", "variant": "fixed"}).json()["data"]
        assert (repeated["project_id"], repeated["run_id"], repeated["job_id"]) == (payload["project_id"], payload["run_id"], payload["job_id"])
        switched = client.post("/api/onboarding/demo/start", json={"schema_version": "1", "variant": "vulnerable"}).json()["data"]
        assert switched["variant"] == "vulnerable"
        assert switched["run_id"] != payload["run_id"]
        assert client.post("/api/onboarding/demo/stop").json()["data"]["status"] == "stopped"
        assert client.post("/api/onboarding/demo/stop").json()["data"]["status"] == "stopped"


@pytest.mark.parametrize("terminal", ("failed", "cancelled"))
def test_demo_failed_or_cancelled_job_restarts_same_variant_with_new_audit_facts(
    tmp_path: Path,
    terminal: str,
) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    context = app.state.context
    with TestClient(app) as client:
        first = client.post(
            "/api/onboarding/demo/start",
            json={"schema_version": "1", "variant": "fixed"},
        ).json()["data"]
        if terminal == "failed":
            changed = context.job_attempts.record_waiting_fatal_failure(
                WaitingFatalFailure(
                    job_id=first["job_id"],
                    now_us=1_900_000_000_000_000,
                )
            )
            assert changed is not None
        else:
            context.job_queue.request_cancellation(
                RequestCancellation(
                    job_id=first["job_id"],
                    now_us=1_900_000_000_000_000,
                )
            )

        second = client.post(
            "/api/onboarding/demo/start",
            json={"schema_version": "1", "variant": "fixed"},
        ).json()["data"]

        assert second["run_id"] != first["run_id"]
        assert second["job_id"] != first["job_id"]
        with context.uow_factory() as work:
            old_job = work.jobs.get(first["job_id"])
            old_run = work.runs.get(first["run_id"])
        assert old_job is not None
        assert old_job.state is (
            JobState.FAILED if terminal == "failed" else JobState.CANCELLED
        )
        assert old_run is not None
        assert old_run.lifecycle is (
            RunLifecycle.FAILED
            if terminal == "failed"
            else RunLifecycle.CANCELLED
        )


def test_demo_preclaim_worker_process_failure_is_logged_and_not_relaunched(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sentinels = iter(
        (
            "demo-owner-secret-sentinel",
            "demo-attacker-secret-sentinel",
            "demo-peer-secret-sentinel",
        )
    )
    monkeypatch.setattr(
        demo_module.secrets,
        "token_urlsafe",
        lambda _size: next(sentinels),
    )
    var_dir = tmp_path / "var"
    app = create_app(var_dir, start_worker=False)
    manager = None
    with TestClient(app) as client:
        started = client.post(
            "/api/onboarding/demo/start",
            json={"schema_version": "1", "variant": "fixed"},
        ).json()["data"]
        broken = var_dir / "data" / "projects" / "broken" / "runs" / "broken"
        broken.mkdir(parents=True)
        (broken / PUBLICATION_MANIFEST_NAME).write_text("{}", encoding="utf-8")
        (var_dir / "quarantine").write_text("block quarantine", encoding="utf-8")
        context = app.state.context
        manager = LocalWorkerSupervisor(
            context.var_dir,
            context.uow_factory,
            context.job_queue,
            attempt_service=context.job_attempts,
            environment_provider=context.environment_for_secret_names,
        )
        manager.start()
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                with context.uow_factory() as work:
                    job = work.jobs.get(started["job_id"])
                    run = work.runs.get(started["run_id"])
                if job is not None and job.state is JobState.FAILED:
                    break
                time.sleep(0.05)
            else:
                pytest.fail("pre-claim Worker failure did not reach FAILED")

            assert job is not None and job.attempt == 0
            assert run is not None and run.lifecycle is RunLifecycle.FAILED
            projected = client.get(f"/api/runs/{started['run_id']}")
            assert projected.status_code == 200
            assert projected.json()["data"]["lifecycle"] == "FAILED"
            assert projected.json()["data"]["job"]["state"] == "FAILED"
            time.sleep(0.2)
            with context.uow_factory() as work:
                events = work.job_events.list_for_job(started["job_id"])
            assert [event.event_type for event in events] == [
                "JOB_SUBMITTED",
                "JOB_FAILED",
            ]
            worker_log = (
                var_dir / "logs" / "workers" / f"{started['job_id']}.log"
            ).read_text(encoding="utf-8")
            main_log = (var_dir / "logs" / "app" / "jiejian.log").read_text(encoding="utf-8")
            assert worker_log.count("WORKER_PROCESS_ERROR") == 1
            assert started["job_id"] in worker_log
            for sentinel in (
                "demo-owner-secret-sentinel",
                "demo-attacker-secret-sentinel",
                "demo-peer-secret-sentinel",
            ):
                assert sentinel not in worker_log
                assert sentinel not in main_log
        finally:
            manager.stop()


def test_demo_start_requires_versioned_variant_body(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        assert client.post("/api/onboarding/demo/start").status_code == 422
        assert client.post("/api/onboarding/demo/start", json={"schema_version": "1", "variant": "unknown"}).status_code == 422


def test_demo_switches_variant_without_reusing_previous_process_or_run(tmp_path: Path) -> None:
    onboarding = FakeOnboarding()
    processes: list[FakeProcess] = []

    def popen(command, **kwargs):
        process = FakeProcess(f"http://127.0.0.1:{43123 + len(processes)}\n")
        processes.append(process)
        return process

    manager = DemoRuntimeSupervisor(
        onboarding,
        var_dir=tmp_path / "var",
        base_environment={"PATH": "path"},
        secret_vault=FakeVault(),
        status_reader=FakeStatusReader(),
        popen=popen,
    )
    fixed = manager.start("fixed")
    vulnerable = manager.start("vulnerable")

    assert len(processes) == 2
    assert processes[0].terminated is True
    assert fixed.variant == "fixed"
    assert vulnerable.variant == "vulnerable"
    assert fixed.run_id != vulnerable.run_id
    assert onboarding.demo_calls == ["fixed", "vulnerable"]


def test_demo_same_variant_restarts_when_persisted_status_is_not_reusable(
    tmp_path: Path,
) -> None:
    onboarding = FakeOnboarding()
    status_reader = FakeStatusReader()
    processes: list[FakeProcess] = []

    def popen(command, **kwargs):
        process = FakeProcess(f"http://127.0.0.1:{43123 + len(processes)}\n")
        processes.append(process)
        return process

    manager = DemoRuntimeSupervisor(
        onboarding,
        var_dir=tmp_path / "var",
        base_environment={"PATH": "path"},
        secret_vault=FakeVault(),
        status_reader=status_reader,
        popen=popen,
    )
    first = manager.start("fixed")
    status_reader.reusable = False
    second = manager.start("fixed")

    assert len(processes) == 2
    assert processes[0].terminated is True
    assert first.run_id != second.run_id
    assert onboarding.demo_calls == ["fixed", "fixed"]


@pytest.mark.parametrize("variant", ("fixed", "vulnerable", "inconclusive"))
def test_demo_target_three_variants_have_distinct_observable_semantics(variant: str) -> None:
    tokens = {"owner": "owner-direct", "attacker": "attacker-direct", "peer": "peer-direct"}
    server = create_demo_target_server(variant=variant, port=0, tokens=tokens)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def call(path: str, *, token: str, method: str = "GET", body: dict | None = None, headers: dict[str, str] | None = None):
        request_headers = {"Authorization": f"Bearer {token}", **(headers or {})}
        request = Request(
            base + path,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            headers=request_headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read() or b"{}")
        except HTTPError as error:
            return error.code, json.loads(error.read() or b"{}")

    try:
        before_status, before = call("/owner/resources/owner-resource", token=tokens["owner"])
        patch_status, _ = call(
            "/resources/owner-resource",
            token=tokens["attacker"],
            method="PATCH",
            body={"value": f"changed-{variant}"},
            headers={"Content-Type": "application/json"},
        )
        after_status, after = call("/owner/resources/owner-resource", token=tokens["owner"])
        assert patch_status == 403
        if variant == "inconclusive":
            assert before_status == after_status == 503
        else:
            assert before_status == after_status == 200
            assert (after["value"] == before["value"]) is (variant == "fixed")
        assert call("/reset", token=tokens["owner"], method="POST", headers={"X-Jiejian-Test-Mode": "1"})[0] == 204
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
