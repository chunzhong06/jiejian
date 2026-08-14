# =============================================================================
# Verification Run CLI 命令组
#
# 定位
#   Run 提交、Worker 调度和终态读取的命令行编排边界
#
# 职责
#   构造冻结执行请求｜等待持久 Job｜输出生命周期与 Verdict
#
# 调用链
#   Typer → run commands → Execution services / WorkerDispatcher / Storage
# =============================================================================

from __future__ import annotations

import json
import os
from functools import partial
from pathlib import Path
import time
from uuid import uuid4

import typer

from ...domain.lifecycle import RunLifecycle
from ...verification.models import RunResult
from ...errors import ErrorCode, JiejianError
from ...execution.requests import build_execution_request
from ...projects.service import ProjectControlService
from ...protocols import RunnerResultType
from ...storage import (
    StorageUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
    default_database_path,
    upgrade_database,
)
from ...verification.inputs import ProjectBundle, load_project_bundle
from ...execution.dispatch import WorkerDispatcher
from ...execution.request_store import (
    ExecutionRequestStore,
    PersistedExecutionRequestV1,
    required_secret_names,
)
from ...execution.submission import ExecutionSubmissionService, SubmitExecutionV1
from ...application.context import ApplicationContext
from ...protocols.runner_v2 import RunnerResultV2
from ..bootstrap import runtime_settings
from ..presentation import emit_json, fail


def run_command(
    context: typer.Context,
    project_path: Path,
    contract_path: Path = typer.Option(..., "--contract", help="显式契约文件"),
) -> None:
    """提交持久任务并等待隔离 Runner 的已发布结果。"""

    try:
        settings = runtime_settings(context)
        bundle = load_project_bundle(project_path, contract_path=contract_path)
        result = _run_persisted_job(settings, bundle)
        emit_json(result.model_dump(mode="json"))
    except JiejianError as exc:
        fail(exc)


def permission_run_command(
    context: typer.Context,
    profile_path: Path,
    revalidate: bool = typer.Option(False, "--revalidate", help="显式更新 Profile 来源摘要"),
) -> None:
    """注册受控 V2 Profile，提交并等待真实 Runner V2 结果。"""

    application = None
    try:
        settings = runtime_settings(context)
        application = ApplicationContext(settings.var_dir, environ=os.environ)
        record = application.permission_execution.register(
            profile_path,
            revalidate=revalidate,
        )
        submitted, request, secret_names = application.permission_execution.submit(
            record.profile_id,
            project_id=record.project_id,
            idempotency_key=f"cli-{uuid4().hex}",
            max_attempts=3,
        )
        environment = application.environment_for_secret_names(secret_names)
        known_secrets = tuple(environment.get(name, "") for name in secret_names)
        dispatcher = WorkerDispatcher(
            var_dir=application.var_dir,
            uow_factory=application.uow_factory,
            environ=environment,
        )
        process = dispatcher.start(
            job_id=submitted.job.job_id,
            lease_owner=f"worker-{uuid4().hex}",
            secret_names=secret_names,
        )
        staged = dispatcher.wait(
            submitted.job.job_id,
            process,
            known_secrets=known_secrets,
            timeout_seconds=(request.budget.max_duration_us * 3) / 1_000_000 + 60,
        )
        if not isinstance(staged.result, RunnerResultV2):
            raise JiejianError(ErrorCode.RUNNER_PROTOCOL_INVALID, "V2 Profile 未形成 V2 结果")
        result = staged.result
        emit_json(
            {
                "schema_version": "2",
                "run_id": result.run_id,
                "job_id": result.job_id,
                "lifecycle": result.run_lifecycle.value,
                "verdict": result.verdict.value if result.verdict else None,
                "coverage_record_count": result.coverage_record_count,
                "coverage_gap_count": result.coverage_gap_count,
                "evidence_count": len(result.evidence),
                "reason_codes": list(result.reason_codes),
                "artifact_dir": str(
                    application.var_dir
                    / "projects"
                    / request.project_snapshot.project_id
                    / "runs"
                    / result.run_id
                ),
            }
        )
    except JiejianError as exc:
        fail(exc)
    finally:
        if application is not None:
            application.close()


def _run_persisted_job(
    settings,
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
        ProjectControlService(uow_factory).register(bundle.project_file, revalidate=True)
        request = build_execution_request(bundle, flow=flow)
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


def _persisted_request(
    bundle: ProjectBundle, *, flow=None
) -> PersistedExecutionRequestV1:
    return build_execution_request(bundle, flow=flow)


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
