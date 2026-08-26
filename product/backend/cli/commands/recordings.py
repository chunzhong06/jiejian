# Recording CLI 命令组
# 编排 Recording 提交、等待、审阅和完成；浏览器执行仍位于受控 Worker 边界。

from __future__ import annotations

import os
from pathlib import Path
import time
from uuid import uuid4

import typer

from product.backend.core.recording import RecordingState
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import RecordingBudget, RecordingRunnerRequest, parse_flow_draft_review_command
from product.backend.workflows.recording.submission import SubmitRecording
from product.backend.cli.bootstrap import application_scope
from product.backend.cli.presentation import emit_json, fail, human_wait
from product.backend.workflows.recording.flow_compiler import compile_flow_bindings
from product.protocols import parse_web_execution_profile


def recording_start_command(
    context: typer.Context,
    profile_path: Path,
    action_candidate_id: str = typer.Option(
        ...,
        "--action",
        help="已确认业务动作候选 ID",
    ),
    test_identity_id: str = typer.Option(
        ...,
        "--test-identity",
        help="已准备测试身份 ID",
    ),
    duration_seconds: int = typer.Option(
        60,
        "--duration-seconds",
        min=1,
        max=3_600,
        help="有界录制时长",
    ),
    headless: bool = typer.Option(
        True,
        "--headless/--headed",
        help="是否无头运行浏览器",
    ),
) -> None:
    """校验项目并提交一次隔离 Recording。"""

    try:
        profile = parse_web_execution_profile(profile_path.resolve().read_bytes())
        now_us = time.time_ns() // 1_000
        duration_us = duration_seconds * 1_000_000
        with application_scope(context, environ=os.environ) as application:
            application.projects.register(profile_path)
            if action_candidate_id not in {
                item.action_id for item in profile.workflow_bindings
            }:
                raise JiejianError(ErrorCode.INPUT_INVALID, "执行配置未登记当前业务动作")
            recording_id = f"rec_{uuid4().hex}"
            session = application.recording_credentials.prepare(
                project_id=profile.project_id,
                test_identity_id=test_identity_id,
                recording_id=recording_id,
                session_ref=f"session_{uuid4().hex}",
                now_us=now_us,
                expires_at_us=now_us + duration_us,
            )
            request = RecordingRunnerRequest(
                schema_version="1",
                recording_id=recording_id,
                project_id=profile.project_id,
                action_candidate_id=action_candidate_id,
                created_at_us=now_us,
                target_scope=profile.target.scope,
                sessions=(session,),
                budget=RecordingBudget(max_duration_us=duration_us, max_contexts=1),
                headless=headless,
                trace_enabled=False,
            )
            try:
                submission = application.recording_runs.run(
                    SubmitRecording(
                        request=request,
                        flow_id=profile.profile_id,
                        idempotency_key=f"cli-recording-{uuid4().hex}",
                        max_attempts=3,
                        available_at_us=now_us,
                        now_us=now_us,
                    ),
                    timeout_seconds=duration_seconds + 30,
                )
                with human_wait("正在录制流程"):
                    view = application.recording_lifecycle.status(request.recording_id)
            finally:
                application.recording_credentials.clear(recording_id)
            emit_json(
                {
                    "schema_version": "1",
                    "recording_id": request.recording_id,
                    "job_id": submission.job.job_id,
                    "state": view.recording.state.value,
                    "draft_revision": view.draft.revision if view.draft else None,
                }
            )
    except JiejianError as exc:
        fail(exc)


def recording_status_command(context: typer.Context, recording_id: str) -> None:
    """查看 Recording 状态和当前 FlowDraft revision。"""

    try:
        with application_scope(context, environ=os.environ) as application:
            view = application.recording_lifecycle.status(recording_id)
            emit_json(view.model_dump(mode="json"))
    except JiejianError as exc:
        fail(exc)


def recording_review_command(
    context: typer.Context,
    recording_id: str,
    command_path: Path = typer.Option(..., "--command", help="流程审阅命令 JSON"),
) -> None:
    """应用一个不可变 FlowDraft 审阅命令并生成新 revision。"""

    try:
        command = parse_flow_draft_review_command(command_path.read_bytes())
        with application_scope(context, environ=os.environ) as application:
            view = application.recording_lifecycle.review(recording_id, command)
            emit_json(view.model_dump(mode="json"))
    except (OSError, JiejianError) as exc:
        fail(
            exc
            if isinstance(exc, JiejianError)
            else JiejianError(ErrorCode.INPUT_FILE, "审阅命令文件不可读取")
        )


def recording_finalize_command(
    context: typer.Context,
    recording_id: str,
) -> None:
    """确认已满足审阅门禁，原子发布最终 Flow 并完成 Recording。"""

    try:
        with application_scope(context, environ=os.environ) as application:
            view = application.recording_lifecycle.finalize(
                recording_id,
                var_dir=application.var_dir,
                now_us=time.time_ns() // 1_000,
            )
            emit_json(view.model_dump(mode="json"))
    except JiejianError as exc:
        fail(exc)


def recording_replay_command(
    context: typer.Context,
    recording_id: str,
    profile_path: Path = typer.Option(..., "--profile", help="当前 Web 执行配置（WebExecutionProfile）JSON"),
    runs: int = typer.Option(3, "--runs", min=1, max=3, help="连续回放次数"),
) -> None:
    """通过独立 Verification Runner 连续回放已完成 Flow。"""

    try:
        with application_scope(context, environ=os.environ) as application:
            workflow = application.recording_lifecycle
            record = application.execution.register(profile_path, accept_source_changes=False)
            profile = application.execution.current(record.profile_id)
            with application.uow_factory() as work:
                recording = work.recordings.get(recording_id)
            if (
                recording is None
                or recording.state is not RecordingState.COMPLETED
                or recording.project_id != profile.project_id
            ):
                raise JiejianError(
                    ErrorCode.RECORD_REVIEW_STATE,
                    "录制尚未完成，不能回放",
            )
            flow = workflow.load_final_flow(workflow.flow_path(application.var_dir, recording))
            target_override, workflow_bindings_override = compile_flow_bindings(flow, profile)
            with human_wait("正在回放并检查流程"):
                results = [
                    application.execution.run_profile(
                        profile_path,
                        accept_source_changes=index == 0,
                        target_override=target_override,
                        workflow_bindings_override=workflow_bindings_override,
                        idempotency_key=f"recording-replay:{recording_id}:{index}:{uuid4().hex}",
                    ).model_dump(mode="json")
                    for index in range(runs)
                ]
        emit_json(
            {
                "schema_version": "1",
                "recording_id": recording_id,
                "runs": results,
            }
        )
    except (OSError, JiejianError) as exc:
        fail(
            exc
            if isinstance(exc, JiejianError)
            else JiejianError(ErrorCode.RECORD_REPLAY_FAILED, "回放输入不可读取")
        )
