# =============================================================================
# 1.1.0 当前 CLI 组合入口
#
# 定位
#   装配 Web 产品启动、环境诊断与本地维护入口。
#
# 职责
#   解析全局展示参数｜注册产品命令｜统一运行环境失败出口
#
# 边界
#   不注册延期的检查、录制、运行、结果或旧权限命令，不建立后台 daemon。
# =============================================================================

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import typer

from product.backend import __version__
from product.backend.cli.bootstrap import CliOptions
from product.backend.cli.localization import configure_cli_localization
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
    help="界鉴命令行：启动本地 Web 产品并检查或维护运行环境。",
    no_args_is_help=False,
    invoke_without_command=True,
    add_completion=False,
    rich_markup_mode="rich",
)
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
    """加载共享覆盖项；无子命令时仅展示当前可用命令。"""

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
        typer.echo(context.get_help())


def _group_help(context: typer.Context) -> None:
    if context.invoked_subcommand is None:
        typer.echo(context.get_help())


app.callback()(root)
for group in (system_group, clean_group):
    group.callback()(_group_help)

app.add_typer(system_group, name="system", rich_help_panel="运行与维护")
app.command("serve", help="打开图形界面", rich_help_panel="图形界面")(serve_command)

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
