# =============================================================================
# Recording 审阅工作流
#
# 定位
#   CLI/API 与 Recording、FlowDraft revision、最终 Flow 文件之间的应用服务
#
# 职责
#   查询状态｜追加不可变审阅 revision｜原子发布已确认 Flow
#
# 边界
#   不执行浏览器请求；仅在审阅完成且绑定有效后发布最终 Flow。
#
# 调用链
#   CLI / API → RecordingLifecycle → reviewer + compiler / Storage / final flow file
# =============================================================================

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from product.backend.core.lifecycle import JobState
from product.backend.core.recording import RecordingState, transition_recording_state
from product.protocols.recording_flow import Flow
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import FlowDraftReviewCommand, FlowDraft, canonical_flow_draft_json_bytes
from product.backend.infra.artifacts.run_packages import attempt_paths_for
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.recording.control import control_paths_for_attempt, valid_control_marker, write_control_marker
from product.backend.infra.storage import FlowDraftRevisionRecord, RecordingRecord, StorageUnitOfWork
from product.backend.workflows.recording.flow_compiler import FlowDraftCompiler
from product.backend.workflows.recording.review import FlowDraftReviewer


class RecordingStatusView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    recording: RecordingRecord
    draft: FlowDraft | None = None
    capture_phase: Literal[
        "PREPARING_BROWSER",
        "AWAITING_CAPTURE",
        "CAPTURE_STARTING",
        "CAPTURING",
        "STOPPING",
        "FINISHED",
    ]


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


class RecordingFinalizationView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    recording: RecordingRecord
    flow: Flow
    flow_path: str


