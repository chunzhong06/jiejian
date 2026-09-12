# 当前真实应用入口的预览、不可变提交和只读状态，沿用本地控制面会话与同源保护。
import socket
import subprocess
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient as RawTestClient

from tests.fixtures.action_preparation import MemorySecretStore
from tests.fixtures.check_service import ready_check_harness
from tests.fixtures.control_plane import create_app, TestClient, TEST_CONTROL_ORIGIN


@pytest.fixture
def check_api(tmp_path):
    app = create_app(tmp_path / "var", start_worker=False, secret_store=MemorySecretStore(), environ={})
    harness = ready_check_harness(tmp_path, core=app.state.context)
    with TestClient(app) as client:
        yield app, harness, client


def test_current_preview_submit_and_status_use_no_target_or_secret_read(check_api, monkeypatch):
    app, harness, client = check_api
    forbidden = Mock(side_effect=AssertionError("API must not execute target or resolve credentials"))
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(app.state.context.secret_store, "read", forbidden)
    preview = client.get(f"/api/projects/{harness.project_id}/check-preview")
    assert preview.status_code == 200
    facts = preview.json()["data"]
    assert facts["can_execute"] and facts["action_count"] == 1
    body = dict(schema_version="2", expected_plan_fingerprint=facts["plan_fingerprint"], idempotency_key="check-api")
    path = f"/api/projects/{harness.project_id}/runs"
    response = client.post(path, json=body)
    assert response.status_code == 202
    accepted = response.json()["data"]
    assert client.post(path, json=body).json()["data"] == accepted
    run_id = accepted["run"]["run_id"]
    status = client.get(f"/api/runs/{run_id}").json()["data"]
    assert status["result_integrity"] == "NOT_PUBLISHED" and status["run"]["verdict"] is None
    assert client.get(path).json()["data"] == [status]
    assert client.get(f"/api/runs/{run_id}/result-story").status_code == 404
    assert client.get(f"/api/runs/{run_id}/evidence").status_code == 404
    assert "lease_owner" not in accepted["job"]
    forbidden.assert_not_called()


@pytest.mark.parametrize("extra", [{"profile_id": "old"}, {"cases": []}, {"rules": []}, {"target": "http://invalid"}])
def test_current_submit_rejects_legacy_or_arbitrary_execution_shape(check_api, extra):
    _, harness, client = check_api
    body = dict(schema_version="2", expected_plan_fingerprint="a" * 64, idempotency_key="shape") | extra
    assert client.post(f"/api/projects/{harness.project_id}/runs", json=body).status_code == 422


def test_current_submit_enforces_fingerprint_and_local_control(check_api):
    app, harness, client = check_api
    path = f"/api/projects/{harness.project_id}/runs"
    body = dict(schema_version="2", expected_plan_fingerprint="a" * 64, idempotency_key="stale")
    assert client.post(path, json=body).status_code == 409
    assert client.post(path, json=body, headers={"Origin": "https://foreign.invalid"}).status_code == 403
    raw = RawTestClient(app, base_url=TEST_CONTROL_ORIGIN)
    try:
        assert raw.post(path, json=body, headers={"Origin": TEST_CONTROL_ORIGIN}).status_code == 403
    finally:
        raw.close()
    assert client.post(path, json=body | {"schema_version": "1"}).status_code == 422
    assert client.get("/api/projects/missing-project/check-preview").status_code == 404
    assert client.get("/api/runs/run_" + "0" * 32).status_code == 404
    for suffix in ("checks", "check-preparation"):
        assert client.post(f"/api/projects/{harness.project_id}/{suffix}", json={}).status_code == 404
