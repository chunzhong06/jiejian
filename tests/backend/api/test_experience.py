# 验证官方 Sample Experience API 只自动化已同意的机械事实并复用正式产品服务。

from __future__ import annotations

import json
from pathlib import Path

from product.backend.core.test_identity import (
    TestIdentityAuthMethod as IdentityAuthMethod,
)
from product.backend.core.lifecycle import ProjectStatus
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


def _start(client: TestClient):
    return client.post(
        "/api/experience/official-sample/start",
        json={
            "schema_version": "1",
            "consent": True,
        },
    )


def _validation_summary() -> dict[str, object]:
    return {
        "schema_version": "1",
        "generated_at_us": 1_800_000_000_000_000,
        "suite": "validation",
        "status": "accepted",
        "repetitions": 1,
        "case_count": 30,
        "case_run_count": 30,
        "application_count": 2,
        "mode_count": 5,
        "state_count": 3,
        "full_exact_match_count": 30,
        "full_wrong_pass_vulnerable": 0,
        "full_wrong_pass_evidence_gap": 0,
        "http_exact_match_count": 14,
        "http_wrong_pass_vulnerable": 6,
        "http_wrong_pass_evidence_gap": 10,
        "http_wrong_pass_per_matrix": 16,
        "source_revision": "a" * 40,
        "source_dirty": False,
    }


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
            "project_id": None,
            "origin": None,
            "scenario_prepared": False,
            "scenario_version": None,
            "scenario_changed_at_us": None,
            "vulnerable_change_id": None,
            "repair_change_id": None,
        }
        assert client.get("/ready").status_code == 200
        rejected = client.post(
            "/api/experience/official-sample/start",
            json={
                "schema_version": "1",
                "consent": False,
            },
        )
        assert rejected.status_code == 422


def test_validation_summary_reads_only_the_stable_sanitized_receipt(
    tmp_path: Path,
) -> None:
    app, _ = _app(tmp_path)
    summary_path = (
        app.state.context.paths.competition_audit
        / "latest-validation-summary.json"
    )
    with TestClient(app) as client:
        missing = client.get(
            "/api/experience/official-sample/validation-summary"
        )
        assert missing.status_code == 200
        assert missing.json()["data"] == {
            "available": False,
            "unavailable_reason": "尚未发布可展示的验证汇总",
            "summary": None,
        }

        summary_path.write_text(
            json.dumps(_validation_summary()),
            encoding="utf-8",
        )
        published = client.get(
            "/api/experience/official-sample/validation-summary"
        )
        assert published.status_code == 200
        assert published.json()["data"]["available"] is True
        assert published.json()["data"]["summary"]["case_count"] == 30
        assert "private_oracle" not in published.text
        assert "results" not in published.json()["data"]["summary"]

        summary_path.write_text(
            json.dumps({**_validation_summary(), "results": []}),
            encoding="utf-8",
        )
        invalid = client.get(
            "/api/experience/official-sample/validation-summary"
        )
        assert invalid.status_code == 200
        assert invalid.json()["data"]["available"] is False
        assert invalid.json()["data"]["summary"] is None


def test_start_creates_agent_regression_on_top_of_a_safe_source_baseline(
    tmp_path: Path,
) -> None:
    app, _ = _app(tmp_path)
    with TestClient(app) as client:
        response = _start(client)
        assert response.status_code == 200, response.text
        started = response.json()["data"]
        assert started["active"] is True
        assert started["scenario_version"] == "VULNERABLE"
        assert started["scenario_prepared"] is False
        assert started["vulnerable_change_id"] is None
        assert started["origin"].startswith("http://127.0.0.1:")
        assert "source" not in started
        assert "secret" not in response.text.casefold()

        core = app.state.context
        understanding = core.application_understanding.get(started["project_id"])
        assert understanding.confirmed_endpoint == started["origin"]
        assert understanding.source_analysis_authorized is True
        assert understanding.source_fingerprint is not None
        assert core.local_observer_environments.resolve(
            understanding.source_root,
            understanding.confirmed_endpoint,
        ) == str(core.official_samples.active.descriptor_path)
        experience_root = core.official_samples.active.experience_root

        stopped = client.post("/api/experience/official-sample/stop")
        assert stopped.status_code == 200
        assert stopped.json()["data"]["active"] is False
        assert core.local_observer_environments.resolve(
            understanding.source_root,
            understanding.confirmed_endpoint,
        ) is None
        assert not experience_root.exists()
        assert core.projects.get(started["project_id"]).status is ProjectStatus.ARCHIVED
        assert all(
            item.project_id != started["project_id"]
            for item in core.projects.list()
        )


def test_starting_a_new_official_sample_archives_the_previous_sample_project(
    tmp_path: Path,
) -> None:
    app, _ = _app(tmp_path)
    with TestClient(app) as client:
        first = _start(client).json()["data"]
        second_response = _start(client)

        assert second_response.status_code == 200, second_response.text
        second = second_response.json()["data"]
        assert second["project_id"] != first["project_id"]
        assert app.state.context.projects.get(first["project_id"]).status is ProjectStatus.ARCHIVED
        assert [item.project_id for item in app.state.context.projects.list()] == [second["project_id"]]


def test_one_click_prepare_applies_public_scenario_contract_without_publishing_a_result(
    tmp_path: Path,
) -> None:
    app, store = _app(tmp_path)
    with TestClient(app) as client:
        response = _start(client)
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

        prepared = client.post("/api/experience/official-sample/prepare")
        assert prepared.status_code == 200, prepared.text
        prepared_data = prepared.json()["data"]
        assert prepared_data["scenario_prepared"] is True
        assert prepared_data["vulnerable_change_id"].startswith("chg_")
        manifest, change_set, _ = app.state.context.source_changes.get(
            prepared_data["vulnerable_change_id"]
        )
        assert change_set.modified_paths == ("authorization_policy.py",)
        assert manifest.submitted_by == "MCP · Codex"
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
        flows = app.state.context.product_flows.list(project_id)
        assert len(flows) == 2
        assert all(item["state"] == "COMPLETED" for item in flows)
        assert all(item["job"]["state"] == "SUCCEEDED" for item in flows)
        assert all(item["job"]["attempt"] == 1 for item in flows)
        preview = client.get(f"/api/projects/{project_id}/check-preview")
        assert preview.status_code == 200, preview.text
        assert preview.json()["data"]["ready"] is True
        assert preview.json()["data"]["case_count"] == 3
        assert preview.json()["data"]["differential_pair_count"] == 1
        assert app.state.context.product_status.get(project_id).latest_result is None

        repeated = client.post("/api/experience/official-sample/prepare")
        assert repeated.status_code == 200
        assert len(app.state.context.test_identities.list(project_id)) == 2
        assert len(store.values) == 2

        limited = client.post(
            "/api/experience/official-sample/version",
            json={"schema_version": "1", "version": "EVIDENCE_LIMITED", "source_run_id": None},
        )
        assert limited.status_code == 200, limited.text
        assert limited.json()["data"]["scenario_version"] == "EVIDENCE_LIMITED"
