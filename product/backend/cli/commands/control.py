# CLI 持续验证控制面：公开应用、代码变化、检查和可信结果的非交互入口。

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


def _attention_actions(status: object) -> list[dict[str, str]]:
    return [
        {
            "action": item.key,
            "label": item.label,
            "route": item.route,
        }
        for item in status.attention_items
    ]


def status_command(
    context: typer.Context,
    project_id: str | None = typer.Option(None, "--project", help="明确选择应用"),
) -> None:
    """查看持续验证工作区、全部待办和最近可信结果。"""

    try:
        with application_scope(context) as application:
            status = application.product_status.get(project_id)
        emit_command(
            "status",
            status,
            next_actions=_attention_actions(status),
            human=lambda: emit_status(status),
        )
    except JiejianError as exc:
        fail(exc)


def application_list_command(context: typer.Context) -> None:
    """列出已经正式接入的应用。"""

    try:
        with application_scope(context) as application:
            projects = application.projects.list()
        rows = [
            {
                "project_id": item.project_id,
                "name": item.name,
                "status": item.status.value,
            }
            for item in projects
        ]
        emit_command("application-list", rows)
    except JiejianError as exc:
        fail(exc)


def application_show_command(context: typer.Context, project_id: str) -> None:
    """只读展示与 GUI 同源的应用业务摘要，不返回源码或候选内部事实。"""

    try:
        with application_scope(context) as application:
            status = application.product_status.get(project_id)
        readiness = status.readiness
        if status.project is None or readiness is None:
            raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "应用不存在")
        summary = {
            "project_id": status.project.project_id,
            "name": status.project.name,
            "status": status.project.status.value,
            "connection": {
                "endpoint": readiness.endpoint_status,
                "source_analysis": readiness.source_analysis_status,
            },
            "confirmed_business_facts": {
                "permission_group_count": readiness.confirmed_role_count,
                "business_action_count": readiness.confirmed_action_count,
            },
            "preparation": {
                "business_flow_ready": readiness.completed_flow_available,
                "permission_requirements_ready": readiness.active_contract_available,
                "check_ready": readiness.current_scope_runnable,
            },
            "attention_items": [
                {
                    "label": item.label,
                    "description": item.description,
                    "route": item.route,
                }
                for item in status.attention_items
            ],
        }
        emit_command(
            "application",
            summary,
            human=lambda: _emit_application_summary(summary),
        )
    except JiejianError as exc:
        fail(exc)


def application_remove_command(
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
        emit_command("application-removed", result)
    except JiejianError as exc:
        fail(exc)


def source_change_list_command(
    context: typer.Context,
    project_id: str,
    limit: int = typer.Option(20, "--limit", min=1, max=100, help="最多显示多少次变化"),
) -> None:
    """按新到旧查看 Agent 提交的代码变化及其权限影响。"""

    try:
        with application_scope(context) as application:
            changes = application.source_changes.list_views(project_id, limit=limit)
        emit_command(
            "change-list",
            _dump(changes),
            human=lambda: _emit_source_changes(changes),
        )
    except JiejianError as exc:
        fail(exc)


def source_change_show_command(
    context: typer.Context,
    project_id: str,
    change_id: str,
) -> None:
    """查看一次代码变化的真实差异摘要和重新确认范围。"""

    try:
        with application_scope(context) as application:
            change = application.source_changes.view(change_id)
        if change.project_id != project_id:
            raise JiejianError(ErrorCode.INPUT_INVALID, "代码变化不属于当前应用")
        emit_command(
            "change",
            change,
            human=lambda: _emit_source_changes((change,)),
        )
    except JiejianError as exc:
        fail(exc)


def check_preview_command(
    context: typer.Context,
    project_id: str,
    change_id: str | None = typer.Option(None, "--change", help="核对指定 Agent 代码变化"),
) -> None:
    """只读预览当前已批准权限要求能否形成检查。"""

    try:
        with application_scope(context) as application:
            result = application.checks.preview(project_id, change_id=change_id)
        emit_command("check-preview", result)
    except JiejianError as exc:
        fail(exc)


def check_prepare_command(
    context: typer.Context,
    project_id: str,
    change_id: str | None = typer.Option(None, "--change", help="为指定 Agent 代码变化准备检查"),
) -> None:
    """调用正式编译器准备当前检查条件，并回读最新预览。"""

    try:
        with application_scope(context) as application:
            preview = application.checks.prepare(project_id, change_id=change_id)
        emit_command(
            "check-prepared",
            {"preview": _dump(preview)},
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
    change_id: str | None = typer.Option(None, "--change", help="把指定 Agent 变化冻结到本次检查"),
) -> None:
    """按当前已确认事实提交检查，不接收内部执行配置路径。"""

    try:
        with application_scope(context) as application:
            result, request, _ = application.checks.submit(
                project_id,
                idempotency_key=f"cli-{uuid4().hex}",
                change_id=change_id,
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


def result_report_command(
    context: typer.Context,
    run_id: str = typer.Option(..., "--run"),
    report_id: str | None = typer.Option(None, "--report"),
) -> None:
    """读取已发布报告 JSON，并置于稳定 Machine envelope 的 data 中。"""

    try:
        with application_scope(context) as application:
            selected_report_id = report_id
            if selected_report_id is None:
                reports = application.reports.list(run_id)
                if not reports:
                    raise JiejianError(
                        ErrorCode.REPORT_NOT_FOUND,
                        "当前检查还没有已发布报告",
                    )
                selected_report_id = str(reports[0]["report_id"])
            result = application.reports.read(run_id, selected_report_id)
        emit_command("report", result)
    except JiejianError as exc:
        fail(exc)


def history_command(
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


def _emit_application_summary(summary: dict[str, object]) -> None:
    """人类输出保留当前应用事实和全部需要处理的事项。"""

    facts = summary["confirmed_business_facts"]
    preparation = summary["preparation"]
    attention_items = summary["attention_items"]
    assert isinstance(facts, dict)
    assert isinstance(preparation, dict)
    assert isinstance(attention_items, list)
    typer.echo(str(summary["name"]))
    typer.echo("")
    typer.echo(f"已确认权限组：{facts['permission_group_count']}")
    typer.echo(f"已确认关键业务动作：{facts['business_action_count']}")
    typer.echo(f"业务流程：{'已准备' if preparation['business_flow_ready'] else '待准备'}")
    typer.echo(f"当前范围：{'可以检查' if preparation['check_ready'] else '仍需准备'}")
    if attention_items:
        typer.echo("")
        typer.echo("需要处理")
        for item in attention_items:
            assert isinstance(item, dict)
            typer.echo(f"- {item['label']}：{item['description']}")


def _emit_source_changes(changes: object) -> None:
    """以业务影响为主展示代码变化，不输出源码正文和内部指纹。"""

    rows = tuple(changes)
    if not rows:
        typer.echo("当前还没有 Agent 代码变化记录")
        return
    for change in rows:
        typer.echo(f"{change.change_id}  {change.reason}")
        typer.echo(f"  {change.summary}")
        typer.echo(
            "  实际文件变化："
            f"新增 {change.added_count}，修改 {change.modified_count}，删除 {change.removed_count}"
        )


__all__ = [name for name in globals() if name.endswith("_command")]
