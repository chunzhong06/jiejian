# 验证旧手工治理和 ExecutionProfile 产品路由已从控制面移除。

from __future__ import annotations

import pytest

from pathlib import Path

from product.backend.infrastructure.storage.base import Base
from tests.support.builders.control_plane import create_app




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
    assert "/api/projects/{project_id}/permission-intents" not in paths
    assert "/api/projects/{project_id}/permission-drafts" not in paths
    assert "/api/projects/{project_id}/business-boundaries/rule-candidates" in paths
    assert "/api/projects/{project_id}/runs" in paths
    for suffix in ("result-status", "result-repair", "presentation", "report", "reports/base", "reports/gate"):
        assert f"/api/runs/{{run_id}}/{suffix}" not in paths
    assert "/api/runs/{run_id}/result-story" in paths


def test_internal_execution_profile_storage_remains_registered() -> None:
    assert "execution_profiles" in Base.metadata.tables
    assert "contract_versions" in Base.metadata.tables
    assert "requirements" not in Base.metadata.tables
    assert "contract_candidates" not in Base.metadata.tables


def test_cli_does_not_offer_human_approval_commands():
    import click
    from typer.main import get_command
    from typer.testing import CliRunner
    from product.backend.interfaces.cli.app import app
    def commands(group):
        for name,command in group.commands.items():
            yield name
            if isinstance(command,click.Group):yield from commands(command)
    assert {'approve','confirm','activate','decide-role','decide-action'}.isdisjoint(commands(get_command(app)))
    result=CliRunner().invoke(app,['permissions','approve'])
    assert result.exit_code==2


pytestmark = [pytest.mark.level3]
