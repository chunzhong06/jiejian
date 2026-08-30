# CLI 精简控制面：只公开已接入应用、已批准检查、可信结果和历史的非交互入口。

from __future__ import annotations

import time
from uuid import uuid4

import typer

from product.backend.cli.bootstrap import application_scope
from product.backend.cli.presentation import emit_command, emit_result_presentation, emit_status, fail
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import JobState
from product.backend.infra.runtime.jobs.models import RequestCancellation


def _dump(value: object) -> object:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, tuple):
        return [_dump(item) for item in value]
    return value


def _next_actions(status: object) -> list[dict[str, str]]:
    action = status.next_action
    return [{"action": action.action, "label": action.label, "route": action.route, "cli_command": action.cli_command}]


def status_command(
    context: typer.Context,
    project_id: str | None = typer.Option(None, "--project", help="明确选择应用"),
) -> None:
    """查看产品准备状态、唯一下一步和最近可信结果。"""

    try:
        with application_scope(context) as application:
            status = application.product_status.get(project_id)
        emit_command("status", status, next_actions=_next_actions(status), human=lambda: emit_status(status))
    except JiejianError as exc:
        fail(exc)


def app_list_command(
    context: typer.Context,
    include_archived: bool = typer.Option(False, "--include-archived", help="同时列出已移除应用"),
) -> None:
    """列出已经正式接入的应用。"""

    try:
        with application_scope(context) as application:
            projects = application.projects.list(include_archived=include_archived)
        emit_command("app-list", [_dump(item) for item in projects])
    except JiejianError as exc:
        fail(exc)


def app_show_command(context: typer.Context, project_id: str) -> None:
    """只读查看应用理解事实，不触发探测或分析。"""

    try:
        with application_scope(context) as application:
            understanding = application.application_understanding.get(project_id)
        emit_command("app", understanding)
    except JiejianError as exc:
        fail(exc)


def app_remove_command(
    context: typer.Context,
    project_id: str,
    confirmed: bool = typer.Option(False, "--confirm", help="确认移除当前应用但保留源码和历史结果"),
) -> None:
    """归档应用并清理当前测试身份秘密，不物理删除历史。"""

    try:
        if not confirmed:
            raise JiejianError(ErrorCode.STATE_OPERATOR_REQUIRED, "移除应用前需要使用 --confirm 明确确认")
        with application_scope(context) as application:
            result = application.project_lifecycle.archive(project_id)
        emit_command("app-removed", result)
    except JiejianError as exc:
        fail(exc)


def check_preview_command(context: typer.Context, project_id: str) -> None:
    """只读预览当前已批准权限要求能否形成检查。"""

    try:
        with application_scope(context) as application:
            result = application.checks.preview(project_id)
        emit_command("check-preview", result)
    except JiejianError as exc:
        fail(exc)


def check_prepare_command(context: typer.Context, project_id: str) -> None:
    """调用正式编译器准备当前检查条件，并回读最新预览。"""

    try:
        with application_scope(context) as application:
            compiled = application.security_setup.compile(project_id)
            preview = application.checks.preview(project_id)
        emit_command(
            "check-prepared",
            {"preview": _dump(preview), "compilation": _dump(compiled)},
            human=lambda: typer.echo("检查条件已经准备好" if preview.ready else "检查条件仍有缺项"),
        )
    except JiejianError as exc:
        fail(exc)


def check_cancel_command(
    context: typer.Context,
    project_id: str | None = typer.Option(None, "--project"),
) -> None:
    """取消显式项目或唯一当前项目的最新活动检查。"""

    try:
        with application_scope(context) as application:
            status = application.product_status.get(project_id)
            if status.project is None:
                raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "当前还没有已接入应用")
            with application.uow_factory() as work:
                candidates = tuple(
                    job
                    for run in work.runs.list_for_project(status.project.project_id)
                    if (job := work.jobs.get_by_run(run.run_id)) is not None
                    and job.state not in {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED}
                )
            if not candidates:
                raise JiejianError(ErrorCode.JOB_NOT_FOUND, "当前应用没有正在进行的检查")
            job = max(candidates, key=lambda item: (item.created_at_us, item.job_id))
            result = application.job_queue.request_cancellation(
                RequestCancellation(job_id=job.job_id, now_us=time.time_ns() // 1_000)
            )
        emit_command("check-cancelled", result)
    except JiejianError as exc:
        fail(exc)


def check_run_command(
    context: typer.Context,
    project_id: str,
    idempotency_key: str | None = typer.Option(None, "--idempotency-key"),
) -> None:
    """按当前已确认事实提交检查，不接收内部执行配置路径。"""

    try:
        with application_scope(context) as application:
            result, request, _ = application.checks.submit(
                project_id,
                idempotency_key=idempotency_key or f"cli-{uuid4().hex}",
            )
        emit_command(
            "check-submitted",
            {
                "job": result.job.model_dump(mode="json"),
                "run": result.run.model_dump(mode="json"),
                "schema_version": request.schema_version,
            },
        )
    except JiejianError as exc:
        fail(exc)


def result_show_command(
    context: typer.Context,
    run_id: str | None = typer.Option(None, "--run"),
    project_id: str | None = typer.Option(None, "--project"),
) -> None:
    """读取同一个 ResultPresentation，包括全部 evidence_sources。"""

    try:
        with application_scope(context) as application:
            result = application.product_results.presentation(run_id=run_id, project_id=project_id)
        emit_command("result", result, human=lambda: emit_result_presentation(result))
    except JiejianError as exc:
        fail(exc)


def result_reports_command(context: typer.Context, run_id: str) -> None:
    """列出一次检查已经发布的报告。"""

    try:
        with application_scope(context) as application:
            result = application.reports.list(run_id)
        emit_command("result-reports", result)
    except JiejianError as exc:
        fail(exc)


def result_report_command(context: typer.Context, run_id: str, report_id: str) -> None:
    """读取已发布报告 JSON，并置于稳定 Machine envelope 的 data 中。"""

    try:
        with application_scope(context) as application:
            result = application.reports.read(run_id, report_id)
        emit_command("report", result)
    except JiejianError as exc:
        fail(exc)


def history_show_command(
    context: typer.Context,
    project_id: str | None = typer.Option(None, "--project"),
) -> None:
    """读取既有 HistoryView，不重新比较 raw Evidence。"""

    try:
        with application_scope(context) as application:
            result = application.product_results.history(project_id)
        emit_command("history", result)
    except JiejianError as exc:
        fail(exc)


__all__ = [name for name in globals() if name.endswith("_command")]
