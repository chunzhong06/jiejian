from __future__ import annotations

import json
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from product.backend.cli.app import app
from product.backend.cli.presentation import configure_presentation, emit_human, fail
from product.backend.core.errors import ErrorCode, JiejianError


PROFILE = Path(__file__).parents[2] / "samples" / "http" / "vulnerable" / "profile.json"


def test_non_tty_auto_mode_keeps_project_result_as_json() -> None:
    result = CliRunner().invoke(app, ["project", "validate", str(PROFILE)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["kind"] == "project"
    assert "项目检查" not in result.stdout


def test_human_mode_projects_a_result_without_json_or_logo() -> None:
    result = CliRunner().invoke(
        app, ["--human", "project", "validate", str(PROFILE)]
    )

    assert result.exit_code == 0
    assert result.stdout.startswith("界鉴项目检查\n")
    assert "名称：permission-check-vulnerable" in result.stdout
    assert not result.stdout.lstrip().startswith("{")
    assert "JIEJIAN" not in result.stdout


def test_json_mode_is_explicit_and_stable() -> None:
    result = CliRunner().invoke(
        app, ["--json", "project", "validate", str(PROFILE)]
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["valid"] is True
    assert "项目检查" not in result.stdout


def test_human_error_is_separate_from_machine_error() -> None:
    human = CliRunner().invoke(app, ["--human", "project", "validate", "missing.yaml"])
    machine = CliRunner().invoke(app, ["--json", "project", "validate", "missing.yaml"])

    assert human.exit_code == machine.exit_code == 3
    assert "输入信息不可用" in human.stderr
    assert "原因" in human.stderr
    assert "如何解决" in human.stderr
    assert "错误代码" in human.stderr
    assert "INPUT_FILE" in human.stderr
    assert human.stdout == ""
    assert json.loads(machine.stderr)["error"]["code"] == "INPUT_FILE"


def test_ci_forces_machine_mode_even_when_human_is_requested() -> None:
    result = CliRunner().invoke(app, ["--human", "ci", "missing.yaml"])

    assert result.exit_code == 4
    assert result.stdout == ""
    assert json.loads(result.stderr)["error"]["code"] == "EXECUTION_PROFILE_INVALID"


def test_human_result_puts_unknown_fields_under_technical_details(capsys) -> None:
    emit_human(
        {
            "schema_version": "1",
            "run_id": "run_demo",
            "verdict": "PASS",
            "lifecycle": "COMPLETED",
            "internal_marker": "kept",
        }
    )

    output = capsys.readouterr().out
    assert output.startswith("界鉴检查\n")
    assert "运行标识：run_demo" in output
    assert "高级：技术详情" in output
    assert "internal_marker：kept" in output
    assert "lifecycle：" not in output


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
