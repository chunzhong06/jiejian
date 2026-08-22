from __future__ import annotations

from pathlib import Path
import json

from fastapi.testclient import TestClient
import pytest

from product.backend.api import create_app
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.onboarding.models import FolderSelectionResult
from product.protocols.execution_profile import parse_execution_profile


class FakeFolderSelector:
    def __init__(self, result: FolderSelectionResult) -> None:
        self.result = result

    def select_folder(self) -> FolderSelectionResult:
        return self.result


class FailingFolderSelector:
    def select_folder(self) -> FolderSelectionResult:
        raise JiejianError(
            ErrorCode.ONBOARDING_SELECTOR_UNAVAILABLE,
            "系统目录选择器当前不可用，请改用手工绝对路径",
        )


def test_onboarding_select_folder_uses_injected_selector(tmp_path: Path) -> None:
    selected = tmp_path / "application"
    selected.mkdir()
    app = create_app(
        tmp_path / "var",
        start_worker=False,
        folder_selector=FakeFolderSelector(
            FolderSelectionResult(status="selected", path=str(selected))
        ),
    )
    with TestClient(app) as client:
        response = client.post("/api/onboarding/select-folder")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "schema_version": "1",
        "status": "selected",
        "path": str(selected),
    }


def test_onboarding_cancelled_selector_is_not_an_error(tmp_path: Path) -> None:
    app = create_app(
        tmp_path / "var",
        start_worker=False,
        folder_selector=FakeFolderSelector(
            FolderSelectionResult(status="cancelled")
        ),
    )
    with TestClient(app) as client:
        response = client.post("/api/onboarding/select-folder")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "schema_version": "1",
        "status": "cancelled",
    }


def test_onboarding_inspect_returns_versioned_safe_result(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"scripts":{"dev":"echo secret"}}', encoding="utf-8"
    )
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        response = client.post(
            "/api/onboarding/inspect",
            json={"schema_version": "1", "path": str(tmp_path.resolve())},
        )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["schema_version"] == "1"
    assert payload["start_candidates"][0]["executed"] is False
    assert "echo secret" not in response.text


