# 验证后端 API中的项目注册与就绪度接口。

from __future__ import annotations

from pathlib import Path

from tests.fixtures.control_plane import TestClient, create_app


def test_project_register_uses_profile_without_governed_binding(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    profile_path = Path("samples/web/fixed/profile.json").resolve()
    with TestClient(app) as client:
        response = client.post(
            "/api/projects",
            json={"schema_version": "1", "profile_path": str(profile_path)},
        )
        assert response.status_code == 200
        assert response.json()["data"]["governed_contract_id"] is None
        assert response.json()["data"]["governed_contract_version"] is None

        readiness = client.get(
            f"/api/projects/{response.json()['data']['project_id']}/readiness"
        )
        assert readiness.status_code == 200
        assert readiness.json()["data"]["endpoint_status"] == "LEGACY_PROFILE"
