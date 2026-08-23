# Verification Run CLI 命令组。
#
# 定位：当前 WebExecutionProfile 的命令行适配器；提交、等待和结果读取
# 均由唯一 ExecutionWorkflow 编排，CLI 不直接装配执行基础设施。

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import typer

from product.backend.cli.bootstrap import application_scope
from product.backend.cli.presentation import emit_json, fail, human_wait
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import RunnerResultType


def run_command(
    context: typer.Context,
    profile_path: Path,
    accept_source_changes: bool = typer.Option(False, "--accept-profile-changes", help="显式接受当前 Web 执行配置文件变化"),
) -> None:
    """登记当前执行配置并等待隔离 Runner 的当前结果。"""

    try:
        with application_scope(context, environ=os.environ) as application:
            with human_wait("正在执行安全检查"):
                result = application.execution.run_profile(
                    profile_path,
                    accept_source_changes=accept_source_changes,
                    idempotency_key=f"cli-{uuid4().hex}",
                )
        _emit_or_fail(result)
    except JiejianError as exc:
        fail(exc)


def _emit_or_fail(result) -> None:
    if result.result_type is RunnerResultType.SUCCESS:
        emit_json(result.model_dump(mode="json"))
        return
    if result.result_type is RunnerResultType.SAFETY_STOPPED:
        raise JiejianError(result.reason_codes[0], "Runner 因安全边界主动停止")
    if result.result_type is RunnerResultType.CANCELLED:
        raise JiejianError(ErrorCode.EXEC_CANCELLED, "运行已经安全取消")
    error_code = result.error.code if result.error is not None else ErrorCode.RUNNER_RESULT_MISSING.value
    raise JiejianError(error_code, "Runner 执行未形成安全结论")
