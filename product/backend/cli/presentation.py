# CLI 输出与失败映射
# 将应用结果转换为确定性 JSON、脱敏错误和稳定退出码。

from __future__ import annotations

from contextlib import contextmanager
import json
import threading
from collections.abc import Callable, Sequence
from typing import NoReturn
from uuid import uuid4

import click
import typer

from product.backend.core.errors import ErrorCode, JiejianError
_configured_presentation = "auto"
_configured_machine_only = False


def configure_presentation(mode: str, *, machine_only: bool = False) -> None:
    global _configured_presentation, _configured_machine_only
    _configured_presentation = mode
    _configured_machine_only = machine_only


def _root_context() -> click.Context | None:
    return click.get_current_context(silent=True)


def _options(context: click.Context | None = None):
    current = context or _root_context()
    if current is None:
        return None
    return current.find_root().obj


def set_command_mode(mode: str) -> None:
    """为仍接受旧命令位置选项的入口设置统一展示模式。"""

    global _configured_presentation
    _configured_presentation = mode
    context = _root_context()
    if context is not None:
        context.find_root().meta["presentation_mode"] = mode


def force_machine_mode() -> None:
    global _configured_machine_only
    _configured_machine_only = True
    context = _root_context()
    if context is not None:
        context.find_root().meta["machine_only"] = True


def presentation_mode(context: click.Context | None = None) -> str:
    if _configured_machine_only:
        return "json"
    if _configured_presentation != "auto":
        return _configured_presentation
    options = _options(context)
    root = context or _root_context()
    if root is not None:
        root = root.find_root()
    if options is not None and options.machine_only:
        return "json"
    if root is not None and root.meta.get("machine_only"):
        return "json"
    if root is not None and root.meta.get("presentation_mode"):
        return root.meta["presentation_mode"]
    explicit = getattr(options, "presentation", "auto") if options is not None else "auto"
    if explicit != "auto":
        return explicit
    return "human" if click.get_text_stream("stdout").isatty() else "json"


_FIELD_LABELS = {
    "valid": "项目校验",
    "project_id": "项目",
    "flow_id": "Flow",
    "contract_id": "契约",
    "run_id": "运行标识",
    "job_id": "任务标识",
    "recording_id": "录制标识",
    "state": "录制状态",
    "lifecycle": "运行状态",
    "verdict": "结论",
    "decision": "门禁结论",
    "reason_codes": "原因代码",
    "artifact_dir": "结果位置",
    "report_id": "报告标识",
    "gate_result_id": "门禁结果",
    "baseline_id": "回归基线",
    "coverage_record_count": "证据记录",
    "coverage_gap_count": "覆盖缺口",
    "evidence_count": "证据数量",
    "draft_revision": "Flow 修订",
}

_DOCTOR_LABELS = {
    "python": "Python",
    "dependencies": "Python 依赖",
    "config": "配置",
    "var_dir": "运行目录",
    "sqlite": "数据库",
    "playwright": "浏览器",
    "loopback": "本机服务",
    "redaction": "日志脱敏",
}


def _human_value(value: object) -> str:
    if isinstance(value, bool):
        return "通过" if value else "失败"
    if value is None:
        return "未提供"
    return str(value)


def _outcome(value: object) -> str:
    return {
        "PASS": "当前已执行规则与可用证据范围内未发现确认问题",
        "SAFE": "当前已执行规则与可用证据范围内未发现确认问题",
        "BLOCK": "发现权限问题",
        "VULNERABLE": "发现权限问题",
        "INCONCLUSIVE": "证据不足，暂时不能下结论",
        "ERROR": "错误",
    }.get(str(value), _human_value(value))


def _status_value(value: object) -> str:
    return {
        "PENDING": "等待处理",
        "QUEUED": "等待处理",
        "RUNNING": "正在检查",
        "COMPLETED": "已完成",
        "SUCCEEDED": "已完成",
        "FAILED": "检查失败",
        "CANCELLED": "已取消",
        "SAFETY_STOPPED": "已安全停止",
        "CONFIRMED": "已确认",
        "DRAFT": "待确认",
    }.get(str(value), _human_value(value))


