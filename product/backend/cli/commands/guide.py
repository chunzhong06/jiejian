# CLI 新手引导：只读取 ApplicationCore 事实并调用现有检查、结果和图形界面能力。
# 引导不保存独立进度，不要求普通用户输入 Contract/Profile 等内部标识。

from __future__ import annotations

import os
from uuid import uuid4

import click
import typer

from product.backend.cli.bootstrap import application_scope
from product.backend.cli.commands.system import serve_command
from product.backend.cli.presentation import (
    emit_doctor,
    emit_result_presentation,
    fail,
    presentation_mode,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.diagnostics import run_doctor


def guide_command(context: typer.Context) -> None:
    """打开任务导向的新手工作台。"""

    stdin = click.get_text_stream("stdin")
    stdout = click.get_text_stream("stdout")
    if (
        presentation_mode() != "human"
        or not getattr(stdin, "isatty", lambda: False)()
        or not getattr(stdout, "isatty", lambda: False)()
    ):
        fail(
            JiejianError(
                ErrorCode.INPUT_INVALID,
                "引导模式需要交互式终端；脚本和自动化请使用 --json 或 ci 命令。",
            )
        )

    while True:
        _write_workspace(context)
        selected = _choose(
            "你想做什么？",
            (
                "开始第一次权限检查",
                "检查运行环境",
                "录制业务流程",
                "查看最近检查结果",
                "打开图形界面",
                "进入普通命令行",
                "退出",
            ),
        )
        if selected == 0:
            _first_check(context)
        elif selected == 1:
            _doctor(context)
        elif selected == 2:
            _complex_in_gui(context, "录制和确认业务流程")
        elif selected == 3:
            _recent_result(context)
        elif selected == 4:
            _open_gui(context)
        elif selected == 5:
            return
        else:
            raise typer.Exit(
                code=10 if os.environ.get("JIEJIAN_GUIDE_STARTUP") == "1" else 0
            )


def _write_workspace(context: typer.Context) -> None:
    with application_scope(context) as application:
        projects = application.projects.list()
        guidance = tuple(
            (project, application.assistant_guidance.get(project.project_id))
            for project in projects
        )
        recent = tuple(
            (
                project,
                application.project_readiness.get(project.project_id),
            )
            for project in projects
        )
    typer.echo("界鉴命令行 · 引导模式")
    typer.echo("")
    typer.secho("运行环境已经准备完成  ✓", fg="green")
    typer.echo("")
    if not projects:
        typer.echo("当前状态")
        typer.echo("├─ ○ 尚未接入应用")
        typer.echo("└─ ○ 尚未开始检查")
        typer.echo("")
        typer.echo("下一步")
        typer.echo("└─ 打开图形界面接入你的 Web 应用")
    else:
        runnable = any(snapshot.current_scope_runnable for _, snapshot in guidance)
        typer.echo("当前状态")
        typer.echo(f"├─ ✓ 已接入 {len(projects)} 个应用")
        typer.echo(
            "├─ ✓ 有可直接检查的当前范围" if runnable else "├─ ! 还需要在图形界面完成准备"
        )
        latest = next(
            (readiness.latest_verified_run_id for _, readiness in recent if readiness.latest_verified_run_id),
            None,
        )
        if latest:
            typer.echo("└─ 已有最近一次可信检查结果")
        else:
            typer.echo("└─ ○ 尚未开始检查")
        typer.echo("")
        typer.echo("下一步")
        typer.echo(
            "└─ 查看最近检查结果" if latest else "└─ 开始第一次检查" if runnable else "└─ 在图形界面完成准备"
        )
    typer.echo("")


def _first_check(context: typer.Context) -> None:
    choice = _choose(
        "从哪里开始？",
        (
            "检查已经接入的应用",
            "打开图形界面接入应用",
            "返回",
        ),
    )
    if choice == 0:
        _existing_application(context)
    elif choice == 1:
        _open_gui(context)


def _existing_application(context: typer.Context) -> None:
    try:
        with application_scope(context) as application:
            projects = application.projects.list()
            candidates = [
                project
                for project in projects
                if application.assistant_guidance.get(project.project_id).current_scope_runnable
            ]
        if not candidates:
            _complex_in_gui(context, "接入应用并完成权限规则准备")
            return
        labels = tuple(project.name for project in candidates) + ("返回",)
        selected = _choose("选择应用", labels)
        if selected == len(candidates):
            return
        project = candidates[selected]
        with application_scope(context) as application:
            submission, _, _ = application.checks.submit(
                project.project_id,
                idempotency_key=f"guide-{uuid4().hex}",
            )
        typer.echo("检查已提交。请打开图形界面查看运行进度。")
        typer.echo(f"任务已进入队列：{submission.job.job_id}")
        _pause()
    except JiejianError as exc:
        fail(exc)


def _recent_result(context: typer.Context) -> None:
    try:
        with application_scope(context) as application:
            candidates = []
            for project in application.projects.list():
                readiness = application.project_readiness.get(project.project_id)
                if readiness.latest_verified_run_id:
                    presentation = application.result_presentation.build(
                        readiness.latest_verified_run_id
                    )
                    candidates.append((project, presentation))
            if not candidates:
                typer.echo("")
                typer.echo("还没有检查结果。")
                typer.echo("下一步：接入应用并开始第一次检查。")
                _pause()
                return
            labels = tuple(
                f"{project.name} · {presentation.headline}"
                for project, presentation in candidates[:5]
            ) + ("返回",)
            selected = _choose("选择检查结果", labels)
            if selected == len(labels) - 1:
                return
            presentation = candidates[selected][1]
        emit_result_presentation(presentation)
        _pause()
    except JiejianError as exc:
        fail(exc)


def _doctor(context: typer.Context) -> None:
    options = context.obj
    report = run_doctor(
        config_path=options.config,
        cli_overrides={
            "var_dir": options.var_dir,
            "log_level": options.log_level,
            "trace_id": options.trace_id,
        },
    )
    typer.echo("")
    emit_doctor(report)
    _pause()


def _complex_in_gui(context: typer.Context, task: str) -> None:
    typer.echo("")
    typer.echo(f"{task}在图形界面中更容易完成。")
    choice = _choose("下一步", ("打开图形界面", "返回"))
    if choice == 0:
        _open_gui(context)


def _open_gui(context: typer.Context) -> None:
    serve_command(
        context,
        host="127.0.0.1",
        port=8765,
        open_browser=True,
        frontend_dir=None,
    )


def _choose(title: str, items: tuple[str, ...]) -> int:
    typer.echo(title)
    for index, item in enumerate(items, start=1):
        typer.echo(f"  {index}. {item}")
    while True:
        value = typer.prompt(f"请输入 1-{len(items)}", type=int)
        if 1 <= value <= len(items):
            typer.echo("")
            return value - 1
        typer.echo("请输入列表中的编号。")


def _pause() -> None:
    typer.prompt("按 Enter 返回", default="", show_default=False)
    typer.echo("")
