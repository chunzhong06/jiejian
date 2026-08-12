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
) -> None:
    """按运行 ID 读取完整性校验后的 JSON 报告。"""

    if output_format.lower() != "json":
        fail(JiejianError(ErrorCode.INPUT_INVALID, "阶段 1 只支持 JSON 报告"))
    try:
        settings = runtime_settings(context)
        _require_published_completion(settings.var_dir, run_id)
        emit_json(load_report(settings.var_dir, run_id))
    except JiejianError as exc:
        fail(exc)


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
