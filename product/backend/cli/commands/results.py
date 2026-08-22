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
    gate_result_id: str | None = typer.Option(None, "--gate-result-id", help="显式门禁结果 ID；提供时生成统一报告"),
    report_id: str | None = typer.Option(None, "--report-id", help="读取已发布统一报告 ID"),
) -> None:
    """按运行 ID 读取基础报告或明确生成/读取 Gate 报告。"""

    try:
        with application_scope(context) as application:
            selected_id = report_id
            if gate_result_id is not None:
                if report_id is not None:
                    fail(JiejianError(ErrorCode.INPUT_INVALID, "不能同时指定 GateResult 和 report_id"))
                payload = application.reports.generate_gate(run_id, gate_result_id).model_dump(mode="json")
                selected_id = str(payload["report_id"])
            elif selected_id is None:
                selected_id = str(application.result_finalizer.status(run_id).base_report_id or "")
                if not selected_id:
                    fail(JiejianError(ErrorCode.RESULT_FINALIZATION_NOT_READY, "基础报告尚未完成；请执行 jiejian result-repair " + run_id))
            if output_format.lower() == "json":
                emit_json(application.reports.read(run_id, selected_id))
            else:
                get_binary_stream("stdout").write(
                    application.reports.read_format(run_id, selected_id, output_format.lower())
                )
    except JiejianError as exc:
        fail(exc)


def result_repair_command(context: typer.Context, run_id: str) -> None:
    """显式恢复 Finding 或基础报告最终化状态。"""

    try:
        with application_scope(context) as application:
            emit_json(application.result_finalizer.repair(run_id).model_dump(mode="json"))
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
