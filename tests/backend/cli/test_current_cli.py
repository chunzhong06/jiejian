# 验证 CLI 只公开 Web 启动、系统诊断与维护入口。

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from product.backend import __version__
from product.backend.cli.app import app
from product.backend.core.errors import JiejianError
from product.backend.infra.runtime.serve_lock import ServeLock


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


def test_cli_scope_rejects_existing_controller_before_constructing_application(tmp_path, monkeypatch) -> None:
    from product.backend.cli import bootstrap

    var_dir = tmp_path / "var"
    constructor = Mock(side_effect=AssertionError("不得创建第二个 ApplicationCore"))
    monkeypatch.setattr("product.backend.composition.ApplicationCore", constructor)
    monkeypatch.setattr(bootstrap, "runtime_settings", lambda _context: SimpleNamespace(var_dir=var_dir))
    owner = ServeLock.acquire(var_dir)
    try:
        with pytest.raises(JiejianError) as raised:
            with bootstrap.application_scope(SimpleNamespace(), environ={}):
                pytest.fail("已有控制者时不能进入应用作用域")
        assert raised.value.code == "WORKSPACE_ALREADY_CONTROLLED"
        constructor.assert_not_called()
    finally:
        owner.release()
