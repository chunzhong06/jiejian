from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import typer
from typer.testing import CliRunner

from product.backend.cli.app import app
from product.backend.cli.presentation import configure_presentation, emit_guide_result, emit_human, fail
from product.backend.core.errors import ErrorCode, JiejianError


PROFILE = Path(__file__).parents[3] / "samples" / "web" / "vulnerable" / "profile.json"


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
    machine_error = json.loads(machine.stderr)["error"]
    assert machine_error["code"] == "INPUT_FILE"
    assert machine_error["message"] == "Web 执行配置（WebExecutionProfile）文件不可读取"


def test_ci_forces_machine_mode_even_when_human_is_requested() -> None:
    result = CliRunner().invoke(app, ["--human", "ci", "missing.yaml"])

    assert result.exit_code == 4
    assert result.stdout == ""
    assert json.loads(result.stderr)["error"]["code"] == "EXECUTION_PROFILE_INVALID"


def test_human_result_hides_technical_details_until_verbose(capsys) -> None:
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
    configure_presentation("human", verbose=True)
    emit_human(payload)
    verbose = capsys.readouterr().out
    configure_presentation("auto")

    assert ordinary.startswith("界鉴检查\n")
    assert "高级：技术详情" not in ordinary
    assert "run_demo" not in ordinary
    assert "高级：技术详情" in verbose
    assert "运行标识：run_demo" in verbose
    assert "internal_marker：kept=one、two" in verbose
    assert "{" not in verbose and "}" not in verbose


def test_verbose_and_json_are_rejected_as_ambiguous() -> None:
    result = CliRunner().invoke(app, ["--json", "--verbose", "doctor"])

    assert result.exit_code != 0
    assert "--verbose 只能用于普通人类可读输出" in result.stderr


def test_guide_result_uses_surface_and_real_effect_language(capsys) -> None:
    evidence = SimpleNamespace(
        verdict="VULNERABLE",
        case_snapshot=SimpleNamespace(
            subject_id="attacker",
            action_id="modify",
            resource_ids=("owner-resource",),
        ),
        execution_fact=SimpleNamespace(outcome="DENIED"),
        observation_facts=(SimpleNamespace(effect="CONFIRMED"),),
    )
    result = SimpleNamespace(
        verdict="BLOCK",
        evidence=(evidence,),
        run_id="run_demo",
        reason_codes=(),
    )
    configure_presentation("human")
    emit_guide_result(result)
    output = capsys.readouterr().out
    configure_presentation("auto")

    assert "发现 1 个权限问题" in output
    assert "普通成员修改了不属于自己的资源" in output
    assert "系统表面结果\n└─ 请求被拒绝" in output
    assert "真实结果\n└─ 资源内容已经发生变化" in output
    assert "权限限制没有真正阻止这次操作" in output
    assert "run_demo" not in output


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
