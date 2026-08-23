# Recording CLI 命令组
# 编排 Recording 提交、等待、审阅和完成；浏览器执行仍位于受控 Worker 边界。

from __future__ import annotations

import json
import os
from pathlib import Path
import time
from uuid import uuid4

import typer

from product.backend.core.recording import RecordingState
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import RecordingBudget, RecordingRunnerRequest, RecordingSessionRef, parse_flow_draft_review_command, required_identity_secret_refs
from product.backend.workflows.recording.submission import SubmitRecording
from product.backend.cli.bootstrap import application_scope
from product.backend.cli.presentation import emit_json, fail, human_wait
from product.backend.workflows.recording.review import compile_flow_bindings
from product.protocols import parse_web_execution_profile


def recording_start_command(
    context: typer.Context,
    profile_path: Path,
    identity: list[str] | None = typer.Option(
        None,
        "--identity",
        help="录制身份 ID；可重复指定，默认使用项目全部身份",
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
        selected = identity or [item.identity_id for item in profile.identities]
        known = {item.identity_id for item in profile.identities}
        if not selected or len(set(selected)) != len(selected) or any(
            item not in known for item in selected
        ):
            raise JiejianError(ErrorCode.INPUT_INVALID, "录制身份选择无效")
        now_us = time.time_ns() // 1_000
        duration_us = duration_seconds * 1_000_000
        identities_by_id = {item.identity_id: item for item in profile.identities}
        request = RecordingRunnerRequest(
            schema_version="2",
            recording_id=f"rec_{uuid4().hex}",
            project_id=profile.project_id,
            created_at_us=now_us,
            target_scope=profile.target.scope,
            sessions=tuple(
                RecordingSessionRef(
                    identity_id=item,
                    session_ref=f"session_{uuid4().hex}",
                    secret_refs=required_identity_secret_refs(identities_by_id[item]),
                    expires_at_us=now_us + duration_us,
                )
                for item in selected
            ),
            budget=RecordingBudget(
                max_duration_us=duration_us,
                max_contexts=len(selected),
            ),
            headless=headless,
            trace_enabled=False,
        )
        with application_scope(context, environ=os.environ) as application:
            application.projects.register(profile_path)
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
    bindings_path: Path | None = typer.Option(
        None,
        "--bindings",
        help="显式身份/资源绑定 JSON，可选",
    ),
) -> None:
    """应用一个不可变 FlowDraft 审阅命令并生成新 revision。"""

    try:
        command = parse_flow_draft_review_command(command_path.read_bytes())
        bindings = _load_recording_bindings(bindings_path) if bindings_path else None
        with application_scope(context, environ=os.environ) as application:
            view = application.recording_lifecycle.review(
                recording_id,
                command,
                bindings=bindings,
            )
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


def _load_recording_bindings(path: Path) -> dict[str, dict[str, str]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise JiejianError(ErrorCode.INPUT_FILE, "绑定文件不可读取") from None
    if not isinstance(value, dict):
        raise JiejianError(ErrorCode.INPUT_INVALID, "绑定文件必须是对象")
    result: dict[str, dict[str, str]] = {}
    for step_id, binding in value.items():
        if not isinstance(step_id, str) or not isinstance(binding, dict):
            raise JiejianError(ErrorCode.INPUT_INVALID, "绑定文件结构无效")
        if any(
            not isinstance(key, str) or not isinstance(item, str)
            for key, item in binding.items()
        ):
            raise JiejianError(ErrorCode.INPUT_INVALID, "绑定文件值无效")
        result[step_id] = dict(binding)
    return result
