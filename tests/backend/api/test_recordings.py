# 验证 Recording API 的确认动作、完成时间与已准备测试身份接线。

from __future__ import annotations
from contextlib import contextmanager
import json
from pathlib import Path
import time
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient as RawTestClient
import pytest
from product.backend.infra.runtime.jobs.models import RequestCancellation
from product.backend.infra.recording.request_store import RecordingRequestStore
from product.backend.api.routers.recordings import build_recordings_router
from tests.fixtures.control_plane import TestClient, create_app
from tests.fixtures.action_preparation import build_preparation_harness, MemorySecretStore

pytestmark = [pytest.mark.database, pytest.mark.process, pytest.mark.slow]
def test_recording_finalize_api_supplies_runtime_timestamp(tmp_path: Path) -> None:
    calls: list[tuple[str, Path, int]] = []
    metadata_calls = []

    def frozen_action(action_id, revision):
        metadata_calls.append((action_id, revision))
        return SimpleNamespace(action_id=action_id, revision=revision, display_name="录制时的动作")

    class RecordingLifecycle:
        def finalize(self, recording_id: str, *, var_dir: Path, now_us: int):
            calls.append((recording_id, var_dir, now_us))
            return SimpleNamespace(
                recording=SimpleNamespace(business_action_id="bac_" + "1" * 32, action_revision=1, test_identity_id="tid_" + "1" * 32),
                model_dump=lambda **_kwargs: {"recording_id": recording_id}
            )

    @contextmanager
    def uow_factory():
        yield SimpleNamespace(
            jobs=SimpleNamespace(get_by_recording=lambda _recording_id: None),
            business_boundaries=SimpleNamespace(action_revision=frozen_action)
        )

    var_dir = tmp_path / "var"
    app = FastAPI()
    app.include_router(
        build_recordings_router(
            SimpleNamespace(
                recording_lifecycle=RecordingLifecycle(),
                test_identities=SimpleNamespace(get=lambda identity_id: SimpleNamespace(identity_id=identity_id, label="账号", actor_display_name="成员")),
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
    assert response.json()["data"]["recording_id"] == "recording-finalize"
    assert len(calls) == 1
    recording_id, supplied_var_dir, now_us = calls[0]
    assert recording_id == "recording-finalize"
    assert supplied_var_dir == var_dir
    assert isinstance(now_us, int) and now_us > 0
    assert metadata_calls == [("bac_" + "1" * 32, 1)]
    assert response.json()["data"]["action"] == {
        "business_action_id": "bac_" + "1" * 32,
        "action_revision": 1, "display_name": "录制时的动作",
    }

@pytest.mark.essential
def test_recording_api_uses_confirmed_action_and_prepared_test_identity(tmp_path: Path) -> None:
    store = MemorySecretStore()
    app = create_app(tmp_path / "var", start_worker=False, secret_store=store, environ={})
    harness = build_preparation_harness(tmp_path, core=app.state.context)
    app.include_router(build_recordings_router(app.state.context))
    project_id = harness.project_id
    action_id = harness.action.action_id
    identity = harness.identities[0]
    with TestClient(app) as client:
        setup = client.get(f"/api/projects/{project_id}/recordings/setup")
        assert setup.status_code == 200, setup.text
        setup_data = setup.json()["data"]
        assert setup_data["action_options"] == [
            {
                "business_action_id": action_id,
                "action_revision": 1,
                "display_name": "更新文档",
            }
        ]
        assert setup_data["test_identity_options"][0]["test_identity_id"] == identity.identity_id
        assert "secret_ref" not in json.dumps(setup.json()["data"])
        schema = client.get("/openapi.json").json()["components"]["schemas"][
            "RecordingCreateRequest"
        ]["properties"]
        assert set(schema) == {
            "schema_version",
            "business_action_id",
            "action_revision",
            "test_identity_id",
            "duration_seconds",
            "idempotency_key",
            "purpose",
            "parent_recording_id",
            "effect_id",
        }
        valid = client.post(
            f"/api/projects/{project_id}/recordings",
            json={
                "schema_version": "2",
                "business_action_id": action_id,
                "action_revision": 1,
                "test_identity_id": identity.identity_id,
                "duration_seconds": 60,
                "idempotency_key": "single-owner",
            },
        )
        assert valid.status_code == 202, valid.text
        data = valid.json()["data"]
        assert data["action"]["business_action_id"] == action_id
        assert data["test_identity"]["test_identity_id"] == identity.identity_id
        assert "fixture-secret" not in valid.text
        request = RecordingRequestStore(tmp_path / "var").load(
            data["job"]["job_id"], expected_hash=data["job"]["request_hash"]
        )
        listing = client.get(f"/api/projects/{project_id}/recordings")
        assert listing.status_code == 200
        assert len(listing.json()["data"]) == 1
        assert "browser_events" not in listing.text
        assert "preparation_source_fingerprint" not in listing.text
        for method in (client.get, client.put):
            assert method(f"/api/projects/{project_id}/recordings/safety-setup").status_code == 404
        assert request.headless is False
        assert request.business_action_id == action_id
        assert tuple(item.test_identity_id for item in request.sessions) == (identity.identity_id,)
        detail = client.get(f"/api/recordings/{data['recording']['recording_id']}")
        assert detail.status_code == 200
        detail_data = detail.json()["data"]
        assert detail_data["capture_phase"] == "PREPARING_BROWSER"
        assert detail_data["action"]["display_name"] == "更新文档"
        assert detail_data["test_identity"]["label"] == "测试账号 1"
        # 当前测试只接录制路由；取消走同一正式 Job 服务，再由录制 GET 投影终态。
        cancelled_job = app.state.context.job_queue.request_cancellation(RequestCancellation(
            job_id=data["job"]["job_id"], now_us=time.time_ns() // 1_000,
        ))
        assert cancelled_job is not None
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
            "actor_display_name": "已删除",
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
        legacy_candidate = client.post(f"/api/projects/{project_id}/recordings", json={
            "schema_version": "2", "action_candidate_id": "action_" + "1" * 32,
            "test_identity_id": identity.identity_id, "idempotency_key": "old-candidate",
        })
        assert legacy_candidate.status_code == 422
