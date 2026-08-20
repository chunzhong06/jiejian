# CLI 新手引导：只读取 ApplicationCore 事实并调用现有检查、结果和图形界面能力。
# 引导不保存独立进度，不要求普通用户输入 Contract/Profile 等内部标识。

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import click
import typer

from product.backend.cli.bootstrap import application_scope
from product.backend.cli.commands.system import serve_command
from product.backend.cli.presentation import (
    emit_doctor,
    emit_guide_result,
    fail,
    human_wait,
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
        snapshot = application.guide_snapshot()
    projects = snapshot["projects"]
    recent_runs = snapshot["recent_runs"]
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
        typer.echo("└─ 运行内置演示，或打开图形界面接入你的 Web 应用")
    else:
        rules_ready = any(item["permission_rules_ready"] for item in projects)
        typer.echo("当前状态")
        typer.echo(f"├─ ✓ 已接入 {len(projects)} 个应用")
        typer.echo(
            "├─ ✓ 权限规则已准备" if rules_ready else "├─ ! 还需要确认权限规则"
        )
        if recent_runs:
            typer.echo(f"└─ {_verdict_line(recent_runs[0][1].verdict)}")
        else:
            typer.echo("└─ ○ 尚未开始检查")
        typer.echo("")
        typer.echo("下一步")
        typer.echo(
            "└─ 查看最近检查结果"
            if recent_runs
            else "└─ 开始第一次检查" if rules_ready else "└─ 在图形界面确认权限规则"
        )
    typer.echo("")


def _first_check(context: typer.Context) -> None:
    choice = _choose(
        "从哪里开始？",
        (
            "运行内置演示（推荐）",
            "检查已经接入的应用",
            "打开图形界面接入应用",
            "返回",
        ),
    )
    if choice == 0:
        _demo(context)
    elif choice == 1:
        _existing_application(context)
    elif choice == 2:
        _open_gui(context)


def _demo(context: typer.Context) -> None:
    choice = _choose(
        "选择你想看到的结果",
        (
            "存在权限问题（推荐）",
            "权限限制正常",
            "证据不足，暂时不能下结论",
            "返回",
        ),
    )
    if choice == 3:
        return
    variant = ("vulnerable", "fixed", "inconclusive")[choice]
    try:
        with application_scope(context) as application:
            with human_wait("正在运行内置权限检查"):
                _status, result = application.run_demo(variant)
        emit_guide_result(result)
        _pause()
    except JiejianError as exc:
        fail(exc)


def _existing_application(context: typer.Context) -> None:
    try:
        with application_scope(context) as application:
            snapshot = application.guide_snapshot()
        candidates = [
            item
            for item in snapshot["projects"]
            if item["permission_rules_ready"] and item["profiles"]
        ]
        if not candidates:
            _complex_in_gui(context, "接入应用并确认权限规则")
            return
        labels = tuple(item["project"].name for item in candidates) + ("返回",)
        selected = _choose("选择应用", labels)
        if selected == len(candidates):
            return
        profiles = candidates[selected]["profiles"]
        if len(profiles) > 1:
            profile_labels = tuple(
                f"检查方式 {index + 1}" for index in range(len(profiles))
            ) + ("返回",)
            profile_index = _choose("选择检查方式", profile_labels)
            if profile_index == len(profiles):
                return
        else:
            profile_index = 0
        with application_scope(context) as application:
            with human_wait("正在执行权限检查"):
                result = application.execution.run_profile(
                    Path(profiles[profile_index].source_path),
                    idempotency_key=f"guide-{uuid4().hex}",
                )
        emit_guide_result(result)
        _pause()
    except JiejianError as exc:
        fail(exc)


def _recent_result(context: typer.Context) -> None:
    try:
        with application_scope(context) as application:
            recent = application.guide_snapshot()["recent_runs"]
            if not recent:
                typer.echo("")
                typer.echo("还没有检查结果。")
                typer.echo("下一步：运行内置演示或开始第一次检查。")
                _pause()
                return
            labels = tuple(
                f"{project.name} · {_verdict_text(run.verdict)}"
                for project, run in recent[:5]
            ) + ("返回",)
            selected = _choose("选择检查结果", labels)
            if selected == len(labels) - 1:
                return
            run = recent[selected][1]
            view = application.results.read(run.run_id)
            result = view.publication.result
        emit_guide_result(result)
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


def _verdict_text(verdict: object) -> str:
    return {
        "PASS": "未发现确认问题",
        "BLOCK": "发现权限问题",
        "INCONCLUSIVE": "证据不足",
    }.get(str(verdict), "检查尚未完成")


def _verdict_line(verdict: object) -> str:
    return {
        "PASS": "✓ 最近检查未发现确认问题",
        "BLOCK": "× 最近检查发现权限问题",
        "INCONCLUSIVE": "! 最近检查证据不足",
    }.get(str(verdict), "○ 最近检查尚未完成")
