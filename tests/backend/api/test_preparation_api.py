# 验证本地 API 只把 prepare-safe 写入口适配到确定性准备服务。

from unittest.mock import Mock

from product.backend.workflows.projects.preparation import ProjectPreparationView
from tests.fixtures.control_plane import TestClient, create_app


def test_prepare_safe_api_delegates_to_project_preparation_service(tmp_path) -> None:
    app = create_app(tmp_path / "var", start_worker=False, environ={})
    expected = ProjectPreparationView(
        project_id="project-1",
        ready=False,
        items=(),
        next_item_key=None,
        auto_action_count=0,
        user_action_count=0,
        blocked_count=0,
        external_blockers=(),
    )
    prepare_safe = Mock(return_value=expected)
    app.state.context.project_preparation.prepare_safe = prepare_safe

    with TestClient(app) as client:
        response = client.post("/api/projects/project-1/preparation/prepare-safe")

    assert response.status_code == 200
    assert response.json()["data"] == expected.model_dump(mode="json")
    prepare_safe.assert_called_once_with("project-1")
