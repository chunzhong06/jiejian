# =============================================================================
# 持续权限验证 CLI 组合入口
#
# 定位
#   装配与 GUI 同步的普通任务命令树和本地维护入口。
#
# 职责
#   解析全局展示参数｜注册产品命令｜统一运行环境失败出口
#
# 边界
#   命令入口不承载业务实现，不建立第二个 ApplicationCore 或后台 daemon。
# =============================================================================

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import typer

from product.backend import __version__
from product.backend.cli.bootstrap import CliOptions
from product.backend.cli.localization import configure_cli_localization
from product.backend.cli.commands.control import (
    application_list_command,
    application_remove_command,
    application_show_command,
    check_cancel_command,
    check_prepare_command,
    check_preview_command,
    check_run_command,
    history_command,
    result_report_command,
    result_show_command,
    source_change_list_command,
    source_change_show_command,
    status_command,
)
from product.backend.cli.commands.system import (
    doctor_command,
    maintenance_clean_all_command,
    maintenance_clean_assistant_command,
    maintenance_clean_logs_command,
    maintenance_clean_temporary_command,
    maintenance_repair_command,
    serve_command,
)
from product.backend.cli.presentation import configure_presentation
from product.backend.core.errors import JiejianError
from product.backend.infra.runtime.process.identity import require_python_environment


configure_cli_localization()

app = typer.Typer(
    name="jiejian",
    help="界鉴命令行：接入应用、准备检查并查看可信结果。",
    no_args_is_help=False,
    invoke_without_command=True,
    add_completion=False,
    rich_markup_mode="rich",
)
application_group = typer.Typer(help="查看和移除已经接入的 Web 应用", invoke_without_command=True)
check_group = typer.Typer(help="确认权限要求并提交检查", invoke_without_command=True)
change_group = typer.Typer(help="查看 Agent 代码变化及其权限影响", invoke_without_command=True)
result_group = typer.Typer(help="查看可信检查结果和报告", invoke_without_command=True)
system_group = typer.Typer(help="检查运行环境和执行显式维护", invoke_without_command=True)

clean_group = typer.Typer(help="清理本地可删除内容", invoke_without_command=True)


def _version_callback(value: bool) -> None:
    """产品版本只从后端包真源输出，不建立 CLI 独立版本。"""

    if value:
        typer.echo(__version__)
        raise typer.Exit()


def root(
    context: typer.Context,
    var_dir: Path | None = typer.Option(None, "--var-dir", hidden=True),
    json_output: bool = typer.Option(False, "--json", help="强制 Machine JSON 输出"),
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="显示界鉴产品版本并退出",
    ),
) -> None:
    """加载共享覆盖项；无子命令时直接展示统一终端工作台。"""

    presentation = "json" if json_output else "human"
    context.obj = CliOptions(
        var_dir,
        f"cli-{uuid4().hex}",
        presentation=presentation,
        machine_only=False,
    )
    context.meta["presentation_mode"] = presentation
    context.meta["machine_only"] = False
    configure_presentation(presentation, machine_only=False)
    if context.invoked_subcommand is None:
        status_command(context, project_id=None)


def _group_help(context: typer.Context) -> None:
    if context.invoked_subcommand is None:
        typer.echo(context.get_help())


app.callback()(root)
for group in (
    application_group,
    change_group,
    check_group,
    result_group,
    system_group,
    clean_group,
):
    group.callback()(_group_help)

app.add_typer(application_group, name="application", rich_help_panel="普通任务")
app.add_typer(change_group, name="change", rich_help_panel="普通任务")
app.add_typer(check_group, name="check", rich_help_panel="普通任务")
app.add_typer(result_group, name="result", rich_help_panel="普通任务")
app.add_typer(system_group, name="system", rich_help_panel="运行与维护")
app.command("status", help="查看持续验证工作区和全部待办", rich_help_panel="普通任务")(status_command)
app.command("serve", help="打开图形界面", rich_help_panel="图形界面")(serve_command)
app.command("history", help="查看同一应用的历史变化", rich_help_panel="普通任务")(history_command)

application_group.command("list")(application_list_command)
application_group.command("show")(application_show_command)
application_group.command("remove")(application_remove_command)
change_group.command("list")(source_change_list_command)
change_group.command("show")(source_change_show_command)
check_group.command("prepare")(check_prepare_command)
check_group.command("preview")(check_preview_command)
check_group.command("run")(check_run_command)
check_group.command("cancel")(check_cancel_command)

result_group.command("show")(result_show_command)
result_group.command("report")(result_report_command)

system_group.add_typer(clean_group, name="clean")
system_group.command("doctor")(doctor_command)
system_group.command("repair")(maintenance_repair_command)
clean_group.command("assistant")(maintenance_clean_assistant_command)
clean_group.command("logs")(maintenance_clean_logs_command)
clean_group.command("temporary")(maintenance_clean_temporary_command)
clean_group.command("all")(maintenance_clean_all_command)

def main() -> None:
    if "doctor" not in sys.argv[1:] and "--version" not in sys.argv[1:]:
        try:
            require_python_environment()
        except JiejianError as exc:
            typer.echo("界鉴运行环境不可信，已拒绝启动。", err=True)
            details = exc.to_dict().get("details", {})
            for issue in details.get("issues", ()):
                typer.echo(f"- {issue}", err=True)
            typer.echo(
                "仓库开发请使用 .\\scripts\\dev.ps1 start；正式运行请使用 .\\start.cmd。",
                err=True,
            )
            raise SystemExit(40) from None
    app(prog_name="jiejian")
