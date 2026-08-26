# 验证命令行入口中的用户可见信息呈现。

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import typer
from typer.testing import CliRunner

from product.backend.cli.commands import guide as guide_commands
from product.backend.cli.commands import results as result_commands
from product.backend.cli.app import app
from product.backend.cli.presentation import configure_presentation, emit_human, emit_result_presentation, fail
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


def test_ci_forces_machine_mode_even_when_human_is_requested(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        ["--var-dir", str(tmp_path / "var"), "--human", "ci", "missing.yaml"],
    )

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


def test_result_presentation_uses_surface_and_real_effect_language(capsys) -> None:
    result = SimpleNamespace(
        verdict="BLOCK",
        run_lifecycle="COMPLETED",
        headline="发现权限问题",
        scope_statement="可信执行与观察事实确认存在不符合权限预期的真实影响。",
        checked_count=1,
        safe_count=0,
        problem_count=1,
        inconclusive_count=0,
        uncovered_count=0,
        execution_problem=None,
        issues=(SimpleNamespace(
            finding_id="finding_demo",
            title="成员账号不应对文档执行修改",
            conclusion="发现权限问题",
            explanation="页面或接口虽然显示已拒绝，但外部可信观察确认真实资源已经变化；权限限制没有真正阻止修改，表面拒绝没有阻止真实副作用。",
            verdict=SimpleNamespace(value="VULNERABLE"),
        ),),
        limitations=(),
        run_id="run_demo",
        project_id="project_demo",
    )
    configure_presentation("human")
    emit_result_presentation(result)
    output = capsys.readouterr().out
    configure_presentation("auto")

    assert "发现权限问题" in output
    assert "成员账号不应对文档执行修改" in output
    assert "权限限制没有真正阻止修改" in output
    assert "run_demo" not in output


def test_explicit_json_report_stays_canonical_in_human_mode(monkeypatch, capsys) -> None:
    reports = SimpleNamespace(
        read=lambda run_id, report_id: {
            "run_id": run_id,
            "report_id": report_id,
            "runtime": {"verdict": "BLOCK"},
        }
    )
    application = SimpleNamespace(
        result_presentation=SimpleNamespace(
            build=lambda _run_id: pytest.fail("显式 JSON 不应读取人类结果投影")
        ),
        result_finalizer=SimpleNamespace(
            status=lambda _run_id: SimpleNamespace(base_report_id="report_demo")
        ),
        reports=reports,
    )

    @contextmanager
    def fake_scope(_context):
        yield application

    monkeypatch.setattr(result_commands, "application_scope", fake_scope)
    configure_presentation("human")
    try:
        result_commands.report_command(
            SimpleNamespace(),
            "run_demo",
            output_format="json",
            gate_result_id=None,
            report_id=None,
        )
        payload = json.loads(capsys.readouterr().out)
    finally:
        configure_presentation("auto", machine_only=False)

    assert payload["runtime"]["verdict"] == "BLOCK"
    assert payload["report_id"] == "report_demo"


def test_guide_submits_current_scope_without_profile_choice(monkeypatch, capsys) -> None:
    project = SimpleNamespace(project_id="project_demo", name="演示应用")
    submission = SimpleNamespace(job=SimpleNamespace(job_id="job_demo"))
    application = SimpleNamespace(
        projects=SimpleNamespace(list=lambda: (project,)),
        assistant_guidance=SimpleNamespace(
            get=lambda _project_id: SimpleNamespace(current_scope_runnable=True)
        ),
        checks=SimpleNamespace(
            submit=lambda project_id, **_: (
                submission,
                SimpleNamespace(project_id=project_id),
                (),
            )
        ),
    )

    @contextmanager
    def fake_scope(_context):
        yield application

    monkeypatch.setattr(guide_commands, "application_scope", fake_scope)
    monkeypatch.setattr(guide_commands, "_choose", lambda _title, _items: 0)
    monkeypatch.setattr(guide_commands, "_pause", lambda: None)

    guide_commands._existing_application(SimpleNamespace())
    output = capsys.readouterr().out

    assert "检查已提交" in output
    assert "任务已进入队列：job_demo" in output
    assert "Profile" not in output


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
