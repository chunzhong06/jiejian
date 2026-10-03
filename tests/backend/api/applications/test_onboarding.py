# 验证首次使用 API 只保留目录选择与预算内只读识别。

from __future__ import annotations

from pathlib import Path

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.onboarding.models import FolderSelectionResult
from tests.fixtures.control_plane import TestClient, create_app


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
    assert response.json()["data"] == {"status": "cancelled"}


def test_onboarding_inspect_returns_safe_result(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"scripts":{"dev":"echo secret"}}',
        encoding="utf-8",
    )
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        response = client.post(
            "/api/onboarding/inspect",
            json={"schema_version": "1", "path": str(tmp_path.resolve())},
        )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert "schema_version" not in payload
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


def test_onboarding_openapi_contains_no_manual_quick_check_routes(
    tmp_path: Path,
) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        paths = client.get("/openapi.json").json()["paths"]

    assert paths["/api/onboarding/select-folder"]["post"]
    assert paths["/api/onboarding/inspect"]["post"]
    assert not any(path.startswith("/api/onboarding/sessions") for path in paths)
    assert not any("quick-check" in path for path in paths)