def _result_title(payload: dict[str, object]) -> str:
    if payload.get("kind") == "project":
        return "界鉴项目检查"
    if "decision" in payload and "gate_result_id" in payload:
        return "界鉴回归门禁"
    if "coverage_record_count" in payload or "evidence_count" in payload:
        return "界鉴检查结果"
    if "recording_id" in payload:
        return "界鉴流程录制"
    if "report_id" in payload or ("verdict" in payload and "evidence" in payload):
        return "界鉴报告"
    if "verdict" in payload:
        return "界鉴检查"
    return "界鉴"


def _supports_unicode(stream=None) -> bool:
    target = stream or click.get_text_stream("stdout")
    encoding = getattr(target, "encoding", None) or "utf-8"
    try:
        "✓×├─⠹".encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return False
    return True


def _marker(value: object, *, unicode: bool) -> tuple[str, str | None]:
    raw = str(value).upper()
    if value is True or raw in {"PASS", "SAFE", "COMPLETED", "SUCCEEDED", "VERIFIED", "AVAILABLE", "OK"}:
        return ("✓" if unicode else "OK", "green")
    if value is False or raw in {"BLOCK", "VULNERABLE", "FAILED", "INVALID", "ERROR", "UNAVAILABLE"}:
        return ("×" if unicode else "FAILED", "red")
    if raw in {"RUNNING", "PROCESSING", "TESTING"}:
        return ("●" if unicode else "RUNNING", "cyan")
    if raw in {"INCONCLUSIVE", "SAFETY_STOPPED", "CANCELLED"}:
        return ("!", "yellow")
    return ("○" if unicode else "-", None)


def _emit_section(title: str, rows: list[tuple[str, object, str]], *, err: bool = False) -> None:
    if not rows:
        return
    stream = click.get_text_stream("stderr" if err else "stdout")
    unicode = _supports_unicode(stream)
    typer.echo(title, err=err)
    for index, (label, value, marker_value) in enumerate(rows):
        branch = ("└─" if index == len(rows) - 1 else "├─") if unicode else ("`--" if index == len(rows) - 1 else "|--")
        content = f"{label}：{value}" if label else str(value)
        if marker_value:
            marker, color = _marker(marker_value, unicode=unicode)
            typer.secho(f"{branch} {content}  {marker}", fg=color, err=err)
        else:
            typer.echo(f"{branch} {content}", err=err)


def _result_sections(payload: dict[str, object]) -> list[tuple[str, list[tuple[str, object, str]]]]:
    shown = {"schema_version", "kind"}
    sections: list[tuple[str, list[tuple[str, object, str]]]] = []
    if "project_id" in payload:
        shown.add("project_id")
        sections.append(("应用", [("名称", _human_value(payload["project_id"]), "")]))
    status_rows: list[tuple[str, object, str]] = []
    for key in ("valid", "state", "lifecycle"):
        if key not in payload:
            continue
        shown.add(key)
        value = payload[key]
        label = _FIELD_LABELS[key]
        status_rows.append((label, "通过" if key == "valid" and value is True else _status_value(value), str(value)))
    if status_rows:
        sections.append(("状态", status_rows))
    result_rows: list[tuple[str, object, str]] = []
    for key in ("verdict", "decision", "coverage_record_count", "coverage_gap_count", "evidence_count", "artifact_dir"):
        if key not in payload:
            continue
        shown.add(key)
        value = payload[key]
        if key == "verdict":
            rendered = _outcome(value)
        elif key == "decision":
            rendered = {
                "PASS": "交付门禁通过",
                "BLOCK": "交付门禁阻断",
                "INCONCLUSIVE": "交付门禁证据不足",
                "ERROR": "交付门禁错误",
            }.get(str(value), _human_value(value))
        elif key in {"coverage_record_count", "coverage_gap_count", "evidence_count"}:
            rendered = f"{_human_value(value)} 项"
        else:
            rendered = _human_value(value)
        result_rows.append((_FIELD_LABELS[key], rendered, str(value) if key in {"verdict", "decision"} else ""))
    if result_rows:
        sections.append(("检查结果", result_rows))
    return sections


