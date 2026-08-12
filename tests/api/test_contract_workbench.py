from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jiejian.api import create_app
from jiejian.contracts.llm.adapters.base import LLMHttpResponse
from jiejian.contracts.llm.service import LLMCandidateGenerationService
from jiejian.contracts.workbench import ContractWorkbenchService
from jiejian.storage import StorageUnitOfWork

pytestmark = pytest.mark.database


def _output(requirement_id: str) -> str:
    return json.dumps(
        {
            "schema_version": "1",
            "candidates": [
                {
                    "requirement_ids": [requirement_id],
                    "rule": {
                        "schema_version": "1",
                        "id": "llm-rule",
                        "kind": "foreign_read",
                        "required_observers": ["http"],
                        "severity": "high",
                    },
                }
            ],
        }
    )


def _register(client: TestClient, path: Path | None = None) -> str:
    response = client.post(
        "/api/v1/projects",
        json={
            "schema_version": "1",
            "path": str((path or Path("samples/fixed_apps/ownership/project.yaml")).resolve()),
        },
    )
    assert response.status_code == 200
    return response.json()["data"]["project_id"]


def test_contract_workbench_api_full_offline_governance_loop(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        project_id = _register(client)
        malformed = client.post(
            f"/api/v1/projects/{project_id}/contract-governance/requirements",
            json={"schema_version": "1", "text": "任意自然语言", "security_tags": [], "actor": "analyst"},
        )
        malformed_requirement = malformed.json()["data"]
        blocked = client.post(
            f"/api/v1/projects/{project_id}/contract-governance/candidates/derive",
            json={
                "schema_version": "1",
                "requirement_ids": [malformed_requirement["requirement_id"]],
                "include_flow": False,
                "actor": "analyst",
            },
        )
        assert blocked.status_code == 200
        assert blocked.json()["data"]["persisted_candidates"] == []
        assert any(issue["severity"] == "BLOCKING" for issue in blocked.json()["data"]["batches"][0]["issues"])

        requirement = client.post(
            f"/api/v1/projects/{project_id}/contract-governance/requirements",
            json={
                "schema_version": "1",
                "text": "rule id=foreign-read kind=foreign_read observers=http severity=high\nrule id=unauthorized-side-effect kind=unauthorized_side_effect observers=http,owner_api severity=critical\nrule id=privileged-field kind=privileged_field observers=http,owner_api severity=critical",
                "security_tags": ["ownership"],
                "actor": "analyst",
            },
        ).json()["data"]
        derive_body = {
            "schema_version": "1",
            "requirement_ids": [requirement["requirement_id"]],
            "include_flow": False,
            "actor": "analyst",
        }
        first = client.post(
            f"/api/v1/projects/{project_id}/contract-governance/candidates/derive",
            json=derive_body,
        )
        second = client.post(
            f"/api/v1/projects/{project_id}/contract-governance/candidates/derive",
            json=derive_body,
        )
        assert first.status_code == second.status_code == 200
        candidates = first.json()["data"]["persisted_candidates"]
        assert [item["candidate_id"] for item in second.json()["data"]["persisted_candidates"]] == [item["candidate_id"] for item in candidates]

        draft = client.post(
            f"/api/v1/projects/{project_id}/contract-governance/contracts",
            json={
                "schema_version": "1",
                "contract_id": "workbench-contract",
                "candidate_ids": [item["candidate_id"] for item in candidates],
                "actor": "analyst",
            },
        ).json()["data"]
        assessment = client.get(
            f"/api/v1/projects/{project_id}/contract-governance/contracts/workbench-contract/versions/1/assessment"
        )
        assert assessment.status_code == 200
        assert assessment.json()["data"]["eligible"] is True
        review = client.post(
            f"/api/v1/projects/{project_id}/contract-governance/contracts/workbench-contract/versions/{draft['version']}/submit",
            json={"schema_version": "1", "actor": "reviewer"},
        ).json()["data"]
        active = client.post(
            f"/api/v1/projects/{project_id}/contract-governance/contracts/workbench-contract/versions/{review['version']}/activate",
            json={"schema_version": "1", "actor": "approver"},
        ).json()["data"]
        snapshot = client.get(f"/api/v1/projects/{project_id}/contract-governance")
        assert snapshot.status_code == 200
        assert snapshot.json()["data"]["project"]["governed_contract_id"] == active["contract_id"]
        assert snapshot.json()["data"]["llm_available"] is False

        revision = client.post(
            f"/api/v1/projects/{project_id}/contract-governance/contracts/workbench-contract/revisions",
            json={
                "schema_version": "1",
                "candidate_ids": [item["candidate_id"] for item in candidates],
                "actor": "analyst",
            },
        ).json()["data"]
        diff = client.get(
            f"/api/v1/projects/{project_id}/contract-governance/contracts/workbench-contract/versions/{revision['version']}/diff",
            params={"from_version": 1},
        )
        assert diff.status_code == 200
        drift = client.get(
            f"/api/v1/projects/{project_id}/contract-governance/contracts/workbench-contract/versions/{active['version']}/drift"
        )
        assert drift.status_code == 200
        run = client.post(
            f"/api/v1/projects/{project_id}/runs",
            json={"schema_version": "1", "idempotency_key": "workbench-history"},
        )
        assert run.status_code == 202
        history = client.get(f"/api/v1/runs/{run.json()['data']['run']['run_id']}/contract")
        assert history.status_code == 200
        assert history.json()["data"]["source"] == "EXECUTION_REQUEST"


def test_contract_workbench_api_llm_offline_and_injected_provider(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        project_id = _register(client)
        requirement = client.post(
            f"/api/v1/projects/{project_id}/contract-governance/requirements",
            json={
                "schema_version": "1",
                "text": "rule id=foreign-read kind=foreign_read observers=http severity=high",
                "security_tags": [],
                "actor": "analyst",
            },
        ).json()["data"]
        body = {"schema_version": "1", "requirement_ids": [requirement["requirement_id"]], "actor": "analyst"}
        unavailable = client.post(
            f"/api/v1/projects/{project_id}/contract-governance/candidates/llm",
            json=body,
        )
        assert unavailable.status_code == 503
        assert unavailable.json()["error"]["code"] == "LLM_PROVIDER_UNAVAILABLE"

        context = app.state.context
        context.llm_candidates = LLMCandidateGenerationService(
            context.uow_factory,
            provider=lambda _: _output(requirement["requirement_id"]),
            provider_id="test-provider",
            model_id="test-model",
        )
        context.contract_workbench = ContractWorkbenchService(
            context.uow_factory,
            context.projects,
            context.contracts,
            context.contract_analysis,
            context.llm_candidates,
        )
        generated = client.post(
            f"/api/v1/projects/{project_id}/contract-governance/candidates/llm",
            json=body,
        )
        assert generated.status_code == 200
        candidate = generated.json()["data"]["candidates"][0]
        assert candidate["source"]["source_type"] == "llm"
        assert candidate["llm_metadata"]["provider_id"] == "test-provider"
        with context.uow_factory() as work:
            stored = work.contract_candidates.get(candidate["candidate_id"])
        assert stored is not None and stored.llm_metadata is not None


def test_contract_workbench_api_generates_with_explicit_profile_and_persists_provenance(
    tmp_path: Path,
) -> None:
    class SecretStore:
        def __init__(self) -> None:
            self.values: dict[str, str] = {}

        def write(self, secret_ref: str, secret: str) -> None:
            self.values[secret_ref] = secret

        def read(self, secret_ref: str) -> str | None:
            return self.values.get(secret_ref)

        def delete(self, secret_ref: str) -> None:
            self.values.pop(secret_ref, None)

        def configured(self, secret_ref: str | None) -> bool:
            return secret_ref is not None and secret_ref in self.values

    class Transport:
        def __init__(self) -> None:
            self.calls = 0
            self.requests = []
            self.requirement_id = ""

        def send(self, request):
            self.calls += 1
            self.requests.append(request)
            return LLMHttpResponse(
                200,
                json.dumps({"choices": [{"message": {"content": _output(self.requirement_id)}}]}).encode(),
            )

    store = SecretStore()
    transport = Transport()
    app = create_app(
        tmp_path / "var",
        start_worker=False,
        llm_transport=transport,
        llm_secret_store=store,
        clock_us=lambda: 1,
    )
    with TestClient(app) as client:
        profile = client.post(
            "/api/v1/llm/profiles",
            json={"schema_version": "1", "profile_name": "candidate-profile", "provider": "openai", "model": "gpt-test", "secret": "value-c"},
        )
        assert profile.status_code == 201
        project_id = _register(client)
        requirement = client.post(
            f"/api/v1/projects/{project_id}/contract-governance/requirements",
            json={"schema_version": "1", "text": "rule id=foreign-read kind=foreign_read observers=http severity=high", "security_tags": [], "actor": "analyst"},
        ).json()["data"]
        transport.requirement_id = requirement["requirement_id"]
        response = client.post(
            f"/api/v1/projects/{project_id}/contract-governance/candidates/llm",
            json={"schema_version": "1", "requirement_ids": [requirement["requirement_id"]], "actor": "analyst", "profile_name": "candidate-profile"},
        )
        assert response.status_code == 200, response.text
        candidate = response.json()["data"]["candidates"][0]
        assert candidate["llm_metadata"]["provenance_schema_version"] == "2"
        assert candidate["llm_metadata"]["profile_name"] == "candidate-profile"
        assert "value-c" not in response.text
        assert transport.calls == 1
        assert "value-c" not in transport.requests[0].body.decode()


def test_contract_workbench_api_unconfigured_profile_sends_no_request(tmp_path: Path) -> None:
    class Store:
        def write(self, secret_ref: str, secret: str) -> None:
            pass

        def read(self, secret_ref: str) -> str | None:
            return None

        def delete(self, secret_ref: str) -> None:
            pass

        def configured(self, secret_ref: str | None) -> bool:
            return False

    class Transport:
        calls = 0

        def send(self, request):
            self.calls += 1
            raise AssertionError("unconfigured profile must not send")

    transport = Transport()
    app = create_app(
        tmp_path / "var",
        start_worker=False,
        llm_transport=transport,
        llm_secret_store=Store(),
    )
    with TestClient(app) as client:
        project_id = _register(client)
        requirement = client.post(
            f"/api/v1/projects/{project_id}/contract-governance/requirements",
            json={"schema_version": "1", "text": "rule id=foreign-read kind=foreign_read observers=http severity=high", "security_tags": [], "actor": "analyst"},
        ).json()["data"]
        client.post(
            "/api/v1/llm/profiles",
            json={"schema_version": "1", "profile_name": "unconfigured", "provider": "openai", "model": "gpt-test", "secret_ref": "env:MISSING"},
        )
        response = client.post(
            f"/api/v1/projects/{project_id}/contract-governance/candidates/llm",
            json={"schema_version": "1", "requirement_ids": [requirement["requirement_id"]], "actor": "analyst", "profile_name": "unconfigured"},
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "LLM_SECRET_UNAVAILABLE"
        assert transport.calls == 0


def test_contract_workbench_api_rejects_cross_project_requirement(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        first_project = _register(client)
        second_project = _register(client, Path("samples/vulnerable_apps/ownership/project.yaml"))
        requirement = client.post(
            f"/api/v1/projects/{first_project}/contract-governance/requirements",
            json={
                "schema_version": "1",
                "text": "rule id=foreign-read kind=foreign_read observers=http severity=high",
                "security_tags": [],
                "actor": "analyst",
            },
        ).json()["data"]
        response = client.post(
            f"/api/v1/projects/{second_project}/contract-governance/candidates/derive",
            json={
                "schema_version": "1",
                "requirement_ids": [requirement["requirement_id"]],
                "include_flow": False,
                "actor": "analyst",
            },
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "CONTRACT_REFERENCE_INVALID"

        candidate = client.post(
            f"/api/v1/projects/{first_project}/contract-governance/candidates/derive",
            json={
                "schema_version": "1",
                "requirement_ids": [requirement["requirement_id"]],
                "include_flow": False,
                "actor": "analyst",
            },
        ).json()["data"]["persisted_candidates"][0]
        draft = client.post(
            f"/api/v1/projects/{second_project}/contract-governance/contracts",
            json={
                "schema_version": "1",
                "contract_id": "cross-project-contract",
                "candidate_ids": [candidate["candidate_id"]],
                "actor": "analyst",
            },
        )
        assert draft.status_code == 400
        assert draft.json()["error"]["code"] == "CONTRACT_REFERENCE_INVALID"


def test_contract_workbench_api_flow_only_and_strict_surface(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        project_id = _register(client)
        body = {
            "schema_version": "1",
            "requirement_ids": [],
            "include_flow": True,
            "actor": "analyst",
        }
        first = client.post(
            f"/api/v1/projects/{project_id}/contract-governance/candidates/derive",
            json=body,
        )
        second = client.post(
            f"/api/v1/projects/{project_id}/contract-governance/candidates/derive",
            json=body,
        )
        assert first.status_code == second.status_code == 200
        first_candidates = first.json()["data"]["persisted_candidates"]
        assert first_candidates
        assert {item["source"]["source_type"] for item in first_candidates} == {"recording_flow"}
        assert [item["candidate_id"] for item in second.json()["data"]["persisted_candidates"]] == [
            item["candidate_id"] for item in first_candidates
        ]

        invalid = client.post(
            f"/api/v1/projects/{project_id}/contract-governance/candidates/derive",
            json={"schema_version": "1", "requirement_ids": [], "include_flow": False, "actor": "analyst"},
        )
        assert invalid.status_code == 422

        extra = client.post(
            f"/api/v1/projects/{project_id}/contract-governance/requirements",
            json={
                "schema_version": "1",
                "text": "rule id=foreign-read kind=foreign_read observers=http severity=high",
                "security_tags": [],
                "actor": "analyst",
                "path": "secret/routes.py",
                "url": "https://example.invalid",
                "secret": "Bearer hidden",
                "provider_id": "provider",
                "model_id": "model",
            },
        )
        assert extra.status_code == 422

        openapi = client.get("/openapi.json").json()
        for name in ("RequirementCreateRequest", "CandidateDeriveRequest", "LLMCandidateRequest"):
            properties = openapi["components"]["schemas"][name]["properties"]
            assert not {"path", "url", "secret", "provider_id", "model_id"}.intersection(properties)
