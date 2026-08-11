"""Recording 公开工作流：状态查询、草稿审阅、最终 Flow 发布。"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from ..domain.recording import RecordingState, transition_recording_state
from ..domain.verification import Flow
from ..errors import ErrorCode, JiejianError
from ..protocols import (
    FlowDraftReviewCommandV1,
    FlowDraftV1,
    canonical_flow_draft_json_bytes,
)
from ..storage import (
    FlowDraftRevisionRecord,
    RecordingRecord,
    StorageUnitOfWork,
)
from .review import FlowDraftReviewer


class RecordingStatusView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: str = "1"
    recording: RecordingRecord
    draft: FlowDraftV1 | None = None


class RecordingFinalizationView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: str = "1"
    recording: RecordingRecord
    flow: Flow
    flow_path: str


class RecordingWorkflow:
    """不执行浏览器请求，只编排 Recording 的人工审阅和最终化。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        *,
        reviewer: FlowDraftReviewer | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._reviewer = reviewer or FlowDraftReviewer()

    def status(self, recording_id: str) -> RecordingStatusView:
        with self._uow_factory() as work:
            recording = work.recordings.get(recording_id)
            draft_record = work.flow_drafts.latest(recording_id)
            if recording is None:
                raise JiejianError(ErrorCode.RECORD_NOT_FOUND, "录制对象不存在")
            return RecordingStatusView(
                recording=recording,
                draft=draft_record.draft if draft_record is not None else None,
            )

    def review(
        self,
        recording_id: str,
        command: FlowDraftReviewCommandV1,
        *,
        bindings: Mapping[str, Mapping[str, str]] | None = None,
    ) -> RecordingStatusView:
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
            if bindings:
                draft = _confirm_bindings(draft, bindings)
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
            work.commit()
            return RecordingStatusView(recording=recording, draft=draft)

    def finalize(
        self,
        recording_id: str,
        *,
        var_dir: Path,
        now_us: int,
    ) -> RecordingFinalizationView:
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
            flow = self._reviewer.compile(draft_record.draft)
            path = self.flow_path(var_dir, recording)
            encoded = _canonical_flow_bytes(flow)
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
        root = var_dir.resolve() / "projects" / recording.project_id / "recordings"
        path = (root / recording.recording_id / "flow.json").resolve()
        if not path.is_relative_to(root.resolve()):
            raise JiejianError(ErrorCode.RECORD_FLOW_PUBLISH, "最终 Flow 路径越界")
        return path

    @staticmethod
    def load_final_flow(path: Path) -> Flow:
        try:
            return Flow.model_validate_json(path.read_bytes(), strict=True)
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


def _confirm_bindings(
    draft: FlowDraftV1,
    bindings: Mapping[str, Mapping[str, str]],
) -> FlowDraftV1:
    known = {step.id for step in draft.steps}
    if any(step_id not in known for step_id in bindings):
        raise JiejianError(ErrorCode.RECORD_DRAFT_REFERENCE, "绑定步骤引用不存在")
    updated = []
    for step in draft.steps:
        binding = bindings.get(step.id)
        if binding is None:
            updated.append(step)
            continue
        if step.method is None or set(binding) != {
            "alternate_identity_id",
            "resource_id",
            "alternate_resource_id",
        }:
            raise JiejianError(ErrorCode.RECORD_DRAFT_INVALID, "Flow 绑定字段不完整")
        alternate_identity = binding["alternate_identity_id"]
        resource_id = binding["resource_id"]
        alternate_resource_id = binding["alternate_resource_id"]
        if not all(
            isinstance(value, str) and value.strip()
            for value in (alternate_identity, resource_id, alternate_resource_id)
        ):
            raise JiejianError(ErrorCode.RECORD_DRAFT_INVALID, "Flow 绑定值无效")
        updated.append(
            step.model_copy(
                update={
                    "alternate_identity_id": alternate_identity,
                    "resource_id": resource_id,
                    "alternate_resource_id": alternate_resource_id,
                    "bindings_confirmed": True,
                }
            )
        )
    try:
        return FlowDraftV1.model_validate(
            draft.model_copy(update={"steps": tuple(updated)}).model_dump(mode="python")
        )
    except ValueError:
        raise JiejianError(ErrorCode.RECORD_DRAFT_INVALID, "Flow 绑定结果无效") from None