def emit_human(payload: object) -> None:
    if not isinstance(payload, dict):
        typer.echo("界鉴")
        typer.echo("")
        _emit_section("结果", [("内容", _human_value(payload), "")])
        return
    typer.echo(_result_title(payload))
    for title, rows in _result_sections(payload):
        typer.echo("")
        _emit_section(title, rows)


def emit_doctor(report: object) -> None:
    if presentation_mode() != "human":
        model_dump = report.model_dump(mode="json")
        emit_json(model_dump)
        return
    typer.echo("界鉴运行环境")
    typer.echo("")
    conclusion = "所有必要检查均已通过" if report.ok else "存在必要检查失败"
    marker, color = _marker("PASS" if report.ok else "FAILED", unicode=_supports_unicode())
    typer.secho(f"{conclusion}  {marker}", fg=color)
    typer.echo("")
    rows = []
    for check in report.checks:
        label = _DOCTOR_LABELS.get(check.name, check.name)
        rows.append(
            (
                label,
                _doctor_value(check),
                "PASS" if check.ok else "FAILED" if check.required else "",
            )
        )
    _emit_section("检查项", rows)
    for check in report.checks:
        if check.ok or not check.required:
            continue
        label = _DOCTOR_LABELS.get(check.name, check.name)
        typer.echo("")
        typer.secho(f"× {label}不可用", fg="red")
        typer.echo("")
        _emit_section("原因", [("", check.message, "")])
        typer.echo("")
        _emit_section("如何解决", [("", _doctor_recovery(check.name), "")])


def emit_result_presentation(presentation: object) -> None:
    """直接展示后端结果投影；CLI 不从 Evidence 重新推导业务结论。"""

    marker, color = _marker(
        presentation.verdict or presentation.run_lifecycle,
        unicode=_supports_unicode(),
    )
    typer.echo(presentation.headline)
    typer.echo("")
    typer.secho(presentation.scope_statement, fg=color)
    typer.echo("")
    _emit_section(
        "检查概览",
        [
            ("本次检查", f"{presentation.checked_count} 项", ""),
            ("符合预期", f"{presentation.safe_count} 项", ""),
            ("权限问题", f"{presentation.problem_count} 项", ""),
            ("证据不足", f"{presentation.inconclusive_count} 项", ""),
            ("权限要求未覆盖", f"{presentation.uncovered_count} 项", ""),
        ],
    )
    if presentation.execution_problem:
        typer.echo("")
        _emit_section("执行状态", [("", presentation.execution_problem, "FAILED")])
    if presentation.repair_verification is not None:
        typer.echo("")
        _emit_section(
            "修复验证",
            [
                (
                    "修复要求",
                    presentation.repair_verification.message,
                    presentation.repair_verification.status.value,
                )
            ],
        )
    if presentation.issues:
        typer.echo("")
        _emit_section(
            "权限问题与检查项",
            [
                (
                    issue.title,
                    f"{issue.conclusion}；{issue.explanation}",
                    issue.verdict.value,
                )
                for issue in presentation.issues
            ],
        )
        for issue in presentation.issues:
            if issue.repair_requirement is not None:
                typer.echo("")
                _emit_section(
                    f"{issue.title} · 修复后必须满足",
                    [
                        ("必须消失", issue.repair_requirement.must_disappear, ""),
                        ("必须保持", issue.repair_requirement.must_remain, ""),
                        *(
                            ("不能改变", item, "")
                            for item in issue.repair_requirement.must_not_change
                        ),
                    ],
                )
            diagnosis = getattr(issue, "diagnosis", None)
            if diagnosis is not None:
                typer.echo("")
                _emit_section(
                    f"{issue.title} · 权限断裂诊断",
                    [
                        (
                            item.label,
                            item.detail,
                            (
                                (
                                    diagnosis.breakpoint_type.value
                                    if diagnosis.breakpoint_type is not None
                                    else "UNLOCATED"
                                )
                                if item.kind == "BREAKPOINT"
                                else ""
                            ),
                        )
                        for item in diagnosis.minimal_witness
                    ],
                )
                if diagnosis.confirmed_impacts:
                    typer.echo("")
                    _emit_section(
                        f"{issue.title} · 已确认影响",
                        [
                            (impact.kind.value, impact.summary, "CONFIRMED")
                            for impact in diagnosis.confirmed_impacts
                        ],
                    )
            sources = getattr(issue, "evidence_sources", ())
            if not sources:
                continue
            typer.echo("")
            _emit_section(
                f"{issue.title} · 证据来源",
                [
                    (
                        _evidence_role_label(source.role),
                        f"{source.label}：{_evidence_status_label(source.status)}",
                        source.status,
                    )
                    for source in sources
                ],
            )
    if presentation.limitations:
        typer.echo("")
        _emit_section(
            "限制与下一步",
            [("", item, "") for item in presentation.limitations],
        )


