# CLI 组合入口
# 装配 Typer 命令组并保持统一参数、错误和退出语义，不承载领域实现。

from __future__ import annotations

from pathlib import Path

import typer

from product.backend.cli.bootstrap import CliOptions
from product.backend.cli.presentation import configure_presentation
from product.backend.cli.commands.contracts import contract_assessment_command, contract_derive_command, contract_diff_command, contract_draft_command, contract_history_command, contract_requirement_add_command, contract_revise_command, contract_transition_command, contract_validate_command, contract_workspace_command, contract_drift_command
from product.backend.cli.commands.projects import project_validate_command
from product.backend.cli.commands.recordings import recording_finalize_command, recording_replay_command, recording_review_command, recording_start_command, recording_status_command
from product.backend.cli.commands.results import ci_command, report_command
from product.backend.cli.commands.gating import baseline_accept_command, gate_evaluate_command, gate_result_command
from product.backend.cli.commands.runs import run_command
from product.backend.cli.commands.system import doctor_command, serve_command
from product.backend.cli.commands.guide import guide_command


app = typer.Typer(
    name="jiejian",
    help="界鉴命令行：接入应用、确认权限规则并查看检查结果。",
    no_args_is_help=False,
    invoke_without_command=True,
    add_completion=False,
    rich_markup_mode="rich",
)
project_app = typer.Typer(help="查看和校验应用配置", invoke_without_command=True)
contract_app = typer.Typer(help="管理高级权限契约", invoke_without_command=True)
recording_app = typer.Typer(help="录制并确认业务流程", invoke_without_command=True)
baseline_app = typer.Typer(help="管理回归基线", invoke_without_command=True)
gate_app = typer.Typer(help="评估交付门禁", invoke_without_command=True)
app.add_typer(project_app, name="project", rich_help_panel="高级")
app.add_typer(contract_app, name="contract", rich_help_panel="高级")
app.add_typer(recording_app, name="recording", rich_help_panel="常用操作")
app.add_typer(baseline_app, name="baseline", rich_help_panel="高级")
app.add_typer(gate_app, name="gate", rich_help_panel="高级")


def root(
    context: typer.Context,
    config: Path | None = typer.Option(None, "--config", help="显式配置文件"),
    var_dir: Path | None = typer.Option(None, "--var-dir", help="运行态目录"),
    log_level: str | None = typer.Option(None, "--log-level", help="日志级别"),
    trace_id: str | None = typer.Option(None, "--trace-id", help="调用追踪 ID"),
    json_output: bool = typer.Option(False, "--json", help="强制机器 JSON 输出"),
    human_output: bool = typer.Option(False, "--human", help="强制人类可读输出"),
    verbose: bool = typer.Option(False, "--verbose", help="在人类可读模式显示技术详情"),
) -> None:
    """加载所有子命令共享的 CLI 覆盖项。"""

    if json_output and human_output:
        raise typer.BadParameter("--json 与 --human 不能同时使用")
    if verbose and (json_output or context.invoked_subcommand == "ci"):
        raise typer.BadParameter("--verbose 只能用于普通人类可读输出")
    presentation = "json" if json_output else "human" if human_output or verbose else "auto"
    machine_only = context.invoked_subcommand == "ci"
    context.obj = CliOptions(
        config,
        var_dir,
        log_level,
        trace_id,
        presentation=presentation,
        machine_only=machine_only,
        verbose=verbose,
    )
    context.meta["presentation_mode"] = presentation
    context.meta["machine_only"] = machine_only
    configure_presentation(presentation, machine_only=machine_only, verbose=verbose)
    if context.invoked_subcommand is None:
        typer.echo("界鉴命令行")
        typer.echo("")
        typer.echo("第一次使用：jiejian guide")
        typer.echo("检查环境：jiejian doctor")
        typer.echo("完整帮助：jiejian --help")


def _group_help(context: typer.Context) -> None:
    if context.invoked_subcommand is None:
        typer.echo(context.get_help())


project_app.callback()(_group_help)
contract_app.callback()(_group_help)
recording_app.callback()(_group_help)
baseline_app.callback()(_group_help)
gate_app.callback()(_group_help)


app.command("serve", help="打开图形界面", rich_help_panel="常用操作")(serve_command)
app.callback()(root)
app.command("guide", help="打开新手引导", rich_help_panel="常用操作")(guide_command)
app.command("doctor", help="检查运行环境", rich_help_panel="常用操作")(doctor_command)

project_app.command("validate")(project_validate_command)

contract_app.command("validate")(contract_validate_command)
contract_app.command("workspace")(contract_workspace_command)
contract_app.command("requirement-add")(contract_requirement_add_command)
contract_app.command("derive")(contract_derive_command)
contract_app.command("draft")(contract_draft_command)
contract_app.command("revise")(contract_revise_command)
contract_app.command("transition")(contract_transition_command)
contract_app.command("assessment")(contract_assessment_command)
contract_app.command("diff")(contract_diff_command)
contract_app.command("drift")(contract_drift_command)
contract_app.command("history")(contract_history_command)

recording_app.command("start")(recording_start_command)
recording_app.command("status")(recording_status_command)
recording_app.command("review")(recording_review_command)
recording_app.command("finalize")(recording_finalize_command)
recording_app.command("replay")(recording_replay_command)

app.command("run", help="开始权限检查", rich_help_panel="常用操作")(run_command)
app.command("report", help="查看检查报告", rich_help_panel="常用操作")(report_command)
app.command("ci", help="在 CI 中执行检查", rich_help_panel="自动化")(ci_command)
baseline_app.command("accept")(baseline_accept_command)
gate_app.command("evaluate")(gate_evaluate_command)
gate_app.command("result")(gate_result_command)


def main() -> None:
    app(prog_name="jiejian")
