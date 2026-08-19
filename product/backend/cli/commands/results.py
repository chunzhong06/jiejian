# Results 与 CI CLI 命令组
# 读取已发布结果并映射稳定 CI 退出语义，不重新执行或改写 Verdict。

from __future__ import annotations

from pathlib import Path

import typer
from click import get_binary_stream

from product.backend.core.lifecycle import RunVerdict
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.cli.bootstrap import application_scope
from product.backend.cli.presentation import emit_json, fail, force_machine_mode


def report_command(
    context: typer.Context,
    run_id: str,
    output_format: str = typer.Option("json", "--format", help="报告格式"),
    gate_result_id: str | None = typer.Option(None, "--gate-result-id", help="显式 GateResult ID；提供时生成统一报告"),
    report_id: str | None = typer.Option(None, "--report-id", help="读取已发布统一报告 ID"),
) -> None:
    """按运行 ID 读取当前已发布结果或当前报告。"""

    try:
        with application_scope(context) as application:
            selected_id = report_id
            if gate_result_id is not None:
                if report_id is not None:
                    fail(JiejianError(ErrorCode.INPUT_INVALID, "不能同时指定 GateResult 和 report_id"))
                payload = application.reports.generate(run_id, gate_result_id)
                selected_id = str(payload["report_id"])
            elif selected_id is None:
                reports = application.reports.list(run_id)
                if len(reports) == 0:
                    fail(JiejianError(ErrorCode.REPORT_NOT_FOUND, "当前 Run 没有统一报告"))
                if len(reports) > 1:
                    fail(JiejianError(ErrorCode.INPUT_INVALID, "当前 Run 有多份报告，请指定 --report-id"))
                selected_id = str(reports[0]["report_id"])
            if output_format.lower() == "json":
                emit_json(application.reports.read(run_id, selected_id))
            else:
                get_binary_stream("stdout").write(
                    application.reports.read_format(run_id, selected_id, output_format.lower())
                )
    except JiejianError as exc:
        fail(exc)


def ci_command(context: typer.Context, profile_path: Path) -> None:
    """提交持久门禁任务，并用 0/1/2 表示安全结论。"""

    force_machine_mode()
    try:
        with application_scope(context) as application:
            result = application.execution.run_profile(
                profile_path,
                idempotency_key=f"ci-{profile_path.stem}",
            )
        emit_json(result.model_dump(mode="json"))
        raise typer.Exit(
            code={
                RunVerdict.PASS: 0,
                RunVerdict.BLOCK: 1,
                RunVerdict.INCONCLUSIVE: 2,
            }.get(result.verdict, 2)
        )
    except JiejianError as exc:
        fail(exc)
