# 验证当前 Sample API 的显式同意、普通人工审批、准备、版本门禁和精确退出清理。
from pathlib import Path

from product.backend.core.lifecycle import ProjectStatus
from tests.fixtures.collaboration_golden import InMemorySecretStore
from tests.fixtures.control_plane import TestClient, create_app
from tests.fixtures.runtime_environment import runtime_identity_environment

_SAMPLE_ROOT = Path(__file__).resolve().parents[3] / "samples/web/collaboration_space"


def _app(tmp_path, *, sample_root=_SAMPLE_ROOT):
    var_dir = tmp_path / "var"
    store = InMemorySecretStore()
    return create_app(var_dir, start_worker=False, official_sample_root=sample_root,
        secret_store=store, environ=runtime_identity_environment(var_dir)), store


def _start(client):
    return client.post("/api/experience/official-sample/start", json={"schema_version": "1", "consent": True})


def test_unavailable_installation_keeps_product_alive_and_requires_consent(tmp_path):
    app, _ = _app(tmp_path, sample_root=None)
    with TestClient(app) as client:
        status = client.get("/api/experience/official-sample").json()["data"]
        assert not status["available"] and not status["active"]
        assert status["project_id"] is None
        assert client.get("/ready").status_code == 200
        assert client.post("/api/experience/official-sample/start", json={"schema_version": "1", "consent": False}).status_code == 422
        assert client.post("/api/experience/official-sample/boundary-proposal").status_code != 200
        summary = client.get("/api/experience/official-sample/validation-summary").json()["data"]
        assert summary["available"] is False and summary["summary"] is None


def test_start_stop_and_replacement_archive_only_owned_sample(tmp_path):
    app, _ = _app(tmp_path)
    with TestClient(app) as client:
        first_response = _start(client)
        assert first_response.status_code == 200, first_response.text
        first = first_response.json()["data"]
        core = app.state.context
        root = core.official_samples.active.experience_root
        assert first["active"] and first["scenario_version"] == "VULNERABLE"
        assert not first["scenario_prepared"]
        assert first["origin"].startswith("http://127.0.0.1:")
        second_response = _start(client)
        assert second_response.status_code == 200, second_response.text
        second = second_response.json()["data"]
        assert second["project_id"] != first["project_id"]
        assert not root.exists()
        assert core.projects.get(first["project_id"]).status is ProjectStatus.ARCHIVED
        stopped = client.post("/api/experience/official-sample/stop")
        assert stopped.status_code == 200, stopped.text
        assert not stopped.json()["data"]["active"]
        assert core.projects.get(second["project_id"]).status is ProjectStatus.ARCHIVED
        assert core.official_samples.active is None


def test_prepare_requires_ordinary_approval_and_never_publishes_result(tmp_path):
    app, store = _app(tmp_path)
    with TestClient(app) as client:
        project = _start(client).json()["data"]["project_id"]
        core = app.state.context
        unapproved = client.post("/api/experience/official-sample/prepare").json()["data"]
        assert not unapproved["scenario_prepared"]
        assert unapproved["pending_tasks"] == ["HUMAN_BOUNDARY_APPROVAL_REQUIRED"]
        assert core.test_identities.list(project) == ()
        proposed = client.post("/api/experience/official-sample/boundary-proposal")
        assert proposed.status_code == 200, proposed.text
        proposal = proposed.json()["data"]["proposal"]
        approved = client.post(f"/api/projects/{project}/business-boundaries/proposals/{proposal['proposal_id']}/approve",
            json={"schema_version": "1", "expected_fingerprint": proposal["proposal_fingerprint"], "reason": "本机用户确认公开业务规则"})
        assert approved.status_code == 200, approved.text
        prepared = client.post("/api/experience/official-sample/prepare")
        assert prepared.status_code == 200, prepared.text
        assert prepared.json()["data"]["scenario_prepared"]
        assert len(core.test_identities.list(project)) == 2
        assert store.values == {}
        preview = client.get(f"/api/projects/{project}/check-preview").json()["data"]
        assert preview["can_execute"] and preview["case_count"] == 3 and preview["action_count"] == 2
        with core.uow_factory() as work:
            assert len(work.jobs.list_for_project(project)) == 3
            assert all(job.operation_type == "BROWSER_RECORDING" for job in work.jobs.list_for_project(project))
        assert client.post("/api/experience/official-sample/prepare").json()["data"] == prepared.json()["data"]
        rejected = client.post("/api/experience/official-sample/version", json={"schema_version": "1", "version": "FIXED"})
        assert rejected.status_code != 200
        assert core.official_experience.status().scenario_version == "VULNERABLE"
        limited = client.post("/api/experience/official-sample/version", json={"schema_version": "1", "version": "EVIDENCE_LIMITED"})
        assert limited.status_code == 200, limited.text
        assert limited.json()["data"]["scenario_version"] == "EVIDENCE_LIMITED"
        with core.uow_factory() as work:
            assert all(job.operation_type == "BROWSER_RECORDING" for job in work.jobs.list_for_project(project))


def test_active_check_blocks_sample_switch_until_public_cancellation(tmp_path):
    from tests.backend.workflows.test_current_official_sample import prepare_sample
    app, _ = _app(tmp_path)
    with TestClient(app) as client:
        core = app.state.context
        project = prepare_sample(core)
        preview = core.checks.preview(project)
        submitted = core.checks.submit(project, expected_plan_fingerprint=preview.plan_fingerprint, idempotency_key="active-switch-guard")
        before = core.official_experience.status()
        response = client.post("/api/experience/official-sample/version", json={"schema_version": "1", "version": "EVIDENCE_LIMITED"})
        assert response.status_code != 200
        assert core.official_experience.status() == before
        assert client.post("/api/experience/official-sample/stop").status_code != 200
        cancelled = client.post(f"/api/jobs/{submitted.job.job_id}/cancel")
        assert cancelled.status_code == 200, cancelled.text
        assert core.check_results.status(submitted.run.run_id).job.state == "CANCELLED"
        assert client.post("/api/experience/official-sample/stop").status_code == 200
