# =============================================================================
# Web V1 CLI 组合入口
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
    account_cancel_command,
    account_confirm_command,
    account_create_command,
    account_delete_command,
    account_list_command,
    account_preparation_command,
    account_prepare_command,
    account_reset_command,
    account_show_command,
    app_analyze_command,
    app_add_action_command,
    app_add_role_command,
    app_authorize_source_command,
    app_confirm_endpoint_command,
    app_connect_command,
    app_discover_command,
    app_decide_action_command,
    app_decide_role_command,
    app_list_command,
    app_remove_command,
    app_show_command,
    check_cancel_command,
    check_permissions_command,
    check_prepare_command,
    check_preview_command,
    check_run_command,
    check_set_permission_command,
    flow_capture_start_command,
    flow_capture_stop_command,
    flow_finalize_command,
    flow_list_command,
    flow_record_command,
    flow_safety_command,
    flow_show_command,
    history_show_command,
    result_evidence_command,
    result_repair_command,
    result_report_command,
    result_reports_command,
    result_show_command,
    settings_show_command,
    settings_test_command,
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
app_group = typer.Typer(help="接入和理解本地 Web 应用", invoke_without_command=True)
account_group = typer.Typer(help="准备测试账号", invoke_without_command=True)
flow_group = typer.Typer(help="准备业务流程与真实结果观察", invoke_without_command=True)
check_group = typer.Typer(help="确认权限要求并提交检查", invoke_without_command=True)
result_group = typer.Typer(help="查看可信检查结果和报告", invoke_without_command=True)
history_group = typer.Typer(help="查看同一应用的历史变化", invoke_without_command=True)
settings_group = typer.Typer(help="查看和测试模型辅助设置", invoke_without_command=True)
system_group = typer.Typer(help="检查运行环境和执行显式维护", invoke_without_command=True)

clean_group = typer.Typer(help="清理本地可删除内容", invoke_without_command=True)


def _version_callback(value: bool) -> None:
    """产品版本只从后端包真源输出，不建立 CLI 独立版本。"""

    if value:
        typer.echo(__version__)
        raise typer.Exit()


def root(
    context: typer.Context,
    config: Path | None = typer.Option(None, "--config", help="显式配置文件"),
    var_dir: Path | None = typer.Option(None, "--var-dir", help="运行态目录"),
    log_level: str | None = typer.Option(None, "--log-level", help="日志级别"),
    trace_id: str | None = typer.Option(None, "--trace-id", help="调用追踪 ID"),
    json_output: bool = typer.Option(False, "--json", help="强制 Machine JSON 输出"),
    human_output: bool = typer.Option(False, "--human", help="强制人类可读输出"),
    verbose: bool = typer.Option(False, "--verbose", help="在人类模式追加技术引用"),
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="显示界鉴产品版本并退出",
    ),
) -> None:
    """加载共享覆盖项；无子命令时直接展示统一终端工作台。"""

    if json_output and human_output:
        raise typer.BadParameter("--json 与 --human 不能同时使用")
    if verbose and json_output:
        raise typer.BadParameter("--verbose 只能用于普通人类可读输出")
    presentation = "json" if json_output else "human" if human_output or verbose else "auto"
    context.obj = CliOptions(
        config,
        var_dir,
        log_level,
        trace_id or f"cli-{uuid4().hex}",
        presentation=presentation,
        machine_only=False,
        verbose=verbose,
    )
    context.meta["presentation_mode"] = presentation
    context.meta["machine_only"] = False
    configure_presentation(presentation, machine_only=False, verbose=verbose)
    if context.invoked_subcommand is None:
        status_command(context, project_id=None)


def _group_help(context: typer.Context) -> None:
    if context.invoked_subcommand is None:
        typer.echo(context.get_help())


app.callback()(root)
for group in (
    app_group,
    account_group,
    flow_group,
    check_group,
    result_group,
    history_group,
    settings_group,
    system_group,
    clean_group,
):
    group.callback()(_group_help)

app.add_typer(app_group, name="app", rich_help_panel="普通任务")
app.add_typer(account_group, name="account", rich_help_panel="普通任务")
app.add_typer(flow_group, name="flow", rich_help_panel="普通任务")
app.add_typer(check_group, name="check", rich_help_panel="普通任务")
app.add_typer(result_group, name="result", rich_help_panel="普通任务")
app.add_typer(history_group, name="history", rich_help_panel="普通任务")
app.add_typer(settings_group, name="settings", rich_help_panel="普通任务")
app.add_typer(system_group, name="system", rich_help_panel="运行与维护")
app.command("status", help="查看六步状态和唯一下一步", rich_help_panel="普通任务")(status_command)
app.command("serve", help="打开图形界面", rich_help_panel="图形界面")(serve_command)

app_group.command("list")(app_list_command)
app_group.command("show")(app_show_command)
app_group.command("connect")(app_connect_command)
app_group.command("remove")(app_remove_command)
app_group.command("discover-endpoints")(app_discover_command)
app_group.command("confirm-endpoint")(app_confirm_endpoint_command)
app_group.command("authorize-source")(app_authorize_source_command)
app_group.command("analyze")(app_analyze_command)
app_group.command("decide-role")(app_decide_role_command)
app_group.command("decide-action")(app_decide_action_command)
app_group.command("add-role")(app_add_role_command)
app_group.command("add-action")(app_add_action_command)

account_group.command("list")(account_list_command)
account_group.command("show")(account_show_command)
account_group.command("create")(account_create_command)
account_group.command("prepare")(account_prepare_command)
account_group.command("preparation")(account_preparation_command)
account_group.command("confirm")(account_confirm_command)
account_group.command("cancel")(account_cancel_command)
account_group.command("reset")(account_reset_command)
account_group.command("delete")(account_delete_command)

flow_group.command("list")(flow_list_command)
flow_group.command("record")(flow_record_command)
flow_group.command("show")(flow_show_command)
flow_group.command("capture-start")(flow_capture_start_command)
flow_group.command("capture-stop")(flow_capture_stop_command)
flow_group.command("finalize")(flow_finalize_command)
flow_group.command("safety")(flow_safety_command)

check_group.command("permissions")(check_permissions_command)
check_group.command("set-permission")(check_set_permission_command)
check_group.command("prepare")(check_prepare_command)
check_group.command("preview")(check_preview_command)
check_group.command("run")(check_run_command)
check_group.command("cancel")(check_cancel_command)

result_group.command("show")(result_show_command)
result_group.command("evidence")(result_evidence_command)
result_group.command("reports")(result_reports_command)
result_group.command("report")(result_report_command)
result_group.command("repair")(result_repair_command)
history_group.command("show")(history_show_command)
settings_group.command("show")(settings_show_command)
settings_group.command("test")(settings_test_command)

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
