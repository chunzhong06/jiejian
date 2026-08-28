# 验证 Recording API 的确认动作、完成时间与已准备测试身份接线。

from __future__ import annotations
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from fastapi import FastAPI
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
from product.backend.api.routers.recordings import build_recordings_router
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
class RecordingFakeSecretStore:
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


def test_recording_finalize_api_supplies_runtime_timestamp(tmp_path: Path) -> None:
    calls: list[tuple[str, Path, int]] = []

    class RecordingLifecycle:
        def finalize(self, recording_id: str, *, var_dir: Path, now_us: int):
            calls.append((recording_id, var_dir, now_us))
            return SimpleNamespace(
                model_dump=lambda **_kwargs: {"recording_id": recording_id}
            )

    @contextmanager
    def uow_factory():
        yield SimpleNamespace(
            jobs=SimpleNamespace(get_by_recording=lambda _recording_id: None)
        )

    var_dir = tmp_path / "var"
    app = FastAPI()
    app.include_router(
        build_recordings_router(
            SimpleNamespace(
                recording_lifecycle=RecordingLifecycle(),
                uow_factory=uow_factory,
                var_dir=var_dir,
            )
        )
    )

    with RawTestClient(app) as client:
        response = client.post(
            "/api/recordings/recording-finalize/finalize",
            json={"schema_version": "1"},
        )

    assert response.status_code == 200, response.text
    assert response.json()["data"] == {"recording_id": "recording-finalize"}
    assert len(calls) == 1
    recording_id, supplied_var_dir, now_us = calls[0]
    assert recording_id == "recording-finalize"
    assert supplied_var_dir == var_dir
    assert isinstance(now_us, int) and now_us > 0

@pytest.mark.essential
def test_recording_api_uses_confirmed_action_and_prepared_test_identity(tmp_path: Path) -> None:
    project_id = "recording-api-project"
    role_id = candidate_id("role", "owner")
    action_id = candidate_id("action", "modify-resource")
    store = RecordingFakeSecretStore()
    app = create_app(
        tmp_path / "var",
        start_worker=False,
        secret_store=store,
        environ={},
    )
    with app.state.context.uow_factory() as work:
        work.projects.add(
            ProjectRecord(
                project_id=project_id,
                name="录制 API",
                status=ProjectStatus.DRAFT,
                created_at_us=1,
                updated_at_us=1,
            )
        )
        work.application_understanding.add(
            ApplicationUnderstanding(
                project_id=project_id,
                source_root="D:/recording-api",
                confirmed_endpoint="http://127.0.0.1:8865",
                endpoint_source_fingerprint="a" * 64,
                endpoint_confirmed_at_us=2,
                endpoint_last_checked_at_us=2,
                endpoint_reachable=True,
                role_candidates=(
                    RoleCandidate(
                        candidate_id=role_id,
                        canonical_key="owner",
                        display_name="所有者",
                        confidence=CandidateConfidence.HIGH,
                        decision=CandidateDecision.CONFIRMED,
                        origin=CandidateOrigin.MANUAL,
                    ),
                ),
                action_candidates=(
                    ActionCandidate(
                        candidate_id=action_id,
                        canonical_key="modify-resource",
                        display_name="修改资源",
                        confidence=CandidateConfidence.HIGH,
                        decision=CandidateDecision.CONFIRMED,
                        origin=CandidateOrigin.MANUAL,
                    ),
                ),
                revision=3,
                created_at_us=1,
                updated_at_us=2,
            )
        )
        work.commit()
    identity = app.state.context.test_identities.create(
        project_id,
        role_candidate_id=role_id,
        label="所有者账号",
    )
    secret_ref = credential_ref("test-identity", project_id, identity.identity_id, "cookie-00")
    store.write(secret_ref, "recording-api-secret")
    app.state.context.test_identities.save_prepared_state(
        identity.identity_id,
        PreparedLoginState(
            auth_method=TestIdentityAuthMethod.COOKIE_SESSION,
            cookies=(
                TestIdentityCookie(
                    name="session",
                    domain="127.0.0.1",
                    path="/",
                    secure=False,
                    http_only=True,
                    same_site="LAX",
                    value_secret_ref=secret_ref,
                ),
            ),
            prepared_at_us=identity.updated_at_us + 1,
        ),
    )
    with TestClient(app) as client:
        setup = client.get(f"/api/projects/{project_id}/recordings/setup")
        assert setup.status_code == 200, setup.text
        setup_data = setup.json()["data"]
        assert setup_data["action_options"] == [
            {
                "action_candidate_id": action_id,
                "display_name": "修改资源",
                "risk_hint": "UNKNOWN",
            }
        ]
        assert setup_data["test_identity_options"][0]["test_identity_id"] == identity.identity_id
        assert "secret_ref" not in json.dumps(setup.json()["data"])
        schema = client.get("/openapi.json").json()["components"]["schemas"][
            "RecordingCreateRequest"
        ]["properties"]
        assert set(schema) == {
            "schema_version",
            "action_candidate_id",
            "test_identity_id",
            "duration_seconds",
            "idempotency_key",
        }
        valid = client.post(
            f"/api/projects/{project_id}/recordings",
            json={
                "schema_version": "1",
                "action_candidate_id": action_id,
                "test_identity_id": identity.identity_id,
                "duration_seconds": 60,
                "idempotency_key": "single-owner",
            },
        )
        assert valid.status_code == 202, valid.text
        data = valid.json()["data"]
        assert data["action"]["action_candidate_id"] == action_id
        assert data["test_identity"]["test_identity_id"] == identity.identity_id
        assert "recording-api-secret" not in valid.text
        request = RecordingRequestStore(tmp_path / "var").load(
            data["job"]["job_id"], expected_hash=data["job"]["request_hash"]
        )
        assert request.headless is False
        assert request.action_candidate_id == action_id
        assert tuple(item.test_identity_id for item in request.sessions) == (identity.identity_id,)
        detail = client.get(f"/api/recordings/{data['recording']['recording_id']}")
        assert detail.status_code == 200
        detail_data = detail.json()["data"]
        assert detail_data["capture_phase"] == "PREPARING_BROWSER"
        assert detail_data["action"]["display_name"] == "修改资源"
        assert detail_data["test_identity"]["label"] == "所有者账号"
        assert client.post(f"/api/jobs/{data['job']['job_id']}/cancel").status_code == 200
        cancelled = client.get(f"/api/recordings/{data['recording']['recording_id']}")
        assert cancelled.json()["data"]["recording"]["state"] == "CANCELLED"
        assert cancelled.json()["data"]["capture_phase"] == "FINISHED"
        assert cancelled.json()["data"]["draft"] is None
        app.state.context.test_identities.delete(identity.identity_id)
        historical = client.get(
            f"/api/recordings/{data['recording']['recording_id']}"
        )
        assert historical.status_code == 200
        assert historical.json()["data"]["test_identity"] == {
            "test_identity_id": identity.identity_id,
            "label": "已删除的测试账号",
            "role_display_name": "已删除",
        }
        rejected = client.post(
            f"/api/projects/{project_id}/recordings",
            json={
                "schema_version": "1",
                "profile_id": "legacy-profile",
                "identities": ["owner"],
                "headless": True,
                "idempotency_key": "unsupported-fields",
            },
        )
        assert rejected.status_code == 422, rejected.text
