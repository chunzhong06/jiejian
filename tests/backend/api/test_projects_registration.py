from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from product.backend.api import create_app


def test_project_register_uses_profile_without_governed_binding(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    profile_path = Path("samples/http/fixed/profile.json").resolve()
    with TestClient(app) as client:
        response = client.post(
            "/api/projects",
            json={"schema_version": "1", "profile_path": str(profile_path)},
        )
        assert response.status_code == 200
        assert response.json()["data"]["governed_contract_id"] is None
        assert response.json()["data"]["governed_contract_version"] is None
