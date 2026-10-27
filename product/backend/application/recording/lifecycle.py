# =============================================================================
# Recording 审阅工作流
#
# 定位
#   CLI/API 与 Recording、FlowDraft revision、最终 Flow 文件之间的应用服务
#
# 职责
#   查询状态｜追加不可变审阅 revision｜明确放弃待审录制｜原子发布已确认 Flow
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
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from product.backend.domain.lifecycle import JobState
from product.backend.domain.recording.models import RecordingPurpose, RecordingState, transition_recording_state
from product.protocols.recording.recording_flow import Flow
from product.backend.domain.errors import ErrorCode, JiejianError
from product.protocols.recording.flow_draft import FlowDraftReviewCommand, FlowDraft, canonical_flow_draft_json_bytes
from product.backend.infrastructure.artifacts.run_packages import attempt_paths_for
from product.backend.infrastructure.recording.control import control_paths_for_attempt, valid_control_marker, write_control_marker
from product.backend.infrastructure.storage import FlowDraftRevisionRecord, RecordingRecord, StorageUnitOfWork
from product.backend.application.recording.flow_compiler import FlowDraftCompiler
from product.backend.application.recording.review import FlowDraftReviewer
from product.backend.infrastructure.recording.flows import recorded_flow_path, read_recorded_flow, publish_recorded_flow, canonical_flow_bytes


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


class RecordingFinalizationView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    recording: RecordingRecord
    flow: Flow | None = None
    flow_path: str | None = None


