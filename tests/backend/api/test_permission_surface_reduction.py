# 验证旧手工治理和 ExecutionProfile 产品路由已从控制面移除。

from __future__ import annotations

from pathlib import Path

from product.backend.infra.storage import Base
from tests.fixtures.control_plane import create_app


ROOT = Path(__file__).resolve().parents[3]


def test_old_governance_and_execution_profile_routes_are_absent(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    try:
        paths = set(app.openapi()["paths"])
    finally:
        app.state.context.close()

    assert not any("contract-governance" in path for path in paths)
    assert not any("execution-profiles" in path for path in paths)
    assert "/api/projects/{project_id}/contracts" not in paths
    assert "/api/runs/{run_id}/contract" not in paths
    assert "/api/projects/{project_id}/permission-intents" in paths


def test_internal_execution_profile_storage_remains_registered() -> None:
    assert "execution_profiles" in Base.metadata.tables
    assert "contract_versions" in Base.metadata.tables
    assert "requirements" not in Base.metadata.tables
    assert "contract_candidates" not in Base.metadata.tables


def test_non_gui_control_modules_do_not_call_human_approval_surfaces() -> None:
    cli_sources = sorted((ROOT / "product" / "backend" / "cli").rglob("*.py"))
    sources = cli_sources + [ROOT / "product" / "backend" / "api" / "mcp.py"]
    forbidden_calls = (
        "permission_intents.confirm(",
        "application_understanding.decide_role(",
        "application_understanding.decide_action(",
        "application_understanding.add_manual_role(",
        "application_understanding.add_manual_action(",
    )
    for path in sources:
        source = path.read_text(encoding="utf-8-sig")
        assert not [call for call in forbidden_calls if call in source], path
