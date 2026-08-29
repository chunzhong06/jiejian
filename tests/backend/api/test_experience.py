# 验证官方 Sample Experience API 只自动化已同意的机械事实并复用正式产品服务。

from __future__ import annotations

from pathlib import Path

from product.backend.core.test_identity import (
    TestIdentityAuthMethod as IdentityAuthMethod,
)
from tests.fixtures.collaboration_golden import InMemorySecretStore
from tests.fixtures.control_plane import TestClient, create_app
from tests.fixtures.runtime_environment import runtime_identity_environment


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SAMPLE_ROOT = _PROJECT_ROOT / "samples" / "web" / "collaboration_space"


def _app(tmp_path: Path, *, sample_root: Path | None = _SAMPLE_ROOT):
    var_dir = tmp_path / "var"
    store = InMemorySecretStore()
    app = create_app(
        var_dir,
        start_worker=False,
        official_sample_root=sample_root,
        secret_store=store,
        environ=runtime_identity_environment(var_dir),
    )
    return app, store


def _start(client: TestClient, mode: str):
    return client.post(
        "/api/experience/official-sample/start",
        json={
            "schema_version": "1",
            "experience_mode": mode,
            "consent": True,
        },
    )


def test_unavailable_installation_keeps_product_alive_and_requires_consent(
    tmp_path: Path,
) -> None:
    app, _ = _app(tmp_path, sample_root=None)
    with TestClient(app) as client:
        status = client.get("/api/experience/official-sample")
        assert status.status_code == 200
        assert status.json()["data"] == {
            "available": False,
            "display_name": "协作空间",
            "unavailable_reason": "未配置官方示例目录",
            "active": False,
            "experience_id": None,
            "experience_mode": None,
            "project_id": None,
            "origin": None,
            "identities_ready": False,
            "authorization_order": None,
            "blob_observation": None,
        }
        assert client.get("/ready").status_code == 200
        rejected = client.post(
            "/api/experience/official-sample/start",
            json={
                "schema_version": "1",
                "experience_mode": "FULL",
                "consent": False,
            },
        )
        assert rejected.status_code == 422


def test_full_experience_creates_formal_project_and_keeps_behavior_mechanical(
    tmp_path: Path,
) -> None:
    app, _ = _app(tmp_path)
    with TestClient(app) as client:
        response = _start(client, "FULL")
        assert response.status_code == 200, response.text
        started = response.json()["data"]
        assert started["active"] is True
        assert started["experience_mode"] == "FULL"
        assert started["origin"].startswith("http://127.0.0.1:")
        assert "source" not in started
        assert "secret" not in response.text.casefold()

        core = app.state.context
        understanding = core.application_understanding.get(started["project_id"])
        assert understanding.confirmed_endpoint == started["origin"]
        assert understanding.source_analysis_authorized is False
        assert core.local_observer_environments.resolve(
            understanding.source_root,
            understanding.confirmed_endpoint,
        ) == str(core.official_samples.active.descriptor_path)
        experience_root = core.official_samples.active.experience_root

        changed = client.post(
            "/api/experience/official-sample/behavior",
            json={
                "schema_version": "1",
                "authorization_order": "AUTHORIZE_BEFORE_ENQUEUE",
                "blob_observation": "AVAILABLE",
            },
        )
        assert changed.status_code == 200, changed.text
        assert (
            changed.json()["data"]["authorization_order"]
            == "AUTHORIZE_BEFORE_ENQUEUE"
        )
        assert changed.json()["data"]["origin"] == started["origin"]
        assert changed.json()["data"]["project_id"] == started["project_id"]

        stopped = client.post("/api/experience/official-sample/stop")
        assert stopped.status_code == 200
        assert stopped.json()["data"]["active"] is False
        assert core.local_observer_environments.resolve(
            understanding.source_root,
            understanding.confirmed_endpoint,
        ) is None
        assert not experience_root.exists()


def test_guided_experience_analyzes_without_deciding_then_prepares_real_identities(
    tmp_path: Path,
) -> None:
    app, store = _app(tmp_path)
    with TestClient(app) as client:
        response = _start(client, "GUIDED")
        assert response.status_code == 200, response.text
        started = response.json()["data"]
        project_id = started["project_id"]
        understanding = app.state.context.application_understanding.get(project_id)
        assert understanding.source_analysis_authorized is True
        assert understanding.analysis_completed_at_us is not None
        assert {
            candidate.canonical_key: candidate.display_name
            for candidate in understanding.role_candidates
        } == {
            "member": "普通成员",
            "project_owner": "项目负责人",
        }
        assert understanding.action_candidates
        assert all(
            candidate.decision.value == "PROPOSED"
            for candidate in (*understanding.role_candidates, *understanding.action_candidates)
        )

        before_confirmation = client.post(
            "/api/experience/official-sample/identities"
        )
        assert before_confirmation.status_code == 400
        assert before_confirmation.json()["error"]["code"] == "STATE_PRECONDITION"

        revision = understanding.revision
        for candidate in understanding.role_candidates:
            decided = client.put(
                f"/api/projects/{project_id}/roles/{candidate.candidate_id}",
                json={
                    "schema_version": "1",
                    "decision": "CONFIRMED",
                    "display_name": candidate.display_name,
                    "revision": revision,
                },
            )
            assert decided.status_code == 200, decided.text
            revision = decided.json()["data"]["revision"]

        prepared = client.post("/api/experience/official-sample/identities")
        assert prepared.status_code == 200, prepared.text
        assert prepared.json()["data"]["identities_ready"] is True
        assert "session-" not in prepared.text
        identities = app.state.context.test_identities.list(project_id)
        assert {item.label for item in identities} == {
            "Alice · 项目负责人",
            "Bob · 普通成员",
        }
        assert all(
            item.auth_method is IdentityAuthMethod.COOKIE_SESSION
            for item in identities
        )
        assert len(store.values) == 2

        repeated = client.post("/api/experience/official-sample/identities")
        assert repeated.status_code == 200
        assert len(app.state.context.test_identities.list(project_id)) == 2
        assert len(store.values) == 2
