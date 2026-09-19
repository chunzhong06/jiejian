# 验证命令行入口中的用户可见信息呈现。

from __future__ import annotations

import json

import pytest
import typer
from typer.testing import CliRunner

from product.backend.cli.app import app
from product.backend.cli.presentation import configure_presentation, emit_human, fail
from product.backend.core.errors import ErrorCode, JiejianError


def test_machine_error_is_one_redacted_object_with_recovery(capsys) -> None:
    configure_presentation("json")
    try:
        with pytest.raises(typer.Exit) as raised:
            fail(JiejianError(ErrorCode.WORKSPACE_ALREADY_CONTROLLED, "运行目录正在使用",
                             details={"password": "synthetic-sensitive-value"}))
        assert raised.value.exit_code == 4
        captured = capsys.readouterr()
        assert captured.err == ""
        assert "synthetic-sensitive-value" not in captured.out
        payload = json.loads(captured.out)
        assert set(payload) == {"schema_version", "kind", "status", "data", "next_actions", "warnings", "error"}
        assert payload["schema_version"] == "1"
        assert payload["kind"] == payload["status"] == "error"
        assert payload["error"]["error_code"] == "WORKSPACE_ALREADY_CONTROLLED"
        assert payload["error"]["trace_id"].startswith("cli-")
        assert payload["error"]["recovery"]
    finally:
        configure_presentation("auto", machine_only=False)


def test_human_result_never_prints_internal_details(capsys) -> None:
    payload = {
        "schema_version": "1",
        "run_id": "run_demo",
        "verdict": "PASS",
        "lifecycle": "COMPLETED",
        "internal_marker": {"kept": ["one", "two"]},
    }
    configure_presentation("human")
    emit_human(payload)
    ordinary = capsys.readouterr().out
    configure_presentation("auto")

    assert ordinary.startswith("界鉴检查\n")
    assert "高级：技术详情" not in ordinary
    assert "run_demo" not in ordinary
    assert "internal_marker" not in ordinary


def test_verbose_is_not_a_public_option() -> None:
    result = CliRunner().invoke(app, ["--json", "--verbose", "system", "doctor"])

    assert result.exit_code != 0
    assert "--verbose" in result.stderr


def test_human_error_recovery_is_category_specific(capsys) -> None:
    configure_presentation("human")
    try:
        with pytest.raises(typer.Exit) as raised:
            fail(JiejianError(ErrorCode.SCOPE_URL, "目标 URL 不在授权范围"))
        assert raised.value.exit_code == 5
        output = capsys.readouterr().err
        assert "授权目标范围" in output
        assert "输入文件路径" not in output
    finally:
        configure_presentation("auto", machine_only=False)
