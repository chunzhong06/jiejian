# 验证正式 API 读取真实发布文件与收据，禁用 AI 时保留确定性结果，篡改后拒绝详情。
import socket
import sqlite3
import subprocess
from unittest.mock import Mock

from product.backend.infra.artifacts.check_publication import CheckPublisher
from tests.backend.infra.runtime.jobs.test_check_publication import package_parts, NOW
from tests.fixtures.action_preparation import MemorySecretStore
from tests.fixtures.control_plane import create_app, TestClient


def test_published_api_story_evidence_disabled_assistant_and_tamper(package_parts, worker_services, monkeypatch):
    var_dir, factory, job, staging, result = package_parts
    package = CheckPublisher(var_dir, factory, clock_us=lambda: NOW + 20).publish(staging)
    (var_dir / "data").mkdir(exist_ok=True)
    with sqlite3.connect(worker_services.database_path) as source, sqlite3.connect(var_dir / "data/jiejian.db") as destination:
        source.backup(destination)
    app = create_app(var_dir, start_worker=False, secret_store=MemorySecretStore(), environ={})
    with TestClient(app) as client:
        forbidden = Mock(side_effect=AssertionError("published API must not execute target or recompute verdict"))
        monkeypatch.setattr(socket.socket, "connect", forbidden)
        monkeypatch.setattr(subprocess, "Popen", forbidden)
        monkeypatch.setattr("product.backend.core.verification.checks.evaluate_check_case", forbidden)
        prefix = f"/api/runs/{job.run_id}"
        story = client.get(prefix + "/result-story")
        assert story.status_code == 200
        comparison = story.json()["data"]["actions"][0]["fact_comparison"]
        assert comparison["planned_identity"]["identity_id"] is not None
        assert comparison["verified_actual_identity"]["verification_status"] == "UNKNOWN"
        assert comparison["verified_actual_identity"]["identity_id"] is None
        assert comparison["verified_actual_identity"]["label"] is None
        assert client.get(prefix).json()["data"]["run"]["verdict"] == result.verdict.value
        index = client.get(prefix + "/evidence").json()["data"]
        assert len(index) == len(package.evidence)
        assert "observations" not in index[0] and "case" not in index[0]
        detail = client.get(prefix + "/evidence/" + index[0]["evidence_id"])
        assert detail.status_code == 200 and "observations" in detail.json()["data"]
        explanation = client.get(prefix + "/assistant/result-explanation")
        assert explanation.status_code == 200
        assert explanation.json()["data"]["status"] == "DISABLED"
        assert client.get(prefix + "/result-story").json() == story.json()
        forbidden.assert_not_called()
        (package.directory / "result.json").write_bytes(b"{}")
        status = client.get(prefix).json()["data"]
        assert status["result_integrity"] == "INVALID" and status["run"]["verdict"] is None
        assert client.get(prefix + "/result-story").status_code >= 400
        assert client.get(prefix + "/evidence").status_code >= 400
