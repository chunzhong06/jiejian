# =============================================================================
# Results 与 CI CLI 命令组
#
# 定位
#   已发布结果读取和 CI 门禁退出语义的命令行适配器
#
# 职责
#   读取可信报告｜要求完成 publication｜映射 Verdict 到稳定退出码
#
# 调用链
#   Typer → report / ci commands → Published artifacts / persisted Run
# =============================================================================

from __future__ import annotations

from pathlib import Path

import typer
from click import get_binary_stream

from ...domain.lifecycle import RunLifecycle, RunVerdict
from ...errors import ErrorCode, JiejianError
from ...verification.artifacts import load_report
from ..bootstrap import runtime_settings
from ..presentation import emit_json, fail
from .runs import _run_persisted_job


def report_command(
    context: typer.Context,
    run_id: str,
    output_format: str = typer.Option("json", "--format", help="报告格式"),
    v2: bool = typer.Option(False, "--v2", help="读取或生成统一报告 V2"),
    gate_result_id: str | None = typer.Option(None, "--gate-result-id", help="显式 GateResult ID；提供时生成 V2 报告"),
    report_id: str | None = typer.Option(None, "--report-id", help="读取已发布 V2 报告 ID"),
) -> None:
    """按运行 ID 读取历史 V1 报告或显式 V2 统一报告。"""

    if not v2 and output_format.lower() != "json":
        fail(JiejianError(ErrorCode.INPUT_INVALID, "阶段 1 只支持 JSON 报告"))
    application = None
    try:
        settings = runtime_settings(context)
        if v2:
            from ...application.context import ApplicationContext

            application = ApplicationContext(settings.var_dir)
            if gate_result_id is not None:
                if report_id is not None:
                    fail(JiejianError(ErrorCode.INPUT_INVALID, "V2 报告不能同时指定 GateResult 和 report_id"))
                payload = application.reports.generate(run_id, gate_result_id)
                if output_format.lower() == "json":
                    emit_json(payload)
                else:
                    get_binary_stream("stdout").write(application.reports.read_format(run_id, payload["report_id"], output_format.lower()))
                return
            if report_id is None:
                fail(JiejianError(ErrorCode.INPUT_INVALID, "V2 报告必须指定 --gate-result-id 或 --report-id"))
            raw = application.reports.read_format(run_id, report_id, output_format.lower())
            if output_format.lower() == "json":
                emit_json(application.reports.read(run_id, report_id))
            else:
                get_binary_stream("stdout").write(raw)
            return
        _require_published_completion(settings.var_dir, run_id)
        emit_json(load_report(settings.var_dir, run_id))
    except JiejianError as exc:
        fail(exc)
    finally:
        if application is not None:
            application.close()


def ci_command(context: typer.Context, project_path: Path) -> None:
    """提交持久门禁任务，并用 0/1/2 表示安全结论。"""

    try:
        settings = runtime_settings(context)
        from ...verification.inputs import load_project_bundle

        bundle = load_project_bundle(project_path)
        result = _run_persisted_job(settings, bundle)
        emit_json(result.model_dump(mode="json"))
        raise typer.Exit(
            code={
                RunVerdict.PASS: 0,
                RunVerdict.BLOCK: 1,
                RunVerdict.INCONCLUSIVE: 2,
            }[result.verdict]
        )
    except JiejianError as exc:
        fail(exc)


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
    from ...storage import (
        StorageUnitOfWork,
        create_session_factory,
        create_sqlite_engine,
        default_database_path,
    )

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
