"""界鉴命令行入口：只解析输入、调用服务并序列化结果。"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import time
from typing import NoReturn
from uuid import uuid4

from functools import partial

import typer

from .domain.lifecycle import RunLifecycle, RunVerdict
from .domain.verification import RunResult
from .errors import ErrorCode, JiejianError
from .runtime.config import Settings, load_settings
from .runtime.diagnostics import human_lines, run_doctor
from .runtime.logging import configure_logging
from .protocols import (
    ExecutionBudgetV1,
    ExecutionProjectSnapshotV1,
    RunnerResultType,
)
from .storage import (
    StorageUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
    default_database_path,
    upgrade_database,
)
from .verification.artifacts import load_report
from .verification.inputs import ProjectBundle, load_contract, load_project_bundle
from .worker import (
    ExecutionRequestStore,
    ExecutionSubmissionService,
    PersistedExecutionRequestV1,
    SubmitExecutionV1,
    WorkerDispatcher,
    required_secret_names,
)

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
    """提交持久任务并等待隔离 Runner 的已发布结果。"""

    try:
        settings = _runtime_settings(context)
        bundle = load_project_bundle(project_path, contract_path=contract_path)
        result = _run_persisted_job(settings, bundle)
        _emit_json(result.model_dump(mode="json"))
    except JiejianError as exc:
        _fail(exc)


@app.command("report")
def report_command(
    context: typer.Context,
    run_id: str,
    output_format: str = typer.Option("json", "--format", help="报告格式"),
) -> None:
    """按运行 ID 读取完整性校验后的 JSON 报告。"""

    if output_format.lower() != "json":
        _fail(JiejianError(ErrorCode.INPUT_INVALID, "阶段 1 只支持 JSON 报告"))
    try:
        settings = _runtime_settings(context)
        _require_published_completion(settings.var_dir, run_id)
        _emit_json(load_report(settings.var_dir, run_id))
    except JiejianError as exc:
        _fail(exc)


@app.command("ci")
def ci_command(context: typer.Context, project_path: Path) -> None:
    """提交持久门禁任务，并用 0/1/2 表示安全结论。"""

    try:
        settings = _runtime_settings(context)
        bundle = load_project_bundle(project_path)
        result = _run_persisted_job(settings, bundle)
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


def _run_persisted_job(settings: Settings, bundle: ProjectBundle) -> RunResult:
    var_dir = settings.var_dir.resolve()
    database_path = default_database_path(var_dir)
    upgrade_database(database_path)
    engine = create_sqlite_engine(database_path)
    try:
        factory = create_session_factory(engine)
        uow_factory = partial(StorageUnitOfWork, factory)
        request = _persisted_request(bundle)
        secret_names = required_secret_names(request)
        known_secrets = _required_secrets(secret_names)
        submission = ExecutionSubmissionService(
            uow_factory,
            ExecutionRequestStore(var_dir),
        ).submit(
            SubmitExecutionV1(
                request=request,
                idempotency_key=f"cli-{uuid4().hex}",
                max_attempts=3,
                available_at_us=time.time_ns() // 1_000,
                now_us=time.time_ns() // 1_000,
            ),
            known_secrets=known_secrets,
        )
        dispatcher = WorkerDispatcher(
            var_dir=var_dir,
            uow_factory=uow_factory,
            environ=os.environ,
        )
        process = dispatcher.start(
            job_id=submission.job.job_id,
            lease_owner=f"worker-{uuid4().hex}",
            secret_names=secret_names,
        )
        staged = dispatcher.wait(
            submission.job.job_id,
            process,
            known_secrets=known_secrets,
            timeout_seconds=(request.budget.max_duration_us * 3) / 1_000_000 + 60,
        )
        if staged.result.result_type is RunnerResultType.SUCCESS:
            return _published_run_result(
                var_dir,
                staged.paths.staging_dir,
                staged.result.run_id,
            )
        if staged.result.result_type is RunnerResultType.SAFETY_STOPPED:
            raise JiejianError(
                staged.result.reason_codes[0],
                "Runner 因安全边界主动停止",
            )
        if staged.result.result_type is RunnerResultType.CANCELLED:
            raise JiejianError(ErrorCode.EXEC_CANCELLED, "运行已经安全取消")
        error_code = (
            staged.result.error.code
            if staged.result.error is not None
            else ErrorCode.RUNNER_RESULT_MISSING.value
        )
        raise JiejianError(error_code, "Runner 执行未形成安全结论")
    finally:
        engine.dispose()


def _persisted_request(bundle: ProjectBundle) -> PersistedExecutionRequestV1:
    project = bundle.project
    snapshot = ExecutionProjectSnapshotV1(
        schema_version="1",
        project_id=project.id,
        project_name=project.name,
        target=project.target,
        identities=project.identities,
        resources=project.resources,
        flow=bundle.flow,
        contract=bundle.contract,
        owner_observer_enabled=project.owner_observer_enabled,
        mutation_seed=project.mutation_seed,
    )
    duration = min(
        max(int(project.target.timeout_seconds * project.target.max_requests * 1_000_000), 1),
        3_600_000_000,
    )
    return PersistedExecutionRequestV1(
        schema_version="1",
        budget=ExecutionBudgetV1(
            schema_version="1",
            max_requests=project.target.max_requests,
            request_timeout_us=int(project.target.timeout_seconds * 1_000_000),
            max_duration_us=duration,
            max_response_bytes=project.target.max_response_bytes,
            max_parallel_cases=1,
        ),
        project_snapshot=snapshot,
    )


def _required_secrets(names: tuple[str, ...]) -> tuple[str, ...]:
    values: list[str] = []
    for name in names:
        value = os.environ.get(name)
        if not value:
            raise JiejianError(
                ErrorCode.SECRET_MISSING,
                "身份环境变量未设置",
            )
        values.append(value)
    return tuple(values)


def _published_run_result(
    var_dir: Path,
    staging_dir: Path,
    run_id: str,
) -> RunResult:
    report_path = staging_dir / "artifacts" / "report" / "report.json"
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        return RunResult.model_validate(
            {
                "schema_version": "1",
                "run_id": report["run_id"],
                "project_id": report["project_id"],
                "engine_version": report["engine_version"],
                "verdict": report["verdict"],
                "reason_codes": report["reason_codes"],
                "evidence": report["evidence"],
                "artifact_dir": str(
                    var_dir / "projects" / report["project_id"] / "runs" / run_id
                ),
            }
        )
    except (OSError, json.JSONDecodeError, KeyError, ValueError):
        raise JiejianError(
            ErrorCode.RUNNER_PROTOCOL_INVALID,
            "Runner 已发布报告不可读取",
        ) from None


def _require_published_completion(var_dir: Path, run_id: str) -> None:
    manifests = list(
        var_dir.resolve().glob(
            f"projects/*/runs/{run_id}/publication-manifest.json"
        )
    )
    if not manifests:
        return
    if len(manifests) != 1:
        raise JiejianError(ErrorCode.REPORT_NOT_FOUND, "未找到唯一已发布运行")
    database_path = default_database_path(var_dir.resolve())
    if not database_path.is_file():
        raise JiejianError(ErrorCode.REPORT_NOT_FOUND, "已发布运行尚未完成持久化")
    engine = create_sqlite_engine(database_path)
    try:
        factory = create_session_factory(engine)
        with StorageUnitOfWork(factory) as work:
            run = work.runs.get(run_id)
        if run is None or run.lifecycle is not RunLifecycle.COMPLETED:
            raise JiejianError(ErrorCode.REPORT_NOT_FOUND, "已发布运行尚未完成持久化")
    finally:
        engine.dispose()


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
    if error.code == ErrorCode.EXEC_CANCELLED.value:
        raise typer.Exit(code=130)
    raise typer.Exit(
        code=3 if error.code in input_codes else 5 if error.code in safety_codes else 4
    )


def main() -> None:
    app(prog_name="jiejian")
