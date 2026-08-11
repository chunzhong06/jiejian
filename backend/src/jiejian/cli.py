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

from .domain.lifecycle import ProjectStatus, RunLifecycle, RunVerdict
from .domain.recording import RecordingState
from .domain.verification import RunResult
from .errors import ErrorCode, JiejianError
from .runtime.config import Settings, load_settings
from .runtime.diagnostics import human_lines, run_doctor
from .runtime.logging import configure_logging
from .protocols import (
    ExecutionBudgetV1,
    ExecutionProjectSnapshotV1,
    RecordingBudgetV1,
    RecordingRunnerRequestV1,
    RecordingSessionRefV1,
    RunnerResultType,
    parse_flow_draft_review_command,
)
from .storage import (
    ProjectRecord,
    StorageUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
    default_database_path,
    upgrade_database,
)
from .verification.artifacts import load_report
from .verification.inputs import ProjectBundle, load_contract, load_project_bundle
from .recording import (
    RecordingApplicationService,
    RecordingRequestStore,
    SubmitRecordingV1,
    RecordingWorkflow,
)
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
recording_app = typer.Typer(help="浏览器录制与 Flow 审阅", no_args_is_help=True)
app.add_typer(project_app, name="project")
app.add_typer(contract_app, name="contract")
app.add_typer(recording_app, name="recording")


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


@recording_app.command("start")
def recording_start_command(
    context: typer.Context,
    project_path: Path,
    identity: list[str] | None = typer.Option(
        None,
        "--identity",
        help="录制身份 ID；可重复指定，默认使用项目全部身份",
    ),
    duration_seconds: int = typer.Option(
        60,
        "--duration-seconds",
        min=1,
        max=3_600,
        help="有界录制时长",
    ),
    headless: bool = typer.Option(
        True,
        "--headless/--headed",
        help="是否无头运行浏览器",
    ),
) -> None:
    """校验项目并提交一次隔离 Recording。"""

    try:
        settings = _runtime_settings(context)
        bundle = load_project_bundle(project_path)
        selected = identity or [item.id for item in bundle.project.identities]
        known = {item.id for item in bundle.project.identities}
        if not selected or len(set(selected)) != len(selected) or any(
            item not in known for item in selected
        ):
            raise JiejianError(ErrorCode.INPUT_INVALID, "录制身份选择无效")
        now_us = time.time_ns() // 1_000
        duration_us = duration_seconds * 1_000_000
        request = RecordingRunnerRequestV1(
            schema_version="1",
            recording_id=f"rec_{uuid4().hex}",
            project_id=bundle.project.id,
            created_at_us=now_us,
            target_scope=bundle.project.target,
            sessions=tuple(
                RecordingSessionRefV1(
                    schema_version="1",
                    identity_id=item,
                    session_ref=f"session_{uuid4().hex}",
                    expires_at_us=now_us + duration_us,
                )
                for item in selected
            ),
            budget=RecordingBudgetV1(
                schema_version="1",
                max_duration_us=duration_us,
                max_contexts=len(selected),
            ),
            headless=headless,
            trace_enabled=False,
        )
        engine, factory = _open_storage(settings)
        try:
            _ensure_project_record(factory, bundle, now_us)
            application = RecordingApplicationService(
                factory,
                RecordingRequestStore(settings.var_dir),
            )
            submission = application.submit(
                SubmitRecordingV1(
                    request=request,
                    flow_id=bundle.flow.id,
                    idempotency_key=f"cli-recording-{uuid4().hex}",
                    max_attempts=3,
                    available_at_us=now_us,
                    now_us=now_us,
                )
            )
            dispatcher = WorkerDispatcher(
                var_dir=settings.var_dir,
                uow_factory=factory,
                environ=os.environ,
            )
            process = dispatcher.start(
                job_id=submission.job.job_id,
                lease_owner=f"recording-worker-{uuid4().hex}",
                secret_names=(),
            )
            dispatcher.wait_recording(
                submission.job.job_id,
                process,
                timeout_seconds=duration_seconds + 30,
            )
            view = RecordingWorkflow(factory).status(request.recording_id)
            _emit_json(
                {
                    "schema_version": "1",
                    "recording_id": request.recording_id,
                    "job_id": submission.job.job_id,
                    "state": view.recording.state.value,
                    "draft_revision": view.draft.revision if view.draft else None,
                }
            )
        finally:
            engine.dispose()
    except JiejianError as exc:
        _fail(exc)


@recording_app.command("status")
def recording_status_command(context: typer.Context, recording_id: str) -> None:
    """查看 Recording 状态和当前 FlowDraft revision。"""

    try:
        settings = _runtime_settings(context)
        engine, factory = _open_storage(settings)
        try:
            view = RecordingWorkflow(factory).status(recording_id)
            _emit_json(view.model_dump(mode="json"))
        finally:
            engine.dispose()
    except JiejianError as exc:
        _fail(exc)


@recording_app.command("review")
def recording_review_command(
    context: typer.Context,
    recording_id: str,
    command_path: Path = typer.Option(..., "--command", help="Flow 审阅命令 JSON"),
    bindings_path: Path | None = typer.Option(
        None,
        "--bindings",
        help="显式身份/资源绑定 JSON，可选",
    ),
) -> None:
    """应用一个不可变 FlowDraft 审阅命令并生成新 revision。"""

    try:
        command = parse_flow_draft_review_command(
            command_path.read_bytes(),
        )
        bindings = _load_recording_bindings(bindings_path) if bindings_path else None
        settings = _runtime_settings(context)
        engine, factory = _open_storage(settings)
        try:
            view = RecordingWorkflow(factory).review(
                recording_id,
                command,
                bindings=bindings,
            )
            _emit_json(view.model_dump(mode="json"))
        finally:
            engine.dispose()
    except (OSError, JiejianError) as exc:
        _fail(
            exc
            if isinstance(exc, JiejianError)
            else JiejianError(ErrorCode.INPUT_FILE, "审阅命令文件不可读取")
        )


