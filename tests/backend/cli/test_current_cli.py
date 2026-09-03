# 验证 1.1.0 CLI 只公开 Web 启动、系统诊断与维护入口。

from __future__ import annotations

from typer.testing import CliRunner

from product.backend import __version__
from product.backend.cli.app import app


def test_current_cli_help_excludes_deferred_product_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "serve" in result.stdout
    assert "system" in result.stdout
    for deferred in ("application", "change", "check", "result", "history", "status"):
        assert deferred not in result.stdout


def test_current_cli_version_uses_product_version_truth() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__
