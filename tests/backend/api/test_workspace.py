# 验证动作级 Workspace 是唯一 CURRENT 项目状态 API，旧 status 路由不再注册。

from pathlib import Path

from tests.fixtures.control_plane import TestClient, create_app


def test_workspace_api_replaces_legacy_project_status(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    app = create_app(tmp_path / "var", start_worker=False, environ={})

    with TestClient(app) as client:
        connected = client.post(
            "/api/applications/connect",
            json={
                "schema_version": "1",
                "source_root": str(source),
                "project_name": "Workspace API 测试",
            },
        )
        assert connected.status_code == 201
        project_id = connected.json()["data"]["project"]["project_id"]

        response = client.get(f"/api/projects/{project_id}/workspace")
        assert response.status_code == 200
        workspace = response.json()["data"]
        assert workspace["project"]["project_id"] == project_id
        assert workspace["connection"]["endpoint_status"] == "NEEDS_CONFIRMATION"
        assert workspace["primary_task"]["task_kind"] == (
            "CONFIRM_APPLICATION_ENDPOINT"
        )
        assert workspace["primary_task"]["route"] == "/application"
        assert [item["route"] for item in workspace["areas"]] == [
            "/workspace",
            "/permissions",
            "/changes",
            "/tests",
        ]

        assert client.get(f"/api/projects/{project_id}/status").status_code == 404