class RecordingLifecycle:
    """不执行浏览器请求，只编排 Recording 的人工审阅和最终化。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        *,
        var_dir: Path | None = None,
        reviewer: FlowDraftReviewer | None = None,
        compiler: FlowDraftCompiler | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._var_dir = var_dir.resolve() if var_dir is not None else None
        self._reviewer = reviewer or FlowDraftReviewer()
        self._compiler = compiler or FlowDraftCompiler()

    def status(self, recording_id: str) -> RecordingStatusView:
        with self._uow_factory() as work:
            recording = work.recordings.get(recording_id)
            draft_record = work.flow_drafts.latest(recording_id)
            job = work.jobs.get_by_recording(recording_id)
            if recording is None:
                raise JiejianError(ErrorCode.RECORD_NOT_FOUND, "录制对象不存在")
            return RecordingStatusView(
                recording=recording,
                draft=draft_record.draft if draft_record is not None else None,
                capture_phase=self._capture_phase(recording, job),
            )

    def start_capture(self, recording_id: str) -> RecordingStatusView:
        """为当前 fenced attempt 原子写入开始标记，不直接启动浏览器。"""

        return self._write_capture_marker(recording_id, "start")

    def stop_capture(self, recording_id: str) -> RecordingStatusView:
        """为当前 fenced attempt 原子写入停止标记，保留已采集事件。"""

        return self._write_capture_marker(recording_id, "stop")

    def _write_capture_marker(
        self,
        recording_id: str,
        action: Literal["start", "stop"],
    ) -> RecordingStatusView:
        if self._var_dir is None:
            raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "录制控制面尚未完成装配")
        with self._uow_factory() as work:
            recording = work.recordings.get(recording_id)
            job = work.jobs.get_by_recording(recording_id)
            if recording is None:
                raise JiejianError(ErrorCode.RECORD_NOT_FOUND, "录制对象不存在")
            if job is None or job.recording_id != recording_id:
                raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "录制任务尚未建立")
            if job.state is not JobState.RUNNING or job.attempt < 1:
                raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "录制当前不在可控 attempt")
            paths = attempt_paths_for(self._var_dir, job)
            control = control_paths_for_attempt(paths.attempt_dir)
            if action == "start":
                if recording.state is not RecordingState.STARTING:
                    raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "录制当前不在等待开始阶段")
                if not valid_control_marker(control.ready_path):
                    raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "浏览器尚未准备完成")
                if control.start_path.exists() or control.started_path.exists() or control.stop_path.exists():
                    raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "录制开始动作已处理")
                write_control_marker(control.start_path, attempt_dir=control.attempt_dir)
            else:
                if recording.state is not RecordingState.STARTING and recording.state is not RecordingState.RECORDING:
                    raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "录制当前不在采集阶段")
                if not valid_control_marker(control.started_path):
                    raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "录制尚未开始采集")
                if control.stop_path.exists():
                    raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "录制停止动作已处理")
                write_control_marker(control.stop_path, attempt_dir=control.attempt_dir)
        return self.status(recording_id)

    def _capture_phase(self, recording: RecordingRecord, job) -> str:
        if recording.state in {
            RecordingState.PROCESSING,
            RecordingState.PENDING_REVIEW,
            RecordingState.COMPLETED,
            RecordingState.FAILED,
            RecordingState.CANCELLED,
            RecordingState.SAFETY_STOPPED,
        }:
            return "FINISHED"
        if (
            self._var_dir is None
            or job is None
            or job.state is not JobState.RUNNING
            or job.attempt < 1
        ):
            return "PREPARING_BROWSER"
        try:
            control = control_paths_for_attempt(attempt_paths_for(self._var_dir, job).attempt_dir)
        except JiejianError:
            return "PREPARING_BROWSER"
        if valid_control_marker(control.stop_path):
            return "STOPPING"
        if valid_control_marker(control.started_path):
            return "CAPTURING"
        if valid_control_marker(control.start_path):
            return "CAPTURE_STARTING"
        if valid_control_marker(control.ready_path):
            return "AWAITING_CAPTURE"
        return "PREPARING_BROWSER"

    def review(
        self,
        recording_id: str,
        command: FlowDraftReviewCommand,
    ) -> RecordingStatusView:
        """追加一个审阅 revision；旧 FlowDraft 与已发布 Flow 均保持不可变。"""

        with self._uow_factory() as work:
            recording = work.recordings.get(recording_id)
            draft_record = work.flow_drafts.latest(recording_id)
            if recording is None:
                raise JiejianError(ErrorCode.RECORD_NOT_FOUND, "录制对象不存在")
            if recording.state is not RecordingState.PENDING_REVIEW:
                raise JiejianError(
                    ErrorCode.RECORD_REVIEW_STATE,
                    "录制当前状态不允许审阅",
                )
            if draft_record is None:
                raise JiejianError(ErrorCode.RECORD_DRAFT_INVALID, "录制缺少 Flow 草稿")
            draft = self._reviewer.apply(draft_record.draft, command)
            encoded = canonical_flow_draft_json_bytes(draft)
            work.flow_drafts.add(
                FlowDraftRevisionRecord(
                    recording_id=draft.recording_id,
                    revision=draft.revision,
                    flow_id=draft.flow_id,
                    draft=draft,
                    draft_sha256=hashlib.sha256(encoded).hexdigest(),
                    created_at_us=draft_record.created_at_us,
                )
            )
            job = work.jobs.get_by_recording(recording_id)
            work.commit()
            return RecordingStatusView(
                recording=recording,
                draft=draft,
                capture_phase=self._capture_phase(recording, job),
            )

    def finalize(
        self,
        recording_id: str,
        *,
        var_dir: Path,
        now_us: int,
    ) -> RecordingFinalizationView:
        """编译已明确确认的最新 revision，并在状态提交前原子发布 Flow。"""

        # --- 阶段：读取并编译明确记录的最新草稿 revision ---
        with self._uow_factory() as work:
            recording = work.recordings.get(recording_id)
            draft_record = work.flow_drafts.latest(recording_id)
            if recording is None:
                raise JiejianError(ErrorCode.RECORD_NOT_FOUND, "录制对象不存在")
            if draft_record is None:
                raise JiejianError(ErrorCode.RECORD_DRAFT_INVALID, "录制缺少 Flow 草稿")
            if recording.state not in {
                RecordingState.PENDING_REVIEW,
                RecordingState.COMPLETED,
            }:
                raise JiejianError(
                    ErrorCode.RECORD_REVIEW_STATE,
                    "录制当前状态不允许最终化",
                )
            draft = draft_record.draft
            flow = self._compiler.compile(draft)
            path = self.flow_path(var_dir, recording)
            encoded = _canonical_flow_bytes(flow)
            # --- 阶段：先原子发布文件，再提交数据库完成态 ---
            self._publish_flow(path, encoded)
            if recording.state is RecordingState.PENDING_REVIEW:
                completed = transition_recording_state(
                    recording.to_domain(),
                    RecordingState.COMPLETED,
                    operator="CLI_REVIEW",
                    occurred_at_us=now_us,
                    reason_code="REVIEW_COMPLETED",
                )
                recording = RecordingRecord.from_domain(
                    completed,
                    flow_id=recording.flow_id,
                    browser_events=recording.browser_events,
                )
                work.recordings.replace(recording)
                work.commit()
            return RecordingFinalizationView(
                recording=recording,
                flow=flow,
                flow_path=str(path),
            )

    @staticmethod
    def flow_path(var_dir: Path, recording: RecordingRecord) -> Path:
        root = RuntimePaths(var_dir).projects / recording.project_id / "recordings"
        path = (root / recording.recording_id / "flow.json").resolve()
        if not path.is_relative_to(root.resolve()):
            raise JiejianError(ErrorCode.RECORD_FLOW_PUBLISH, "最终 Flow 路径越界")
        return path

    @staticmethod
    def load_final_flow(path: Path) -> Flow:
        try:
            raw = path.read_bytes()
            parsed = json.loads(raw, object_pairs_hook=_unique_json_object)
            if not isinstance(parsed, dict) or parsed.get("schema_version") != "1":
                raise ValueError("unsupported flow schema version")
            return Flow.model_validate_json(raw, strict=True)
        except (OSError, ValueError):
            raise JiejianError(
                ErrorCode.RECORD_FLOW_PUBLISH,
                "最终 Flow 不可读取",
            ) from None

    @staticmethod
    def _publish_flow(path: Path, encoded: bytes) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                if path.read_bytes() != encoded:
                    raise JiejianError(
                        ErrorCode.RECORD_FLOW_PUBLISH,
                        "最终 Flow 已存在且内容冲突",
                    )
                return
            temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{uuid4().hex}")
            with temporary.open("xb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except JiejianError:
            raise
        except OSError:
            raise JiejianError(
                ErrorCode.RECORD_FLOW_PUBLISH,
                "最终 Flow 发布失败",
            ) from None
        finally:
            if "temporary" in locals():
                temporary.unlink(missing_ok=True)


def _canonical_flow_bytes(flow: Flow) -> bytes:
    try:
        return json.dumps(
            flow.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise JiejianError(ErrorCode.RECORD_FLOW_PUBLISH, "最终 Flow 无法序列化") from None
