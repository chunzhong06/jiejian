from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from product.backend.api import create_app
import product.backend.workflows.onboarding.demo as demo_module


def _all_file_bytes(root: Path) -> bytes:
    return b"\n".join(path.read_bytes() for path in root.rglob("*") if path.is_file())


@pytest.mark.parametrize(
    ("variant", "expected_verdict"),
    (("fixed", "PASS"), ("vulnerable", "BLOCK"), ("inconclusive", "INCONCLUSIVE")),
)
def test_real_onboarding_demo_worker_runner_publication_and_secret_boundary(
    tmp_path: Path, monkeypatch, variant: str, expected_verdict: str
) -> None:
    secret_values = (
        f"C6_PRIMARY_{variant}_9c4e",
        f"C6_COMPARISON_{variant}_7b1a",
        f"C6_PEER_{variant}_5d2f",
    )
    sentinels = iter(secret_values)
    monkeypatch.setattr(demo_module.secrets, "token_urlsafe", lambda _size: next(sentinels))
    var_dir = tmp_path / "var"
    app = create_app(var_dir, start_worker=True)

    with TestClient(app) as client:
        started = client.post("/api/onboarding/demo/start", json={"schema_version": "1", "variant": variant})
        assert started.status_code == 200, started.text
        payload = started.json()["data"]
        assert payload["demo_data"] is True
        assert payload["variant"] == variant
        assert payload["message"] == "演示数据，不代表真实项目；检查已排队。"
        run_id = payload["run_id"]
        project_id = payload["project_id"]
        job_id = payload["job_id"]
        profile = json.loads((var_dir / "onboarding" / payload["session_id"] / "profile.json").read_text(encoding="utf-8"))
        assert profile["action_bindings"][0]["action_id"] == "modify"
        assert profile["action_bindings"][0]["method"] == "PATCH"
        assert {item["id"] for item in profile["identities"]} == {"owner", "attacker", "peer"}
        assert next(item for item in profile["identities"] if item["id"] == "peer")["secret_ref"] == "env:JIEJIAN_DEMO_PEER_TOKEN"
        assert {item["subject_id"] for item in profile["subject_bindings"]} == {"attacker", "peer"}
        assert profile["observer_bindings"][0]["observer_type"] == "OWNER_API"
        active_contract = app.state.context.projects.current_contract(project_id).snapshot
        assert set(active_contract.role_ids) == {"user", "guest"}
        assert {item.subject_id for item in active_contract.subjects} == {"owner", "attacker", "peer"}
        assert len(active_contract.rules) == 1
        rule = active_contract.rules[0]
        assert (rule.subject_id, rule.action_id, rule.expectation.value) == ("attacker", "modify", "DENY")
        assert rule.required_observations == ("resource_state",)

        detail = None
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            response = client.get(f"/api/runs/{run_id}")
            assert response.status_code == 200, response.text
            detail = response.json()["data"]
            if detail["lifecycle"] in {"COMPLETED", "SAFETY_STOPPED", "FAILED", "CANCELLED"}:
                break
            time.sleep(0.1)

        assert detail is not None
        assert detail["lifecycle"] == "COMPLETED", detail
        assert detail["result_integrity"] == "VERIFIED"
        assert detail["verdict"] == expected_verdict
        assert detail["run_id"] == run_id

        findings = client.get(f"/api/runs/{run_id}/findings")
        evidence = client.get(f"/api/runs/{run_id}/evidence")
        reports = client.get(f"/api/runs/{run_id}/reports")
        assert findings.status_code == evidence.status_code == reports.status_code == 200
        assert reports.json()["data"] == []
        assert detail["case_progress"]["status"] == "PUBLISHED"
        assert detail["finding_count"] == len(findings.json()["data"])
        evidence_index = evidence.json()["data"]
        assert evidence_index
        evidence_detail = client.get(f"/api/runs/{run_id}/evidence/{evidence_index[0]['evidence_id']}")
        assert evidence_detail.status_code == 200, evidence_detail.text
        evidence_payload = evidence_detail.json()["data"]
        expected_outcome = "UNKNOWN" if variant == "inconclusive" else "DENIED"
        assert evidence_payload["execution_fact"]["outcome"] == expected_outcome
        effects = {item["effect"] for item in evidence_payload["observation_facts"]}
        expected_effect = {"fixed": "ABSENT", "vulnerable": "CONFIRMED", "inconclusive": "UNKNOWN"}[variant]
        assert expected_effect in effects

        repeated = client.post("/api/onboarding/demo/start", json={"schema_version": "1", "variant": variant}).json()["data"]
        assert (repeated["project_id"], repeated["run_id"], repeated["job_id"]) == (
            project_id,
            run_id,
            job_id,
        )

        session = client.get(f"/api/onboarding/sessions/{payload['session_id']}")
        assert session.status_code == 200
        assert session.json()["data"]["status"] == "SUBMITTED"

    content = _all_file_bytes(var_dir)
    for secret in secret_values:
        assert secret.encode("utf-8") not in content
    assert app.state.context.demo._process is None
    worker_process = app.state.worker_supervisor._process
    assert worker_process is None or worker_process.poll() is not None
