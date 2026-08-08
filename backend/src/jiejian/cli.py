"""界鉴阶段 0 命令行入口。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import typer

from .doctor import human_lines, run_doctor

app = typer.Typer(
    name="jiejian",
    help="界鉴：安全意图差分验证与交付门禁（阶段 0）",
    no_args_is_help=True,
    add_completion=False,
)


@dataclass(frozen=True, slots=True)
class CliOptions:
    config: Path | None
    var_dir: Path | None
    log_level: str | None
    trace_id: str | None


@app.callback()
def root(
    context: typer.Context,
    config: Path | None = typer.Option(None, "--config", help="显式配置文件"),
    var_dir: Path | None = typer.Option(None, "--var-dir", help="运行态目录"),
    log_level: str | None = typer.Option(None, "--log-level", help="日志级别"),
    trace_id: str | None = typer.Option(None, "--trace-id", help="调用追踪 ID"),
) -> None:
    """加载所有子命令共享的 CLI 覆盖项。"""

    context.obj = CliOptions(config, var_dir, log_level, trace_id)


@app.command("doctor")
def doctor_command(
    context: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="输出稳定 JSON"),
) -> None:
    """检查阶段 0 的本机运行条件。"""

    options: CliOptions = context.obj
    overrides = {
        "var_dir": options.var_dir,
        "log_level": options.log_level,
        "trace_id": options.trace_id,
    }
    report = run_doctor(config_path=options.config, cli_overrides=overrides)
    if json_output:
        typer.echo(report.model_dump_json())
    else:
        for line in human_lines(report):
            typer.echo(line)
    raise typer.Exit(code=0 if report.ok else 1)


def main() -> None:
    app(prog_name="jiejian")
