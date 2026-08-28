# 验证后端 API中的权限契约工作台接口。

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fixtures.control_plane import TestClient, create_app

pytestmark = pytest.mark.database

from tests.fixtures.runner import write_web_test_profile


def _contract_snapshot(contract_path: Path, contract_id: str, version: int = 1) -> dict:
    snapshot = json.loads(contract_path.read_text(encoding="utf-8"))
    snapshot["contract_id"] = contract_id
    snapshot["version"] = version
    return snapshot


def _register(app, path: Path) -> str:
    return app.state.context.projects.register(path.resolve())[0].project_id


def test_contract_workbench_api_full_offline_governance_loop(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    profile_path, contract_path = write_web_test_profile(tmp_path / "base")
    with TestClient(app) as client:
        project_id = _register(app, profile_path)
        malformed = client.post(
            f"/api/projects/{project_id}/contract-governance/requirements",
            json={"schema_version": "1", "text": "任意自然语言", "security_tags": [], "actor": "analyst"},
        )
        malformed_requirement = malformed.json()["data"]
        blocked = client.post(
            f"/api/projects/{project_id}/contract-governance/candidates/derive",
            json={
                "schema_version": "1",
                "requirement_ids": [malformed_requirement["requirement_id"]],
                "actor": "analyst",
            },
        )
        assert blocked.status_code == 200
        assert blocked.json()["data"]["persisted_candidates"] == []
        assert any(issue["severity"] == "BLOCKING" for issue in blocked.json()["data"]["batches"][0]["issues"])

        requirement = client.post(
            f"/api/projects/{project_id}/contract-governance/requirements",
            json={
                "schema_version": "1",
                "text": "suggestion id=foreign-read kind=FOREIGN_READ observations=resource_state severity=high\nsuggestion id=unauthorized-side-effect kind=UNAUTHORIZED_SIDE_EFFECT observations=resource_state severity=critical\nsuggestion id=privileged-field kind=PRIVILEGED_FIELD observations=resource_state severity=critical",
                "security_tags": ["ownership"],
                "actor": "analyst",
            },
        ).json()["data"]
        derive_body = {
            "schema_version": "1",
            "requirement_ids": [requirement["requirement_id"]],
            "actor": "analyst",
        }
        first = client.post(
            f"/api/projects/{project_id}/contract-governance/candidates/derive",
            json=derive_body,
        )
        second = client.post(
            f"/api/projects/{project_id}/contract-governance/candidates/derive",
            json=derive_body,
        )
        assert first.status_code == second.status_code == 200
        candidates = first.json()["data"]["persisted_candidates"]
        assert [item["candidate_id"] for item in second.json()["data"]["persisted_candidates"]] == [item["candidate_id"] for item in candidates]

        draft_response = client.post(
            f"/api/projects/{project_id}/contract-governance/contracts",
            json={
                "schema_version": "1",
                "contract_id": "ownership-contract",
                "snapshot": _contract_snapshot(contract_path, "ownership-contract"),
                "candidate_ids": [item["candidate_id"] for item in candidates],
                "actor": "analyst",
            },
        )
        assert draft_response.status_code == 200, draft_response.text
        draft = draft_response.json()["data"]
        assessment = client.get(
            f"/api/projects/{project_id}/contract-governance/contracts/ownership-contract/versions/1/assessment"
        )
        assert assessment.status_code == 200
        assert assessment.json()["data"]["eligible"] is True
        review = client.post(
            f"/api/projects/{project_id}/contract-governance/contracts/ownership-contract/versions/{draft['version']}/submit",
            json={"schema_version": "1", "actor": "reviewer"},
        ).json()["data"]
        active = client.post(
            f"/api/projects/{project_id}/contract-governance/contracts/ownership-contract/versions/{review['version']}/activate",
            json={"schema_version": "1", "actor": "approver"},
        ).json()["data"]
        snapshot = client.get(f"/api/projects/{project_id}/contract-governance")
        assert snapshot.status_code == 200
        assert snapshot.json()["data"]["project"]["governed_contract_id"] == active["contract_id"]
        assert "llm_available" not in snapshot.json()["data"]

        revision = client.post(
            f"/api/projects/{project_id}/contract-governance/contracts/ownership-contract/revisions",
            json={
                "schema_version": "1",
                "snapshot": _contract_snapshot(contract_path, "ownership-contract", 2),
                "candidate_ids": [item["candidate_id"] for item in candidates],
                "actor": "analyst",
            },
        ).json()["data"]
        diff = client.get(
            f"/api/projects/{project_id}/contract-governance/contracts/ownership-contract/versions/{revision['version']}/diff",
            params={"from_version": 1},
        )
        assert diff.status_code == 200
        drift = client.get(
            f"/api/projects/{project_id}/contract-governance/contracts/ownership-contract/versions/{active['version']}/drift"
        )
        assert drift.status_code == 200

        removed = client.post(
            f"/api/projects/{project_id}/contract-governance/candidates/llm",
            json={"schema_version": "1", "requirement_ids": [requirement["requirement_id"]], "actor": "analyst"},
        )
        assert removed.status_code == 404


def test_contract_workbench_api_rejects_cross_project_requirement(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    first_profile, contract_path = write_web_test_profile(tmp_path / "first")
    second_profile, _ = write_web_test_profile(
        tmp_path / "second", project_id="web-test-project-second", profile_id="web-test-profile-second"
    )
    with TestClient(app) as client:
        first_project = _register(app, first_profile)
        second_project = _register(app, second_profile)
        requirement = client.post(
            f"/api/projects/{first_project}/contract-governance/requirements",
            json={
                "schema_version": "1",
                "text": "suggestion id=foreign-read kind=FOREIGN_READ observations=resource_state severity=high",
                "security_tags": [],
                "actor": "analyst",
            },
        ).json()["data"]
        response = client.post(
            f"/api/projects/{second_project}/contract-governance/candidates/derive",
            json={
                "schema_version": "1",
                "requirement_ids": [requirement["requirement_id"]],
                "actor": "analyst",
            },
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "CONTRACT_REFERENCE_INVALID"

        candidate = client.post(
            f"/api/projects/{first_project}/contract-governance/candidates/derive",
            json={
                "schema_version": "1",
                "requirement_ids": [requirement["requirement_id"]],
                "actor": "analyst",
            },
        ).json()["data"]["persisted_candidates"][0]
        draft = client.post(
            f"/api/projects/{second_project}/contract-governance/contracts",
            json={
                "schema_version": "1",
                "contract_id": "cross-project-contract",
                "snapshot": _contract_snapshot(contract_path, "cross-project-contract"),
                "candidate_ids": [candidate["candidate_id"]],
                "actor": "analyst",
            },
        )
        assert draft.status_code == 400, draft.text
        assert draft.json()["error"]["code"] == "CONTRACT_REFERENCE_INVALID"