def test_onboarding_inspect_maps_invalid_path_without_leaking_path(
    tmp_path: Path,
) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    secret_path = str(tmp_path / "missing-secret-folder")
    with TestClient(app) as client:
        response = client.post(
            "/api/onboarding/inspect",
            json={"schema_version": "1", "path": secret_path},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ONBOARDING_INPUT_INVALID"
    assert secret_path not in response.text


def test_onboarding_selector_unavailable_maps_to_503(tmp_path: Path) -> None:
    app = create_app(
        tmp_path / "var",
        start_worker=False,
        folder_selector=FailingFolderSelector(),
    )
    with TestClient(app) as client:
        response = client.post("/api/onboarding/select-folder")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ONBOARDING_SELECTOR_UNAVAILABLE"


def test_onboarding_read_budget_maps_to_413(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    app = create_app(tmp_path / "var", start_worker=False)
    app.state.context.onboarding.limits = app.state.context.onboarding.limits.model_copy(
        update={"max_file_bytes": 1}
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/onboarding/inspect",
            json={"schema_version": "1", "path": str(tmp_path.resolve())},
        )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "ONBOARDING_READ_BUDGET"
    assert response.json()["error"]["message"] == "应用目录内容过多，自动识别已达到安全扫描上限。请确认选择的是项目根目录，或改为手工填写必要信息。"


def test_onboarding_routes_are_present_in_openapi(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        document = client.get("/openapi.json").json()

    assert document["paths"]["/api/onboarding/select-folder"]["post"]
    inspect = document["paths"]["/api/onboarding/inspect"]["post"]
    assert "OnboardingInspectRequest" in str(inspect)


def test_onboarding_quick_check_creates_current_profile_and_is_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "package.json").write_text("{}", encoding="utf-8")
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        created = client.post(
            "/api/onboarding/sessions",
            json={"schema_version": "1", "path": str(source.resolve()), "project_name": "新手项目"},
        )
        assert created.status_code == 201
        session = created.json()["data"]
        session_id = session["session_id"]
        assert session["primary_configured"] is False
        updated = client.patch(
            f"/api/onboarding/sessions/{session_id}",
            json={
                "schema_version": "1", "revision": session["revision"],
                "target_address": "http://127.0.0.1:8765",
                "primary_display_name": "主账号", "comparison_display_name": "对照账号",
                "primary_resource_id": "primary-resource", "comparison_resource_id": "comparison-resource",
                "read_only_path_template": "/resources/{resource_id}", "recovery_path": "/reset",
                "confirmations": {"app_started": True, "target_authorized": True, "recovery_confirmed": True, "dangerous_inference_confirmed": True},
            },
        )
        assert updated.status_code == 200
        credentials = client.post(
            f"/api/onboarding/sessions/{session_id}/credentials",
            json={"schema_version": "1", "primary": "primary-secret", "comparison": "comparison-secret"},
        )
        assert credentials.status_code == 200
        assert "primary-secret" not in credentials.text
        assert "comparison-secret" not in credentials.text
        refreshed = client.get(f"/api/onboarding/sessions/{session_id}")
        assert refreshed.status_code == 200
        assert refreshed.json()["data"]["status"] == "READY"
        context = app.state.context
        original_submit = context.execution_submission.submit
        failed = True

        def fail_once(command, *, known_secrets=()):
            nonlocal failed
            if failed:
                failed = False
                raise JiejianError(ErrorCode.JOB_PERSISTENCE, "模拟提交失败")
            return original_submit(command, known_secrets=known_secrets)

        context.execution_submission.submit = fail_once
        failed_attempt = client.post(
            f"/api/onboarding/sessions/{session_id}/quick-check",
            json={"schema_version": "1"},
        )
        assert failed_attempt.status_code == 400
        context.execution_submission.submit = original_submit
        quick = client.post(
            f"/api/onboarding/sessions/{session_id}/quick-check",
            json={"schema_version": "1"},
        )
        assert quick.status_code == 202, quick.text
        result = quick.json()["data"]
        repeated = client.post(
            f"/api/onboarding/sessions/{session_id}/quick-check",
            json={"schema_version": "1"},
        )
        assert repeated.status_code == 202
        assert repeated.json()["data"]["run_id"] == result["run_id"]
        assert repeated.json()["data"]["created"] is False

    profile_path = tmp_path / "var" / "onboarding" / session_id / "profile.json"
    profile = parse_execution_profile(profile_path.read_bytes())
    assert profile.target.scope.base_url == "http://127.0.0.1:8765"
    assert profile.target.scope.follow_redirects is False
    assert profile.target.scope.max_requests == 10
    assert profile.contract_id.endswith("-contract")
    assert profile.observer_bindings[0].requirement_id == "resource_state"
    assert {item.subject_id for item in profile.subject_bindings} == {"primary", "comparison"}
    active_contract = app.state.context.projects.current_contract(profile.project_id).snapshot
    assert any(item.relation.value == "OWNS" for item in active_contract.relations)
    assert tuple(item.expectation.value for item in active_contract.rules) == (
        "ALLOW",
        "DENY",
    )
    assert "primary-secret" not in profile_path.read_text(encoding="utf-8")
    assert "comparison-secret" not in profile_path.read_text(encoding="utf-8")
    persisted = json.loads((tmp_path / "var" / "onboarding" / "sessions" / f"{session_id}.json").read_text(encoding="utf-8"))
    assert "primary-secret" not in json.dumps(persisted)
    assert "comparison-secret" not in json.dumps(persisted)

    restarted = create_app(tmp_path / "var", start_worker=False)
    with TestClient(restarted) as client:
        after_restart = client.get(f"/api/onboarding/sessions/{session_id}")
    assert after_restart.status_code == 200
    assert after_restart.json()["data"]["primary_configured"] is False
    assert after_restart.json()["data"]["comparison_configured"] is False


def test_onboarding_quick_check_rejects_changed_session_after_submission_failure(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        created = client.post(
            "/api/onboarding/sessions",
            json={"schema_version": "1", "path": str(source.resolve()), "project_name": "项目"},
        ).json()["data"]
        session_id = created["session_id"]
        updated_response = client.patch(
            f"/api/onboarding/sessions/{session_id}",
            json={
                "schema_version": "1", "revision": created["revision"],
                "target_address": "http://127.0.0.1:8765",
                "primary_display_name": "主账号", "comparison_display_name": "对照账号",
                "primary_resource_id": "primary-resource", "comparison_resource_id": "comparison-resource",
                "read_only_path_template": "/resources/{resource_id}", "recovery_path": "/reset",
                "confirmations": {"app_started": True, "target_authorized": True, "recovery_confirmed": True, "dangerous_inference_confirmed": True},
            },
        )
        assert updated_response.status_code == 200
        client.post(
            f"/api/onboarding/sessions/{session_id}/credentials",
            json={"schema_version": "1", "primary": "primary-secret", "comparison": "comparison-secret"},
        )
        calls: list[str] = []
        context = app.state.context

        def fail_submission(command, *, known_secrets=()):
            calls.append(command.run_id)
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "模拟提交失败")

        context.execution_submission.submit = fail_submission
        first = client.post(
            f"/api/onboarding/sessions/{session_id}/quick-check",
            json={"schema_version": "1"},
        )
        assert first.status_code == 400
        profile_path = tmp_path / "var" / "onboarding" / session_id / "profile.json"
        old_profile = parse_execution_profile(profile_path.read_bytes())
        assert old_profile.target.scope.base_url == "http://127.0.0.1:8765"
        current = client.get(f"/api/onboarding/sessions/{session_id}").json()["data"]

        changed = client.patch(
            f"/api/onboarding/sessions/{session_id}",
            json={
                "schema_version": "1", "revision": current["revision"],
                "target_address": "http://127.0.0.1:8766",
            },
        )
        assert changed.status_code == 200
        retry = client.post(
            f"/api/onboarding/sessions/{session_id}/quick-check",
            json={"schema_version": "1"},
        )

    assert retry.status_code == 409
    assert retry.json()["error"]["code"] == "ONBOARDING_SESSION_CONFLICT"
    assert len(calls) == 1
    assert parse_execution_profile(profile_path.read_bytes()).target.scope.base_url == "http://127.0.0.1:8765"


@pytest.mark.parametrize(
    "path",
    [
        "/resources\\{resource_id}",
        "/resources/\x00{resource_id}",
        "/resources/%2e%2e/{resource_id}",
        "/resources/%2Fprivate/{resource_id}",
        "/resources/%5Cprivate/{resource_id}",
    ],
)
def test_onboarding_rejects_unsafe_encoded_or_control_paths(tmp_path: Path, path: str) -> None:
    source = tmp_path / "source"
    source.mkdir()
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        created = client.post(
            "/api/onboarding/sessions",
            json={"schema_version": "1", "path": str(source.resolve()), "project_name": "项目"},
        ).json()["data"]
        response = client.patch(
            f"/api/onboarding/sessions/{created['session_id']}",
            json={
                "schema_version": "1", "revision": created["revision"],
                "read_only_path_template": path,
            },
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ONBOARDING_INPUT_INVALID"


@pytest.mark.parametrize(
    "target",
    [
        "http://localhost:8765",
        "http://[::1]:8765",
        "http://192.168.1.10:8765",
        "https://example.test:443",
        "http://user:pass@127.0.0.1:8765",
        "http://127.0.0.1",
    ],
)
def test_onboarding_quick_check_rejects_non_ipv4_loopback_targets(
    tmp_path: Path, target: str
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        created = client.post(
            "/api/onboarding/sessions",
            json={"schema_version": "1", "path": str(source.resolve()), "project_name": "项目"},
        ).json()["data"]
        response = client.patch(
            f"/api/onboarding/sessions/{created['session_id']}",
            json={"schema_version": "1", "revision": created["revision"], "target_address": target},
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ONBOARDING_TARGET_INVALID"


def test_onboarding_quick_check_reports_missing_answers_without_creating_profile(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        created = client.post(
            "/api/onboarding/sessions",
            json={"schema_version": "1", "path": str(source.resolve()), "project_name": "项目"},
        ).json()["data"]
        response = client.post(
            f"/api/onboarding/sessions/{created['session_id']}/quick-check",
            json={"schema_version": "1"},
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ONBOARDING_SESSION_INCOMPLETE"
    assert not (tmp_path / "var" / "onboarding" / created["session_id"] / "profile.json").exists()