class RecordingLifecycle:
    """不执行浏览器请求，只编排 Recording 的人工审阅和最终化。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        *,
        var_dir: Path | None = None,
        reviewer: FlowDraftReviewer | None = None,
        compiler: FlowDraftCompiler | None = None,
        bindings=None,
    ) -> None:
        self._uow_factory = uow_factory
        self._var_dir = var_dir.resolve() if var_dir is not None else None
        self._reviewer = reviewer or FlowDraftReviewer()
        self._compiler = compiler or FlowDraftCompiler()
        self._bindings = bindings

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

    def discard_review(self, recording_id: str, *, now_us: int) -> RecordingStatusView:
        """仅放弃已结束执行的待审录制；重复取消幂等，历史与技术资产保持不变。"""

        # 核查与转换共用现有 UoW；不把活动 Job 的取消或资源清理带进审阅事务。
        with self._uow_factory() as work:
            recording = work.recordings.get(recording_id)
            if recording is None:
                raise JiejianError(ErrorCode.RECORD_NOT_FOUND, "录制对象不存在")
            job = work.jobs.get_by_recording(recording_id)
            draft_record = work.flow_drafts.latest(recording_id)
            if recording.state is not RecordingState.CANCELLED:
                if (recording.state is not RecordingState.PENDING_REVIEW
                        or job is None or job.recording_id != recording_id or job.run_id is not None
                        or job.state not in {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED}):
                    raise JiejianError(ErrorCode.RECORD_REVIEW_STATE, "只有执行已结束的待审录制可以放弃")
                cancelled = transition_recording_state(
                    recording.to_domain(), RecordingState.CANCELLED, operator="RECORDING_SERVICE",
                    reason_code="CANCEL_REQUESTED", occurred_at_us=now_us,
                )
                recording = RecordingRecord.from_domain(
                    cancelled, flow_id=recording.flow_id, browser_events=recording.browser_events,
                )
                work.recordings.replace(recording)
                work.commit()
            return RecordingStatusView(
                recording=recording, draft=draft_record.draft if draft_record is not None else None,
                capture_phase=self._capture_phase(recording, job),
            )

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

    def _refresh_resources(self, work, recording, draft, command):
        """复用原事件补充对象候选；保存新修订，不改写历史或重发创建请求。"""
        from product.backend.application.recording.processing import FlowDraftProcessor
        if command.expected_revision != draft.revision:
            raise JiejianError(ErrorCode.RECORD_REVIEW_STATE, "录制已被更新，请重新读取后再识别对象")
        if self._var_dir is None:
            raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "录制来源不可用")
        action, _, understanding = require_persisted_recording_source(work, recording, self._var_dir)
        binding = work.business_boundaries.action_binding(action.action_id, action.revision)
        templates = tuple(item.canonical_key for item in understanding.action_candidates
            if binding is not None and item.candidate_id in binding.action_candidate_ids and not item.stale)
        fresh = FlowDraftProcessor().build(recording_id=draft.recording_id, flow_id=draft.flow_id,
            business_action_id=draft.business_action_id, action_revision=draft.action_revision,
            subject_test_identity_id=draft.subject_test_identity_id, resource_owner_test_identity_id=draft.resource_owner_test_identity_id,
            purpose=draft.purpose, parent_recording_id=draft.parent_recording_id, effect_id=draft.effect_id,
            events=recording.browser_events, action_path_templates=templates,
            allow_created_resources=recording.purpose is RecordingPurpose.TARGET and action.state_changing
                and any(effect.effect_kind.value == "OBJECT_CREATION" for effect in action.effect_catalog))
        replacement = {step.id: step for step in fresh.steps}
        if any(step.id not in replacement or replacement[step.id].request_id != step.request_id for step in draft.steps):
            raise JiejianError(ErrorCode.RECORD_DRAFT_REFERENCE, "原步骤与事件无法对应，已保留原审阅")
        payload = draft.model_dump(mode="json")
        payload.update(schema_version=fresh.schema_version, revision=draft.revision + 1)
        for step in payload["steps"]:
            step["resource_candidates"] = [item.model_dump(mode="json") for item in replacement[step["id"]].resource_candidates]
        chosen = replacement.get(draft.target_step_id)
        if chosen is None or not any(item.candidate_id == draft.resource_candidate_id for item in chosen.resource_candidates):
            payload["resource_candidate_id"] = None
        return FlowDraft.model_validate_json(json.dumps(payload), strict=True)

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
            expected = getattr(command, "expected_revision", None)
            if expected is not None and expected != draft_record.draft.revision:
                raise JiejianError(ErrorCode.RECORD_REVIEW_STATE, "录制已更新，请重新读取当前对象再确认")
            from product.protocols.recording.flow_draft import RefreshFlowDraftResources
            draft = (self._refresh_resources(work, recording, draft_record.draft, command)
                if isinstance(command, RefreshFlowDraftResources) else self._reviewer.apply(draft_record.draft, command))
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
        """原子接受录制和技术绑定；目标录制发布 Flow，补录只形成明确目的的模板。"""

        from product.backend.application.preparation.bindings.service import PreparationBindingService
        from product.backend.application.recording.source import require_persisted_recording_source

        bindings = self._bindings or PreparationBindingService(self._uow_factory, var_dir)

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
            path = recorded_flow_path(var_dir, recording) if recording.purpose is RecordingPurpose.TARGET else None
            if recording.state is RecordingState.COMPLETED:
                # 重复接受不能把当前技术绑定回退到较早的演示。
                return RecordingFinalizationView(
                    recording=recording, flow=read_recorded_flow(path) if path is not None else None,
                    flow_path=str(path) if path is not None else None,
                )
            require_persisted_recording_source(work, recording, var_dir)
            flow = self._compiler.compile(draft) if path is not None else None
            if flow is not None:
                # 文件先原子发布；数据库失败时保留不可变文件，重试按同一内容验证。
                publish_recorded_flow(path, canonical_flow_bytes(flow))
            completed = transition_recording_state(
                recording.to_domain(), RecordingState.COMPLETED, operator="RECORDING_SERVICE",
                occurred_at_us=now_us, reason_code="REVIEW_COMPLETED",
            )
            recording = RecordingRecord.from_domain(completed, flow_id=recording.flow_id,
                                                   browser_events=recording.browser_events)
            work.recordings.replace(recording)
            try:
                if work.preparation_recovery.candidate_recording(recording_id):
                    # 候选审阅仍核对完整来源，但采用须经过材料预览与确认；跨进程自动最终化也遵守此标记。
                    bindings.build_recording_bindings(work, recording, draft_record, flow=flow, now_us=now_us)
                else:
                    bindings.accept_recording(work, recording, draft_record, flow=flow, now_us=now_us)
            except ValidationError:
                raise JiejianError(ErrorCode.RECORD_DRAFT_UNCONFIRMED, "录制中的资源或请求不能形成受限技术绑定") from None
            work.commit()
            return RecordingFinalizationView(
                recording=recording,
                flow=flow,
                flow_path=str(path) if path is not None else None,
            )

    def finalize_if_unambiguous(self, recording_id: str, *, now_us: int):
        """仅在结果消费后的显式写路径自动接受唯一事实，歧义与陈旧来源留待处理。"""
        if self._var_dir is None:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "录制最终化运行目录未装配")
        try:
            return self.finalize(recording_id, var_dir=self._var_dir, now_us=now_us)
        except JiejianError as error:
            if error.code in {
                ErrorCode.RECORD_DRAFT_UNCONFIRMED, ErrorCode.RECORD_DRAFT_REFERENCE,
                ErrorCode.RECORD_DRAFT_COMPILE, ErrorCode.RECORD_STATE_PRECONDITION,
            }:
                return None
            raise





