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
from unittest.mock import Mock
import hashlib
from uuid import uuid4
from sqlalchemy import event
from product.backend.core.lifecycle import JobState
from product.backend.core.recording import RecordingPurpose, RecordingState
from product.backend.infra.storage import FlowDraftRevisionRecord
from product.backend.infra.storage.execution.jobs import JobRecord
from product.protocols.flow_draft import canonical_flow_draft_json_bytes
from product.backend.infra.runtime.jobs.models import RequestCancellation
from product.backend.infra.recording.request_store import RecordingRequestStore
from product.backend.api.routers.recordings import build_recordings_router
from tests.fixtures.control_plane import TestClient, create_app
from tests.fixtures.action_preparation import add_recording, build_preparation_harness, MemorySecretStore
from tests.fixtures.control_plane import TEST_CONTROL_ORIGIN

pytestmark = [pytest.mark.database, pytest.mark.process, pytest.mark.slow]


@pytest.fixture
def review_context(tmp_path):
    app = create_app(tmp_path / "var", start_worker=False, secret_store=MemorySecretStore(), environ={})
    h = build_preparation_harness(tmp_path, core=app.state.context)
    target = add_recording(h)
    h.core.recording_lifecycle.finalize(target.recording_id, var_dir=h.var_dir, now_us=100)
    yield app, h, target
    h.close()


def _supplement(h, target, purpose, count):
    recording = add_recording(h, purpose=purpose, parent_recording_id=target.recording_id,
        effect_id=h.effect_id if purpose is RecordingPurpose.OBSERVATION else None,
        step_count=max(1, count), method=("POST" if purpose is RecordingPurpose.OBSERVATION else "GET") if count == 0 else None)
    # RECOVERY 两条相同请求会被确定性去重；用不同普通查询值构造真实的两个候选。
    with h.core.uow_factory() as work:
        old = work.flow_drafts.latest(recording.recording_id)
        steps = tuple(step.model_copy(update={"name": " " if i == 0 else "恢复业务状态",
            "path": f"/docs/doc-123?variant={i}"}) for i, step in enumerate(old.draft.steps))
        events = tuple(item.model_copy(update={"url": f"http://127.0.0.1:8765/docs/doc-123?variant={(item.sequence - 1) // 2}"})
            for item in recording.browser_events)
        work.recordings.replace(recording.model_copy(update={"browser_events": events}))
        draft = old.draft.model_copy(update={"revision": 2, "steps": steps})
        work.flow_drafts.add(FlowDraftRevisionRecord(recording_id=recording.recording_id,
            revision=2, flow_id=recording.flow_id, draft=draft,
            draft_sha256=hashlib.sha256(canonical_flow_draft_json_bytes(draft)).hexdigest(), created_at_us=4))
        work.commit()
    return recording


@pytest.mark.parametrize("purpose", [RecordingPurpose.OBSERVATION, RecordingPurpose.RECOVERY])
@pytest.mark.parametrize("count", [0, 1, 2])
def test_supplement_choices_are_bounded_readonly_and_selectable(review_context, purpose, count):
    app, h, target = review_context
    recording = _supplement(h, target, purpose, count)
    before = h.core.preparation.get(h.project_id)
    statements = []
    def listener(connection, cursor, statement, parameters, context, many):
        statements.append(statement)
    with TestClient(app) as client:
        event.listen(h.core.engine, "before_cursor_execute", listener)
        response = client.get(f"/api/recordings/{recording.recording_id}")
        event.remove(h.core.engine, "before_cursor_execute", listener)
        assert response.status_code == 200, response.text
        choices = response.json()["data"]["supplement_choices"]
        assert len(choices) == count
        assert all(set(item) == {"step_id", "label"} and 0 < len(item["label"]) <= 160 for item in choices)
        encoded = json.dumps(choices, ensure_ascii=False)
        assert all(value not in encoded for value in ("request_template", "candidate_id", "doc-123", "variant", "fixture-secret", "http"))
        assert statements and all(sql.lstrip().upper().startswith(("SELECT", "PRAGMA")) for sql in statements)
        assert h.core.preparation.get(h.project_id) == before
        if choices:
            assert choices[0]["label"] == ("结果证明 1" if purpose is RecordingPurpose.OBSERVATION else "恢复方式 1")
            selected = choices[-1]["step_id"]
            result = client.post(f"/api/recordings/{recording.recording_id}/review", json={"schema_version": "1",
                "command": {"schema_version": "1", "operation": "CONFIRM_TARGET_STEP", "step_id": selected}})
            assert result.status_code == 200, result.text
            result = client.post(f"/api/recordings/{recording.recording_id}/finalize", json={"schema_version": "1"})
            assert result.status_code == 200, result.text
            with h.core.uow_factory() as work:
                binding = (work.action_preparation.evidence(h.action.action_id, 1, h.effect_id)
                    if purpose is RecordingPurpose.OBSERVATION else work.action_preparation.recovery(h.action.action_id, 1))
                assert binding is not None and binding.step_id == selected


