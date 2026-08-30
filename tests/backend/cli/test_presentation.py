# 验证命令行入口中的用户可见信息呈现。

from __future__ import annotations

from types import SimpleNamespace

import pytest
import typer
from typer.testing import CliRunner

from product.backend.cli.app import app
from product.backend.cli.presentation import configure_presentation, emit_human, emit_result_presentation, fail
from product.backend.core.errors import ErrorCode, JiejianError
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
            evidence_sources=(
                SimpleNamespace(role="KEY", status="FOUND", label="数据库状态"),
                SimpleNamespace(role="SUPPORTING", status="UNAVAILABLE", label="审计日志"),
            ),
            diagnosis=SimpleNamespace(
                breakpoint_type=SimpleNamespace(value="AUTHORIZATION_LATE"),
                minimal_witness=(
                    SimpleNamespace(kind="PERMISSION_REQUIREMENT", label="权限要求", detail="成员不应导出"),
                    SimpleNamespace(kind="ACTUAL_IDENTITY", label="实际身份", detail="成员账号"),
                    SimpleNamespace(kind="PROTECTED_EFFECT", label="本不该发生的业务后果", detail="归档已经生成"),
                    SimpleNamespace(kind="AUTHORIZATION_CONTINUITY", label="合法授权来源", detail="找不到符合原权限要求的合法授权来源"),
                    SimpleNamespace(kind="BREAKPOINT", label="首个可证明断裂", detail="权限决定发生过晚"),
                    SimpleNamespace(kind="AMPLIFIERS", label="后续扩大影响的行为", detail="后台任务继续执行"),
                    SimpleNamespace(kind="CONFIRMED_IMPACT", label="最终业务影响", detail="归档已经生成"),
                ),
                confirmed_impacts=(
                    SimpleNamespace(
                        kind=SimpleNamespace(value="FINAL_EFFECT"),
                        summary="已确认：最终后果",
                    ),
                ),
            ),
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
    assert "关键来源：数据库状态：已取得" in output
    assert "辅助来源：审计日志：当前不可用" in output
    assert "权限断裂诊断" in output
    assert "首个可证明断裂：权限决定发生过晚" in output
    assert "已确认影响" in output
    assert "FINAL_EFFECT：已确认：最终后果" in output
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
