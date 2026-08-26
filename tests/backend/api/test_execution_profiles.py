# 验证 Execution Profile API 的摘要、绑定与重新注册边界。

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
PROFILE_SOURCE = Path("samples/web/fixed/profile.json").resolve()
CONTRACT_SOURCE = Path("samples/web/fixed/contract.json").resolve()

def _write_profile(tmp_path: Path, *, port: int | None = None) -> Path:
    profile = parse_web_execution_profile(PROFILE_SOURCE.read_bytes())
    if port is not None:
        scope = profile.target.scope.model_copy(
            update={
                "base_url": f"http://127.0.0.1:{port}",
                "allowed_origins": (f"http://127.0.0.1:{port}",),
                "allowed_ports": (port,),
            }
        )
        profile = profile.model_copy(update={"target": profile.target.model_copy(update={"scope": scope})})
    path = tmp_path / "profile.json"
    path.write_bytes(canonical_web_execution_profile_json_bytes(profile))
    return path

def _register_project(client: TestClient, profile_path: Path) -> dict[str, object]:
    response = client.post(
        "/api/projects",
        json={"schema_version": "1", "profile_path": str(profile_path)},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]

def _activate_contract(app, project_id: str) -> PermissionContract:
    contract = PermissionContract.model_validate_json(CONTRACT_SOURCE.read_text(encoding="utf-8"), strict=True)
    draft = app.state.context.contracts.create_draft(
        project_id,
        contract.contract_id,
        snapshot=contract,
        actor="test",
    )
    review = app.state.context.contracts.submit_review(
        project_id, draft.contract_id, draft.version, actor="reviewer"
    )
    active = app.state.context.contracts.activate_review(
        project_id, review.contract_id, review.version, actor="approver"
    )
    return active.snapshot

def _register_active_profile(app, client: TestClient, profile_path: Path) -> tuple[dict[str, object], PermissionContract, dict[str, object]]:
    project = _register_project(client, profile_path)
    contract = _activate_contract(app, str(project["project_id"]))
    response = client.post(
        "/api/execution-profiles",
        json={"schema_version": "1", "profile_path": str(profile_path)},
    )
    assert response.status_code == 201, response.text
    return project, contract, response.json()["data"]

def test_execution_profile_summary_exposes_only_user_confirmable_workflow_and_effect_facts(
    tmp_path: Path,
) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    profile_path = _write_profile(tmp_path)
    with TestClient(app) as client:
        project, _, profile = _register_active_profile(app, client, profile_path)
        response = client.get(
            f"/api/projects/{project['project_id']}/execution-profiles/{profile['profile_id']}/summary"
        )

    assert response.status_code == 200, response.text
    summary = response.json()["data"]
    assert "schema_version" not in summary
    assert summary["workflows"]
    assert all(item["target_step"]["method"] for item in summary["workflows"])
    assert summary["effect_bindings"]
    assert all(item["required_channels"] for item in summary["effect_bindings"])
    serialized = json.dumps(summary).lower()
    assert "secret_ref" not in serialized
    assert "authorization" not in serialized
    assert "cookie" not in serialized

def test_profile_reregistration_preserves_explicit_active_contract(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    profile_path = _write_profile(tmp_path)
    with TestClient(app) as client:
        project, active, _ = _register_active_profile(app, client, profile_path)
        response = client.post(
            "/api/projects",
            json={"schema_version": "1", "profile_path": str(profile_path)},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["governed_contract_id"] == active.contract_id
        assert data["governed_contract_version"] == active.version
