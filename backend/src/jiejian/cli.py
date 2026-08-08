"""界鉴命令行入口：只解析输入、调用服务并序列化结果。"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import NoReturn

import typer

from .config import Settings, load_settings
from .doctor import human_lines, run_doctor
from .domain.models import RunVerdict
from .errors import ErrorCode, JiejianError
from .artifacts import load_report
from .inputs import load_contract, load_project_bundle
from .logging import configure_logging
from .services import RunService

app = typer.Typer(
    name="jiejian",
    help="界鉴：安全意图差分验证与交付门禁",
    no_args_is_help=True,
    add_completion=False,
)
project_app = typer.Typer(help="项目输入校验", no_args_is_help=True)
contract_app = typer.Typer(help="契约输入校验", no_args_is_help=True)
app.add_typer(project_app, name="project")
app.add_typer(contract_app, name="contract")


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


@project_app.command("validate")
def project_validate_command(path: Path) -> None:
    """离线校验项目、Flow、默认 Contract 及交叉引用。"""

    try:
        bundle = load_project_bundle(path)
        _emit_json(
            {
                "schema_version": "1",
                "kind": "project",
                "valid": True,
                "project_id": bundle.project.id,
                "flow_id": bundle.flow.id,
                "contract_id": bundle.contract.id,
            }
        )
    except JiejianError as exc:
        _fail(exc)


@contract_app.command("validate")
def contract_validate_command(path: Path) -> None:
    """离线校验独立 Contract Schema。"""

    try:
        contract = load_contract(path)
        _emit_json(
            {
                "schema_version": "1",
                "kind": "contract",
                "valid": True,
                "contract_id": contract.id,
                "version": contract.version,
                "status": contract.status.value,
            }
        )
    except JiejianError as exc:
        _fail(exc)


@app.command("run")
def run_command(
    context: typer.Context,
    project_path: Path,
    contract_path: Path = typer.Option(..., "--contract", help="显式契约文件"),
) -> None:
    """同步执行安全验证并写入不可变 JSON 产物。"""

    try:
        settings = _runtime_settings(context)
        result = RunService(settings.var_dir).run(
            project_path,
            contract_path=contract_path,
        )
        _emit_json(result.model_dump(mode="json"))
    except JiejianError as exc:
        _fail(exc)


@app.command("report")
def report_command(
    context: typer.Context,
    run_id: str,
    output_format: str = typer.Option("json", "--format", help="报告格式"),
) -> None:
    """按运行 ID 读取阶段 1 JSON 报告。"""

    if output_format.lower() != "json":
        _fail(JiejianError(ErrorCode.INPUT_INVALID, "阶段 1 只支持 JSON 报告"))
    try:
        settings = _runtime_settings(context)
        _emit_json(load_report(settings.var_dir, run_id))
    except JiejianError as exc:
        _fail(exc)


@app.command("ci")
def ci_command(context: typer.Context, project_path: Path) -> None:
    """执行同步门禁，并用 0/1/2 表示 PASS/BLOCK/INCONCLUSIVE。"""

    try:
        settings = _runtime_settings(context)
        result = RunService(settings.var_dir).run(project_path)
        _emit_json(result.model_dump(mode="json"))
        raise typer.Exit(
            code={
                RunVerdict.PASS: 0,
                RunVerdict.BLOCK: 1,
                RunVerdict.INCONCLUSIVE: 2,
            }[result.verdict]
        )
    except JiejianError as exc:
        _fail(exc)


def _runtime_settings(context: typer.Context) -> Settings:
    options: CliOptions = context.obj
    loaded = load_settings(
        config_path=options.config,
        cli_overrides={
            "var_dir": options.var_dir,
            "log_level": options.log_level,
            "trace_id": options.trace_id,
        },
    )
    configure_logging(
        loaded.settings.log_level,
        trace_id=loaded.settings.trace_id,
    )
    return loaded.settings


def _emit_json(payload: object) -> None:
    typer.echo(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def _fail(error: JiejianError) -> NoReturn:
    typer.echo(
        json.dumps(
            {"schema_version": "1", "error": error.to_dict()},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        err=True,
    )
    input_codes = {
        ErrorCode.CFG_FILE.value,
        ErrorCode.CFG_INVALID.value,
        ErrorCode.INPUT_FILE.value,
        ErrorCode.INPUT_INVALID.value,
        ErrorCode.INPUT_PATH.value,
        ErrorCode.SECRET_MISSING.value,
        ErrorCode.REPORT_NOT_FOUND.value,
    }
    safety_codes = {
        ErrorCode.SCOPE_URL.value,
        ErrorCode.SCOPE_HOST.value,
        ErrorCode.SCOPE_PORT.value,
        ErrorCode.SCOPE_PRIVATE_NETWORK.value,
        ErrorCode.SCOPE_REDIRECT.value,
        ErrorCode.EXEC_BUDGET.value,
        ErrorCode.EXEC_RESPONSE_TOO_LARGE.value,
    }
    raise typer.Exit(
        code=3 if error.code in input_codes else 5 if error.code in safety_codes else 4
    )


def main() -> None:
    app(prog_name="jiejian")