def _evidence_role_label(value: object) -> str:
    return {"KEY": "关键来源", "SUPPORTING": "辅助来源"}.get(
        str(getattr(value, "value", value)),
        "证据来源",
    )


def _evidence_status_label(value: object) -> str:
    return {
        "FOUND": "已取得",
        "NOT_FOUND": "未观察到",
        "UNAVAILABLE": "当前不可用",
    }.get(str(getattr(value, "value", value)), str(value))


def emit_status(status: object) -> None:
    """以与 Web 工作区相同的区域和待办展示统一状态 View。"""

    project = status.project
    typer.echo("界鉴工作台")
    typer.echo("")
    if project is None:
        _emit_section("当前应用", [("", "尚未接入应用", "")])
    else:
        _emit_section("当前应用", [("名称", project.name, "")])
    typer.echo("")
    _emit_section(
        "持续验证工作区",
        [
            (area.label, area.status_label, area.status)
            for area in status.areas
        ],
    )
    if status.attention_items:
        typer.echo("")
        _emit_section(
            "需要处理",
            [
                (item.label, item.description, item.tone)
                for item in status.attention_items
            ],
        )
    if status.latest_result is not None:
        typer.echo("")
        _emit_section(
            "最近检查",
            [
                ("结论", status.latest_result.headline, status.latest_result.verdict or ""),
                ("范围", status.latest_result.scope_statement, ""),
            ],
        )


