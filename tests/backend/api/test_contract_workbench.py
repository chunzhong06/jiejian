from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from product.backend.api import create_app
from product.backend.infra.llm.adapters.base import LLMHttpResponse
from product.backend.workflows.contracts.candidate_generation import ContractCandidateGenerator
from product.backend.workflows.contracts.workbench import ContractWorkbench
from product.backend.infra.storage import StorageUnitOfWork

pytestmark = pytest.mark.database

SAMPLE_CONTRACT = Path("samples/http/fixed/contract.json").resolve()


def _contract_snapshot(contract_id: str, version: int = 1) -> dict:
    snapshot = json.loads(SAMPLE_CONTRACT.read_text(encoding="utf-8"))
    snapshot["contract_id"] = contract_id
    snapshot["version"] = version
    return snapshot


def _output(requirement_id: str) -> str:
    return json.dumps(
        {
            "schema_version": "1",
            "candidates": [
                {
                    "requirement_ids": [requirement_id],
                    "suggestion": {
                        "schema_version": "1",
                        "id": "llm-rule",
                        "kind": "FOREIGN_READ",
                        "required_observations": ["resource_state"],
                        "severity": "high",
                    },
                }
            ],
        }
    )


def _register(client: TestClient, path: Path | None = None) -> str:
    response = client.post(
        "/api/projects",
        json={
            "schema_version": "1",
            "profile_path": str((path or Path("samples/http/fixed/profile.json")).resolve()),
        },
    )
    assert response.status_code == 200
    return response.json()["data"]["project_id"]


def test_contract_workbench_api_full_offline_governance_loop(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        project_id = _register(client)
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
                "snapshot": _contract_snapshot("ownership-contract"),
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
        assert snapshot.json()["data"]["llm_available"] is False

        revision = client.post(
            f"/api/projects/{project_id}/contract-governance/contracts/ownership-contract/revisions",
            json={
                "schema_version": "1",
                "snapshot": _contract_snapshot("ownership-contract", 2),
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
def test_contract_workbench_api_llm_offline_and_injected_provider(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        project_id = _register(client)
        requirement = client.post(
            f"/api/projects/{project_id}/contract-governance/requirements",
            json={
                "schema_version": "1",
                "text": "suggestion id=foreign-read kind=FOREIGN_READ observations=resource_state severity=high",
                "security_tags": [],
                "actor": "analyst",
            },
        ).json()["data"]
        body = {"schema_version": "1", "requirement_ids": [requirement["requirement_id"]], "actor": "analyst"}
        unavailable = client.post(
            f"/api/projects/{project_id}/contract-governance/candidates/llm",
            json=body,
        )
        assert unavailable.status_code == 503
        assert unavailable.json()["error"]["code"] == "LLM_PROVIDER_UNAVAILABLE"

        context = app.state.context
        context.llm_candidates = ContractCandidateGenerator(
            context.uow_factory,
            provider=lambda _: _output(requirement["requirement_id"]),
            provider_id="test-provider",
            model_id="test-model",
        )
        context.contract_workbench = ContractWorkbench(
            context.uow_factory,
            context.projects,
            context.contracts,
            context.contract_analysis,
            context.llm_candidates,
        )
        generated = client.post(
            f"/api/projects/{project_id}/contract-governance/candidates/llm",
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
            "/api/llm/profiles",
            json={"schema_version": "1", "profile_name": "candidate-profile", "provider": "openai", "model": "gpt-test", "secret": "value-c"},
        )
        assert profile.status_code == 201
        project_id = _register(client)
        requirement = client.post(
            f"/api/projects/{project_id}/contract-governance/requirements",
            json={"schema_version": "1", "text": "suggestion id=foreign-read kind=FOREIGN_READ observations=resource_state severity=high", "security_tags": [], "actor": "analyst"},
        ).json()["data"]
        transport.requirement_id = requirement["requirement_id"]
        response = client.post(
            f"/api/projects/{project_id}/contract-governance/candidates/llm",
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
            f"/api/projects/{project_id}/contract-governance/requirements",
            json={"schema_version": "1", "text": "suggestion id=foreign-read kind=FOREIGN_READ observations=resource_state severity=high", "security_tags": [], "actor": "analyst"},
        ).json()["data"]
        client.post(
            "/api/llm/profiles",
            json={"schema_version": "1", "profile_name": "unconfigured", "provider": "openai", "model": "gpt-test", "secret_ref": "env:MISSING"},
        )
        response = client.post(
            f"/api/projects/{project_id}/contract-governance/candidates/llm",
            json={"schema_version": "1", "requirement_ids": [requirement["requirement_id"]], "actor": "analyst", "profile_name": "unconfigured"},
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "LLM_SECRET_UNAVAILABLE"
        assert transport.calls == 0


def test_contract_workbench_api_rejects_cross_project_requirement(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        first_project = _register(client)
        second_project = _register(client, Path("samples/http/vulnerable/profile.json"))
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
                "snapshot": _contract_snapshot("cross-project-contract"),
                "candidate_ids": [candidate["candidate_id"]],
                "actor": "analyst",
            },
        )
        assert draft.status_code == 400, draft.text
        assert draft.json()["error"]["code"] == "CONTRACT_REFERENCE_INVALID"
