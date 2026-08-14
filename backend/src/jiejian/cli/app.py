# =============================================================================
# CLI 组合入口
#
# 定位
#   稳定 jiejian.cli:main 与各能力命令组之间的 Typer 装配边界
#
# 职责
#   注册命令和参数｜建立共享选项｜保持统一错误与退出语义
#
# 调用链
#   jiejian.cli:main → Typer app → cli.commands.*
# =============================================================================

from __future__ import annotations

from pathlib import Path

import typer

from .bootstrap import CliOptions
from .commands.contracts import (
    contract_assessment_command,
    contract_derive_command,
    contract_diff_command,
    contract_draft_command,
    contract_history_command,
    contract_requirement_add_command,
    contract_revise_command,
    contract_transition_command,
    contract_validate_command,
    contract_workspace_command,
    contract_drift_command,
)
from .commands.projects import project_validate_command
from .commands.recordings import (
    recording_finalize_command,
    recording_replay_command,
    recording_review_command,
    recording_start_command,
    recording_status_command,
)
from .commands.results import ci_command, report_command
from .commands.runs import permission_run_command, run_command
from .commands.system import doctor_command, serve_command


app = typer.Typer(
    name="jiejian",
    help="界鉴：安全意图差分验证与交付门禁",
    no_args_is_help=True,
    add_completion=False,
)
project_app = typer.Typer(help="项目输入校验", no_args_is_help=True)
contract_app = typer.Typer(help="契约输入校验", no_args_is_help=True)
recording_app = typer.Typer(help="浏览器录制与 Flow 审阅", no_args_is_help=True)
app.add_typer(project_app, name="project")
app.add_typer(contract_app, name="contract")
app.add_typer(recording_app, name="recording")


def root(
    context: typer.Context,
    config: Path | None = typer.Option(None, "--config", help="显式配置文件"),
    var_dir: Path | None = typer.Option(None, "--var-dir", help="运行态目录"),
    log_level: str | None = typer.Option(None, "--log-level", help="日志级别"),
    trace_id: str | None = typer.Option(None, "--trace-id", help="调用追踪 ID"),
) -> None:
    """加载所有子命令共享的 CLI 覆盖项。"""

    context.obj = CliOptions(config, var_dir, log_level, trace_id)


app.command("serve")(serve_command)
app.callback()(root)
app.command("doctor")(doctor_command)

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

app.command("run")(run_command)
app.command("permission-run")(permission_run_command)
app.command("report")(report_command)
app.command("ci")(ci_command)


def main() -> None:
    app(prog_name="jiejian")