@pytest.mark.parametrize("problem", ["source", "revision"])
def test_supplement_choices_fail_closed_for_stale_source(review_context, problem):
    app, h, target = review_context
    recording = _supplement(h, target, RecordingPurpose.OBSERVATION, 2)
    if problem == "source":
        with h.core.uow_factory() as work:
            current = work.application_understanding.get(h.project_id)
            work.application_understanding.replace(current.model_copy(update={"confirmed_endpoint": "http://127.0.0.1:8766"}))
            work.commit()
    else:
        # 旧录制保持不可变；按现有业务修订规则推进当前 Action，使其失效。
        with h.core.uow_factory() as work:
            current = work.business_boundaries.action_revision(h.action.action_id, 1)
            root = work.business_boundaries.action(h.action.action_id)
            now_us = max(current.created_at_us, root.updated_at_us) + 1
            work.business_boundaries.add_action_revision(current.model_copy(update={
                "revision": 2, "created_at_us": now_us,
                "approval": current.approval.model_copy(update={"approved_at_us": now_us}),
            }))
            work.business_boundaries.replace_action(root.model_copy(update={"current_revision": 2, "updated_at_us": now_us}))
            work.commit()
    with TestClient(app) as client:
        response = client.get(f"/api/recordings/{recording.recording_id}")
        assert response.status_code == 400 and response.json()["error"]["code"] == "RECORD_STATE_PRECONDITION"


def test_target_and_nonreview_details_have_no_supplement_choices(review_context, monkeypatch):
    app, h, target = review_context
    candidate_reader = Mock(side_effect=AssertionError("非补录待审不得筛选候选"))
    monkeypatch.setattr(h.core.preparation_bindings, "candidates", candidate_reader)
    pending = add_recording(h)
    with TestClient(app) as client:
        for recording in (target, pending):
            response = client.get(f"/api/recordings/{recording.recording_id}")
            assert response.json()["data"]["supplement_choices"] == []
    candidate_reader.assert_not_called()


@pytest.mark.parametrize("missing_draft", [False, True])
def test_supplement_outside_review_or_without_draft_has_no_choices(review_context, monkeypatch, missing_draft):
    app, h, target = review_context
    recording = _supplement(h, target, RecordingPurpose.OBSERVATION, 1)
    original = h.core.recording_lifecycle.status(recording.recording_id)
    if missing_draft:
        monkeypatch.setattr(h.core.recording_lifecycle, "status", lambda _: original.model_copy(update={"draft": None}))
    else:
        h.core.recording_lifecycle.finalize(recording.recording_id, var_dir=h.var_dir, now_us=200)
    reader = Mock(side_effect=AssertionError("无待审草稿不得筛选候选"))
    monkeypatch.setattr(h.core.preparation_bindings, "candidates", reader)
    with TestClient(app) as client:
        result = client.get(f"/api/recordings/{recording.recording_id}")
        assert result.status_code == 200 and result.json()["data"]["supplement_choices"] == []
    reader.assert_not_called()


def test_discard_api_uses_service_and_keeps_draft_history(review_context):
    app, h, target = review_context
    recording = _supplement(h, target, RecordingPurpose.RECOVERY, 2)
    job = JobRecord(job_id="job_" + uuid4().hex, project_id=h.project_id, recording_id=recording.recording_id,
        operation_type="RECORDING", state=JobState.SUCCEEDED, idempotency_key=recording.recording_id,
        request_hash="a" * 64, attempt=0, max_attempts=1, available_at_us=1, fencing_token=0,
        created_at_us=1, updated_at_us=3)
    with h.core.uow_factory() as work:
        work.jobs.add(job)
        work.commit()
    with TestClient(app) as client:
        path = f"/api/recordings/{recording.recording_id}/discard"
        first = client.post(path, json={"schema_version": "1"})
        assert first.status_code == 200, first.text
        assert first.json()["data"]["recording"]["state"] == "CANCELLED"
        assert first.json()["data"]["draft"]["revision"] == 2
        assert client.post(path, json={"schema_version": "1"}).json() == first.json()
        assert client.post(f"/api/recordings/{target.recording_id}/discard", json={"schema_version": "1"}).status_code == 400
        assert client.post("/api/recordings/rec_ffffffffffffffffffffffffffffffff/discard", json={"schema_version": "1"}).status_code == 404


@pytest.mark.parametrize("body", [{}, {"schema_version": 1}, {"schema_version": "2"}, {"schema_version": "1", "reason": "extra"}])
def test_discard_api_strict_body(review_context, body):
    app, h, target = review_context
    with TestClient(app) as client:
        assert client.post(f"/api/recordings/{target.recording_id}/discard", json=body).status_code == 422


@pytest.mark.parametrize("authorization", ["missing_session", "wrong_origin"])
def test_discard_api_local_control(review_context, authorization):
    app, h, target = review_context
    cls = RawTestClient if authorization == "missing_session" else TestClient
    with cls(app, base_url=TEST_CONTROL_ORIGIN) as client:
        result = client.post(f"/api/recordings/{target.recording_id}/discard", json={"schema_version": "1"},
            headers={"Origin": TEST_CONTROL_ORIGIN if authorization == "missing_session" else "http://127.0.0.1:9999"})
        assert result.status_code == 403


def test_cancel_api_rejects_run_without_touching_job_or_queue(tmp_path, monkeypatch):
    app = create_app(tmp_path / "var", start_worker=False, secret_store=MemorySecretStore(), environ={})
    core = app.state.context
    run_job = SimpleNamespace(job_id="job-run", run_id="run-frozen", recording_id=None, state="QUEUED")
    before = vars(run_job).copy()
    original_factory = core.uow_factory
    @contextmanager
    def factory():
        with original_factory() as work:
            work.jobs.get = lambda job_id: run_job if job_id == "job-run" else None
            yield work
    monkeypatch.setattr(core, "uow_factory", factory)
    cancel = Mock(side_effect=AssertionError("RUN 不应进入 cancellation queue"))
    monkeypatch.setattr(core.job_queue, "request_cancellation", cancel)
    with TestClient(app) as client:
        response = client.post("/api/jobs/job-run/cancel")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "STATE_PRECONDITION"
        assert client.post("/api/jobs/missing-job/cancel").status_code == 404
        assert vars(run_job) == before
        cancel.assert_not_called()


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
