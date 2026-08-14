from __future__ import annotations

import io
import os
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from jiejian.api import create_app
from jiejian.errors import ErrorCode, JiejianError
from jiejian.onboarding.demo import DemoRuntimeManager
from jiejian.onboarding.models import OnboardingDemoStatus


class FakeVault:
    def __init__(self) -> None:
        self.cleared: list[str] = []

    def clear_session(self, session_id: str) -> None:
        self.cleared.append(session_id)


class FakeOnboarding:
    def __init__(self) -> None:
        self.session = SimpleNamespace(
            session_id="onb_0123456789abcdef0123456789abcdef",
            revision=0,
            primary_secret_ref="env:JIEJIAN_ONB_DEMO_PRIMARY",
            comparison_secret_ref="env:JIEJIAN_ONB_DEMO_COMPARISON",
        )
        self.credentials: tuple[str, str] | None = None
        self.updated = None

    def create_session(self, source: Path, project_name: str):
        assert source.name == "source"
        assert project_name == "界鉴内置演示"
        return self.session

    def put_credentials(self, session_id: str, primary: str, comparison: str):
        assert session_id == self.session.session_id
        self.credentials = (primary, comparison)
        self.session.revision = 1

    def get_session(self, session_id: str):
        assert session_id == self.session.session_id
        return self.session

    def update_session(self, session_id: str, update):
        assert session_id == self.session.session_id
        self.updated = update
        return self.session

    def quick_check(self, session_id: str):
        return SimpleNamespace(
            session=self.session,
            project_id="onboarding_demo",
            run_id="run_0123456789abcdef0123456789abcdef",
            job_id="job_0123456789abcdef0123456789abcdef",
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
        assert timeout == 2
        return 0

    def kill(self):
        self.killed = True


def test_demo_fake_process_is_fixed_concurrent_and_secret_minimal(tmp_path: Path) -> None:
    onboarding = FakeOnboarding()
    vault = FakeVault()
    calls: list[tuple[list[str], dict]] = []
    processes: list[FakeProcess] = []

    def popen(command, **kwargs):
        calls.append((command, kwargs))
        process = FakeProcess("http://127.0.0.1:43123\n")
        processes.append(process)
        return process

    manager = DemoRuntimeManager(
        onboarding,
        var_dir=tmp_path / "var",
        base_environment={"PATH": "path", "JIEJIAN_OTHER_SECRET": "not-for-demo"},
        secret_vault=vault,
        popen=popen,
    )
    results: list[OnboardingDemoStatus] = []
    threads = [threading.Thread(target=lambda: results.append(manager.start())) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command == [
        sys.executable,
        "-B",
        "-m",
        "jiejian.sample_app",
        "--variant",
        "vulnerable",
        "--port",
        "0",
    ]
    assert kwargs["shell"] is False
    assert kwargs["stdin"] is not None
    assert set(kwargs["env"]) == {"PATH", "PYTHONDONTWRITEBYTECODE", "PYTHONUTF8", "PYTHONPATH", "JIEJIAN_SAMPLE_OWNER_TOKEN", "JIEJIAN_SAMPLE_ATTACKER_TOKEN"}
    assert "JIEJIAN_OTHER_SECRET" not in kwargs["env"]
    assert results[0].run_id == results[1].run_id
    assert manager.stop().status == "stopped"
    assert vault.cleared == []
    assert processes[0].stdout.closed


def test_demo_unexpected_exit_becomes_failed_and_closes_stdout(tmp_path: Path) -> None:
    onboarding = FakeOnboarding()
    vault = FakeVault()
    process: FakeProcess | None = None

    def popen(command, **kwargs):
        nonlocal process
        process = FakeProcess("http://127.0.0.1:43123\n")
        return process

    manager = DemoRuntimeManager(
        onboarding,
        var_dir=tmp_path / "var",
        base_environment={"PATH": "path"},
        secret_vault=vault,
        popen=popen,
    )
    assert manager.start().status == "running"
    assert process is not None
    process.exit_code = 17

    status = manager.status()

    assert status.status == "failed"
    assert "var/log/onboarding-demo.log" in status.message
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
        response = client.get("/api/v1/onboarding/demo")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "failed"
    assert "var/log/onboarding-demo.log" in response.json()["data"]["message"]
    assert process.stdout.closed
    assert process.stderr.closed


def test_demo_fake_ready_timeout_is_stable_and_cleans_secret(tmp_path: Path) -> None:
    onboarding = FakeOnboarding()
    vault = FakeVault()

    def popen(command, **kwargs):
        return FakeProcess("")

    manager = DemoRuntimeManager(
        onboarding,
        var_dir=tmp_path / "var",
        base_environment=dict(os.environ),
        secret_vault=vault,
        popen=popen,
    )
    with pytest.raises(JiejianError) as raised:
        manager.start()
    assert raised.value.code == ErrorCode.ONBOARDING_DEMO_FAILED
    assert onboarding.session.session_id in vault.cleared
    assert manager.status().status == "failed"


def test_demo_real_sample_ready_and_stop_without_http(tmp_path: Path) -> None:
    onboarding = FakeOnboarding()
    manager = DemoRuntimeManager(
        onboarding,
        var_dir=tmp_path / "var",
        base_environment=dict(os.environ),
        secret_vault=FakeVault(),
    )
    started = manager.start()
    assert started.status == "running"
    assert started.message == "演示数据，不代表真实项目；检查已排队。"
    stopped = manager.stop()
    assert stopped.status == "stopped"
    assert manager.status().status == "stopped"


def test_demo_api_start_worker_false_only_queues_and_hides_process_details(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        response = client.post("/api/v1/onboarding/demo/start")
        assert response.status_code == 200, response.text
        payload = response.json()["data"]
        assert payload["status"] == "running"
        assert payload["demo_data"] is True
        assert payload["message"] == "演示数据，不代表真实项目；检查已排队。"
        assert "pid" not in response.text.lower()
        assert "token" not in response.text.lower()
        assert "jiejian.sample_app" not in response.text
        assert client.get("/api/v1/onboarding/demo").json()["data"]["run_id"] == payload["run_id"]
        assert client.post("/api/v1/onboarding/demo/stop").json()["data"]["status"] == "stopped"
