# =============================================================================
# Recording CLI 命令组
#
# 定位
#   Recording 提交、等待、审阅和完成动作的命令行编排边界
#
# 职责
#   复用 Recording 应用能力｜监督本地 Job｜保持取消和错误输出语义
#
# 调用链
#   Typer → recording commands → Recording services / WorkerDispatcher
# =============================================================================

from __future__ import annotations

import json
import os
from functools import partial
from pathlib import Path
import time
from uuid import uuid4

import typer

from ...recording.models import RecordingState
from ...errors import ErrorCode, JiejianError
from ...protocols import (
    RecordingBudgetV1,
    RecordingRunnerRequestV1,
    RecordingSessionRefV1,
    parse_flow_draft_review_command,
)
from ...projects.service import ProjectControlService
from ...recording.application import RecordingApplicationService, SubmitRecordingV1
from ...recording.request_store import RecordingRequestStore
from ...recording.workflow import RecordingWorkflow
from ...storage import ProjectRecord, StorageUnitOfWork
from ...verification.inputs import ProjectBundle, load_project_bundle
from ...execution.dispatch import WorkerDispatcher
from ..bootstrap import open_storage, runtime_settings
from ..presentation import emit_json, fail
from .runs import _run_persisted_job


def recording_start_command(
    context: typer.Context,
    project_path: Path,
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
        settings = runtime_settings(context)
        bundle = load_project_bundle(project_path)
        selected = identity or [item.id for item in bundle.project.identities]
        known = {item.id for item in bundle.project.identities}
        if not selected or len(set(selected)) != len(selected) or any(
            item not in known for item in selected
        ):
            raise JiejianError(ErrorCode.INPUT_INVALID, "录制身份选择无效")
        now_us = time.time_ns() // 1_000
        duration_us = duration_seconds * 1_000_000
        request = RecordingRunnerRequestV1(
            schema_version="1",
            recording_id=f"rec_{uuid4().hex}",
            project_id=bundle.project.id,
            created_at_us=now_us,
            target_scope=bundle.project.target,
            sessions=tuple(
                RecordingSessionRefV1(
                    schema_version="1",
                    identity_id=item,
                    session_ref=f"session_{uuid4().hex}",
                    expires_at_us=now_us + duration_us,
                )
                for item in selected
            ),
            budget=RecordingBudgetV1(
                schema_version="1",
                max_duration_us=duration_us,
                max_contexts=len(selected),
            ),
            headless=headless,
            trace_enabled=False,
        )
        engine, factory = open_storage(settings)
        try:
            _ensure_project_record(factory, bundle, now_us)
            application = RecordingApplicationService(
                factory,
                RecordingRequestStore(settings.var_dir),
            )
            submission = application.submit(
                SubmitRecordingV1(
                    request=request,
                    flow_id=bundle.flow.id,
                    idempotency_key=f"cli-recording-{uuid4().hex}",
                    max_attempts=3,
                    available_at_us=now_us,
                    now_us=now_us,
                )
            )
            dispatcher = WorkerDispatcher(
                var_dir=settings.var_dir,
                uow_factory=factory,
                environ=os.environ,
            )
            process = dispatcher.start(
                job_id=submission.job.job_id,
                lease_owner=f"recording-worker-{uuid4().hex}",
                secret_names=(),
            )
            dispatcher.wait_recording(
                submission.job.job_id,
                process,
                timeout_seconds=duration_seconds + 30,
            )
            view = RecordingWorkflow(factory).status(request.recording_id)
            emit_json(
                {
                    "schema_version": "1",
                    "recording_id": request.recording_id,
                    "job_id": submission.job.job_id,
                    "state": view.recording.state.value,
                    "draft_revision": view.draft.revision if view.draft else None,
                }
            )
        finally:
            engine.dispose()
    except JiejianError as exc:
        fail(exc)


def recording_status_command(context: typer.Context, recording_id: str) -> None:
    """查看 Recording 状态和当前 FlowDraft revision。"""

    try:
        settings = runtime_settings(context)
        engine, factory = open_storage(settings)
        try:
            view = RecordingWorkflow(factory).status(recording_id)
            emit_json(view.model_dump(mode="json"))
        finally:
            engine.dispose()
    except JiejianError as exc:
        fail(exc)


def recording_review_command(
    context: typer.Context,
    recording_id: str,
    command_path: Path = typer.Option(..., "--command", help="Flow 审阅命令 JSON"),
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
        settings = runtime_settings(context)
        engine, factory = open_storage(settings)
        try:
            view = RecordingWorkflow(factory).review(
                recording_id,
                command,
                bindings=bindings,
            )
            emit_json(view.model_dump(mode="json"))
        finally:
            engine.dispose()
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
        settings = runtime_settings(context)
        engine, factory = open_storage(settings)
        try:
            view = RecordingWorkflow(factory).finalize(
                recording_id,
                var_dir=settings.var_dir,
                now_us=time.time_ns() // 1_000,
            )
            emit_json(view.model_dump(mode="json"))
        finally:
            engine.dispose()
    except JiejianError as exc:
        fail(exc)


def recording_replay_command(
    context: typer.Context,
    recording_id: str,
    project_path: Path = typer.Option(..., "--project", help="项目 YAML"),
    runs: int = typer.Option(3, "--runs", min=1, max=3, help="连续回放次数"),
) -> None:
    """通过独立 Verification Runner 连续回放已完成 Flow。"""

    try:
        settings = runtime_settings(context)
        bundle = load_project_bundle(project_path)
        engine, factory = open_storage(settings)
        try:
            workflow = RecordingWorkflow(factory)
            with factory() as work:
                recording = work.recordings.get(recording_id)
            if (
                recording is None
                or recording.state is not RecordingState.COMPLETED
                or recording.project_id != bundle.project.id
            ):
                raise JiejianError(
                    ErrorCode.RECORD_REVIEW_STATE,
                    "录制尚未完成，不能回放",
                )
            flow = workflow.load_final_flow(workflow.flow_path(settings.var_dir, recording))
        finally:
            engine.dispose()
        replay_bundle = ProjectBundle(
            project_file=bundle.project_file,
            project=bundle.project,
            flow=flow,
            contract=bundle.contract,
        )
        results = [
            _run_persisted_job(settings, replay_bundle, flow=flow).model_dump(mode="json")
            for _ in range(runs)
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


def _ensure_project_record(
    factory: partial[StorageUnitOfWork],
    bundle: ProjectBundle,
    now_us: int,
) -> None:
    ProjectControlService(factory).register(bundle.project_file, revalidate=True)
