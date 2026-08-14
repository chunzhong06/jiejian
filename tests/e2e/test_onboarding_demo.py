from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from jiejian.api import create_app
import jiejian.onboarding.demo as demo_module


def _all_file_bytes(root: Path) -> bytes:
    return b"\n".join(path.read_bytes() for path in root.rglob("*") if path.is_file())


def test_real_onboarding_demo_worker_runner_publication_and_secret_boundary(
    tmp_path: Path, monkeypatch
) -> None:
    sentinels = iter(("C4_PRIMARY_SENTINEL_9c4e", "C4_COMPARISON_SENTINEL_7b1a"))
    monkeypatch.setattr(demo_module.secrets, "token_urlsafe", lambda _size: next(sentinels))
    var_dir = tmp_path / "var"
    app = create_app(var_dir, start_worker=True)

    with TestClient(app) as client:
        started = client.post("/api/v1/onboarding/demo/start")
        assert started.status_code == 200, started.text
        payload = started.json()["data"]
        assert payload["demo_data"] is True
        assert payload["message"] == "演示数据，不代表真实项目；检查已排队。"
        run_id = payload["run_id"]
        project_id = payload["project_id"]
        job_id = payload["job_id"]

        detail = None
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            response = client.get(f"/api/v1/runs/{run_id}")
            assert response.status_code == 200, response.text
            detail = response.json()["data"]
            if detail["lifecycle"] in {"COMPLETED", "SAFETY_STOPPED", "FAILED", "CANCELLED"}:
                break
            time.sleep(0.1)

        assert detail is not None
        assert detail["lifecycle"] == "COMPLETED", detail
        assert detail["result_integrity"] == "VERIFIED"
        assert detail["verdict"] == "PASS"
        assert detail["run_id"] == run_id

        findings = client.get(f"/api/v1/runs/{run_id}/findings")
        evidence = client.get(f"/api/v1/runs/{run_id}/evidence")
        report = client.get(f"/api/v1/runs/{run_id}/report")
        assert findings.status_code == evidence.status_code == report.status_code == 200
        assert report.json()["data"]["verdict"] == detail["verdict"]
        assert detail["case_progress"]["status"] == "PUBLISHED"
        assert detail["finding_count"] == len(findings.json()["data"])
        assert evidence.json()["data"]

        repeated = client.post("/api/v1/onboarding/demo/start").json()["data"]
        assert (repeated["project_id"], repeated["run_id"], repeated["job_id"]) == (
            project_id,
            run_id,
            job_id,
        )

        session = client.get(f"/api/v1/onboarding/sessions/{payload['session_id']}")
        assert session.status_code == 200
        assert session.json()["data"]["status"] == "SUBMITTED"

    content = _all_file_bytes(var_dir)
    assert b"C4_PRIMARY_SENTINEL_9c4e" not in content
    assert b"C4_COMPARISON_SENTINEL_7b1a" not in content
    assert app.state.context.demo._process is None
    worker_process = app.state.worker_manager._process
    assert worker_process is None or worker_process.poll() is not None