def emit_command(
    kind: str,
    data: object,
    *,
    next_actions: Sequence[object] = (),
    warnings: Sequence[object] = (),
    human: Callable[[], None] | None = None,
) -> None:
    """一次业务结果在 Human 与稳定 Machine v1 之间选择唯一 renderer。"""

    if presentation_mode() == "human":
        if human is not None:
            human()
        else:
            payload = data.model_dump(mode="json") if hasattr(data, "model_dump") else data
            if isinstance(payload, (list, tuple)):
                typer.echo("界鉴")
                typer.echo("")
                rows: list[tuple[str, object, str]] = []
                for index, item in enumerate(payload, start=1):
                    if isinstance(item, dict):
                        label = next(
                            (
                                str(item[key])
                                for key in ("name", "label", "action_display_name", "headline")
                                if item.get(key)
                            ),
                            f"第 {index} 项",
                        )
                        state = next(
                            (str(item[key]) for key in ("status", "state", "verdict") if item.get(key)),
                            "",
                        )
                        rows.append((label, _status_value(state) if state else "已读取", state))
                    else:
                        rows.append((f"第 {index} 项", "已读取", ""))
                _emit_section("结果", rows or [("", "暂无记录", "")])
            else:
                emit_human(payload)
        return
    payload = data.model_dump(mode="json") if hasattr(data, "model_dump") else data
    typer.echo(
        json.dumps(
            {
                "schema_version": "1",
                "kind": kind,
                "status": "ok",
                "data": payload,
                "next_actions": list(next_actions),
                "warnings": list(warnings),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
def _doctor_value(check: object) -> str:
    details = check.details
    if check.name in {"python", "node", "pnpm"} and details.get("version"):
        return str(details["version"])
    if not check.ok:
        return "不可用"
    return {
        "dependencies": "已准备",
        "config": "正常",
        "var_dir": "可写",
        "sqlite": "SQLite 可用",
        "playwright": "Chromium 可用",
        "loopback": "可用",
        "redaction": "正常",
    }.get(check.name, check.message)


def _doctor_recovery(name: str) -> str:
    if name in {"node", "pnpm", "dependencies", "playwright"}:
        return "重新运行 .\\start.cmd，让界鉴修复运行环境。"
    if name == "config":
        return "检查配置文件路径和内容后重试。"
    if name == "var_dir":
        return "确认运行目录存在且当前用户可以写入。"
    return "查看运行日志，修复对应环境问题后重试。"


def emit_json(payload: object) -> None:
    if presentation_mode() == "human":
        emit_human(payload)
        return
    typer.echo(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def fail(error: JiejianError) -> NoReturn:
    if presentation_mode() == "human":
        payload = error.to_dict()
        stream = click.get_text_stream("stderr")
        cross = "×" if _supports_unicode(stream) else "FAILED"
        branch = "└─" if _supports_unicode(stream) else "`--"
        typer.secho(f"{cross} {_error_title(error)}", fg="red", err=True)
        typer.echo("", err=True)
        typer.echo("原因", err=True)
        typer.secho(f"{branch} {payload['message']}", fg="red", err=True)
        typer.echo("", err=True)
        typer.echo("如何解决", err=True)
        typer.secho(f"{branch} {_recovery_for(error)}", fg="yellow", err=True)
        details = payload.get("details") or {}
        log_path = details.get("log_path") if isinstance(details, dict) else None
        if isinstance(log_path, str) and log_path:
            typer.echo("", err=True)
            typer.echo("日志", err=True)
            typer.echo(f"{branch} {log_path}", err=True)
        typer.echo("", err=True)
        typer.echo("错误代码", err=True)
        typer.secho(f"{branch} {error.code}", fg="red", err=True)
    else:
        options = _options()
        payload = error.to_dict()
        details = payload.get("details")
        trace_id = getattr(options, "trace_id", None) or (
            details.get("trace_id") if isinstance(details, dict) else None
        ) or f"cli-{uuid4().hex}"
        typer.echo(
            json.dumps(
                {
                    "schema_version": "1",
                    "kind": "error",
                    "status": "error",
                    "data": None,
                    "next_actions": [],
                    "warnings": [],
                    "error": {
                        "error_code": error.code,
                        "message": payload["message"],
                        "details": details if isinstance(details, dict) else {},
                        "trace_id": trace_id,
                        "recovery": _recovery_for(error),
                    },
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
    input_codes = {
        ErrorCode.CFG_FILE.value,
        ErrorCode.CFG_INVALID.value,
        ErrorCode.INPUT_FILE.value,
        ErrorCode.INPUT_INVALID.value,
        ErrorCode.INPUT_PATH.value,
        ErrorCode.SECRET_MISSING.value,
        ErrorCode.REPORT_NOT_FOUND.value,
        ErrorCode.REPORT_INPUT_INVALID.value,
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


@contextmanager
def human_wait(message: str):
    """只在交互式人类模式向 stderr 展示可清理的不确定等待动画。"""

    stream = click.get_text_stream("stderr")
    if presentation_mode() != "human" or not getattr(stream, "isatty", lambda: False)():
        yield
        return
    unicode = _supports_unicode(stream)
    frames = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏") if unicode else ("|", "/", "-", "\\")
    stopped = threading.Event()

    def animate() -> None:
        index = 0
        while not stopped.wait(0.09):
            stream.write(f"\r{frames[index % len(frames)]} {message}")
            stream.flush()
            index += 1

    worker = threading.Thread(target=animate, name="jiejian-cli-spinner", daemon=True)
    worker.start()
    try:
        yield
    finally:
        stopped.set()
        worker.join(timeout=0.5)
        stream.write("\r" + (" " * min(120, max(48, len(message) + 8))) + "\r")
        stream.flush()


def _error_title(error: JiejianError) -> str:
    code = error.code
    if code in {ErrorCode.CFG_FILE.value, ErrorCode.CFG_INVALID.value, ErrorCode.INPUT_FILE.value, ErrorCode.INPUT_INVALID.value, ErrorCode.INPUT_PATH.value}:
        return "输入信息不可用"
    if code.startswith("SCOPE_") or code.startswith("AUTH_") or code.startswith("EXEC_BUDGET"):
        return "授权或安全范围不符合要求"
    if code == ErrorCode.SERVE_FAILED.value:
        return "本地服务无法启动"
    if code == ErrorCode.WORKSPACE_ALREADY_CONTROLLED.value:
        return "当前运行目录正在使用"
    if code.startswith("STORAGE_") or code.startswith("JOB_"):
        return "后台检查未完成"
    if code.startswith("RUNNER_") or code.startswith("RECORD_"):
        return "检查执行未完成"
    return "操作未完成"


def _recovery_for(error: JiejianError) -> str:
    code = error.code
    if code in {ErrorCode.CFG_FILE.value, ErrorCode.CFG_INVALID.value}:
        return "修正配置文件路径、格式和版本后重试。"
    if code in {
        ErrorCode.INPUT_FILE.value,
        ErrorCode.INPUT_INVALID.value,
        ErrorCode.INPUT_PATH.value,
    }:
        return "检查命令参数、输入文件路径和文件格式后重试。"
    if code == ErrorCode.SECRET_MISSING.value:
        return "在当前进程环境配置所需身份变量后重试。"
    if code in {
        ErrorCode.SCOPE_URL.value,
        ErrorCode.SCOPE_HOST.value,
        ErrorCode.SCOPE_PORT.value,
        ErrorCode.SCOPE_PRIVATE_NETWORK.value,
        ErrorCode.SCOPE_REDIRECT.value,
        ErrorCode.EXEC_BUDGET.value,
        ErrorCode.EXEC_RESPONSE_TOO_LARGE.value,
    }:
        return "检查授权目标范围、重定向和执行预算，仅在授权范围内重试。"
    if code in {ErrorCode.REPORT_NOT_FOUND.value, ErrorCode.REPORT_INPUT_INVALID.value}:
        return "确认运行 ID、报告 ID 和 var-dir 指向已发布且完整的结果。"
    if code == ErrorCode.SERVE_FAILED.value:
        return "检查本机回环地址、端口和前端静态资源后重试。"
    if code == ErrorCode.WORKSPACE_ALREADY_CONTROLLED.value:
        return "关闭正在使用同一运行目录的界鉴窗口或 CLI，或显式选择其他 --var-dir。"
    if code.startswith("STORAGE_") or code.startswith("JOB_"):
        return "检查 var-dir 数据库、迁移状态和任务日志后重试。"
    if code.startswith("RUNNER_") or code.startswith("RECORD_"):
        return "检查 Worker、隔离进程和运行目录日志后重试。"
    if code == ErrorCode.EXEC_CANCELLED.value:
        return "任务已安全取消；如需继续，请重新提交运行。"
    return "根据错误代码检查运行日志和当前配置后重试。"