@recording_app.command("finalize")
def recording_finalize_command(
    context: typer.Context,
    recording_id: str,
) -> None:
    """确认已满足审阅门禁，原子发布最终 Flow 并完成 Recording。"""

    try:
        settings = _runtime_settings(context)
        engine, factory = _open_storage(settings)
        try:
            view = RecordingWorkflow(factory).finalize(
                recording_id,
                var_dir=settings.var_dir,
                now_us=time.time_ns() // 1_000,
            )
            _emit_json(view.model_dump(mode="json"))
        finally:
            engine.dispose()
    except JiejianError as exc:
        _fail(exc)


@recording_app.command("replay")
def recording_replay_command(
    context: typer.Context,
    recording_id: str,
    project_path: Path = typer.Option(..., "--project", help="项目 YAML"),
    runs: int = typer.Option(3, "--runs", min=1, max=3, help="连续回放次数"),
) -> None:
    """通过独立 Verification Runner 连续回放已完成 Flow。"""

    try:
        settings = _runtime_settings(context)
        bundle = load_project_bundle(project_path)
        engine, factory = _open_storage(settings)
        try:
            workflow = RecordingWorkflow(factory)
            with factory() as work:
                recording = work.recordings.get(recording_id)
            if (
                recording is None
                or recording.state is not RecordingState.COMPLETED
                or recording.project_id != bundle.project.id
            ):
                raise JiejianError(
                    ErrorCode.RECORD_REVIEW_STATE,
                    "录制尚未完成，不能回放",
                )
            flow = workflow.load_final_flow(workflow.flow_path(settings.var_dir, recording))
        finally:
            engine.dispose()
        replay_bundle = ProjectBundle(
            project_file=bundle.project_file,
            project=bundle.project,
            flow=flow,
            contract=bundle.contract,
        )
        results = [
            _run_persisted_job(settings, replay_bundle, flow=flow).model_dump(mode="json")
            for _ in range(runs)
        ]
        _emit_json(
            {
                "schema_version": "1",
                "recording_id": recording_id,
                "runs": results,
            }
        )
    except (OSError, JiejianError) as exc:
        _fail(
            exc
            if isinstance(exc, JiejianError)
            else JiejianError(ErrorCode.RECORD_REPLAY_FAILED, "回放输入不可读取")
        )


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


def _open_storage(
    settings: Settings,
) -> tuple[object, partial[StorageUnitOfWork]]:
    var_dir = settings.var_dir.resolve()
    database_path = default_database_path(var_dir)
    upgrade_database(database_path)
    engine = create_sqlite_engine(database_path)
    factory = partial(StorageUnitOfWork, create_session_factory(engine))
    return engine, factory


def _load_recording_bindings(path: Path) -> dict[str, dict[str, str]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise JiejianError(ErrorCode.INPUT_FILE, "绑定文件不可读取") from None
    if not isinstance(value, dict):
        raise JiejianError(ErrorCode.INPUT_INVALID, "绑定文件必须是对象")
    result: dict[str, dict[str, str]] = {}
    for step_id, binding in value.items():
        if not isinstance(step_id, str) or not isinstance(binding, dict):
            raise JiejianError(ErrorCode.INPUT_INVALID, "绑定文件结构无效")
        if any(not isinstance(key, str) or not isinstance(item, str) for key, item in binding.items()):
            raise JiejianError(ErrorCode.INPUT_INVALID, "绑定文件值无效")
        result[step_id] = dict(binding)
    return result


def _ensure_project_record(
    factory: partial[StorageUnitOfWork],
    bundle: ProjectBundle,
    now_us: int,
) -> None:
    with factory() as work:
        existing = work.projects.get(bundle.project.id)
        if existing is None:
            work.projects.add(
                ProjectRecord(
                    project_id=bundle.project.id,
                    name=bundle.project.name,
                    status=ProjectStatus.READY,
                    created_at_us=now_us,
                    updated_at_us=now_us,
                )
            )
            work.commit()
        elif existing.status is not ProjectStatus.READY:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "项目状态不允许创建录制")


def _run_persisted_job(
    settings: Settings,
    bundle: ProjectBundle,
    *,
    flow=None,
) -> RunResult:
    var_dir = settings.var_dir.resolve()
    database_path = default_database_path(var_dir)
    upgrade_database(database_path)
    engine = create_sqlite_engine(database_path)
    try:
        factory = create_session_factory(engine)
        uow_factory = partial(StorageUnitOfWork, factory)
        request = _persisted_request(bundle, flow=flow)
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


def _persisted_request(bundle: ProjectBundle, *, flow=None) -> PersistedExecutionRequestV1:
    project = bundle.project
    selected_flow = flow or bundle.flow
    snapshot = ExecutionProjectSnapshotV1(
        schema_version="1",
        project_id=project.id,
        project_name=project.name,
        target=project.target,
        identities=project.identities,
        resources=project.resources,
        flow=selected_flow,
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
        ErrorCode.RECORD_NOT_FOUND.value,
        ErrorCode.RECORD_REVIEW_STATE.value,
        ErrorCode.RECORD_DRAFT_UNCONFIRMED.value,
        ErrorCode.RECORD_DRAFT_REFERENCE.value,
        ErrorCode.RECORD_DRAFT_NOT_ADJACENT.value,
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
