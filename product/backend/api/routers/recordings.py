# 录制 API 路由
# 将创建、审阅和完成请求交给 Recording 应用服务，路由不直接操作浏览器或状态机。

from __future__ import annotations

import json
import time
from fastapi import APIRouter

from product.backend.composition import ApplicationCore
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.business_boundary import ImplementationBindingStatus
from product.backend.core.lifecycle import JobState
from product.backend.core.recording import RecordingPurpose, RecordingState
from product.backend.workflows.test_identities import TestIdentityStatus
from product.protocols import parse_flow_draft_review_command
from product.backend.api.envelope import data_response
from product.backend.api.envelope import ApiResponse
from product.backend.infra.runtime.jobs.models import RequestCancellation


def build_recordings_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.post("/api/jobs/{job_id}/cancel", response_model=ApiResponse)
    async def cancel_recording_job(job_id: str):
        with context.uow_factory() as work:
            job = work.jobs.get(job_id)
        if job is None:
            raise JiejianError(ErrorCode.JOB_NOT_FOUND, "任务不存在")
        if job.recording_id is None or job.run_id is not None:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "当前不提供正式权限检查")
        result = context.job_queue.request_cancellation(RequestCancellation(job_id=job_id, now_us=time.time_ns() // 1_000))
        return data_response(result.model_dump(mode="json"))

    @router.post(
        "/api/projects/{project_id}/recordings",
        response_model=ApiResponse,
        status_code=202,
    )
    async def create_recording(project_id: str, body: RecordingCreateRequest):
        started = context.project_recordings.submit(
            project_id,
            business_action_id=body.business_action_id,
            action_revision=body.action_revision,
            test_identity_id=body.test_identity_id,
            duration_seconds=body.duration_seconds,
            idempotency_key=body.idempotency_key,
            purpose=RecordingPurpose(body.purpose),
            parent_recording_id=body.parent_recording_id,
            effect_id=body.effect_id,
            headless=False,
        )
        return data_response(
            {
                "job": started.result.job.model_dump(mode="json"),
                "recording": started.result.recording.model_dump(mode="json"),
                "action": _action_option(started.action),
                "test_identity": _identity_option(started.test_identity),
            },
            status_code=202,
        )

    @router.get(
        "/api/projects/{project_id}/recordings/setup", response_model=ApiResponse
    )
    async def recording_setup(project_id: str):
        boundary = context.business_boundaries.view(project_id)
        current_actions = {
            (item.action_id, item.action_revision)
            for item in boundary.action_bindings
            if item.status is ImplementationBindingStatus.CURRENT
        }
        return data_response(
            {
                "project_id": boundary.project_id,
                "action_options": [
                    _action_option(item)
                    for item in boundary.actions
                    if (item.action_id, item.revision) in current_actions
                ],
                "test_identity_options": [
                    _identity_option(item)
                    for item in context.test_identities.list(project_id)
                    if item.status is TestIdentityStatus.PREPARED
                ],
            }
        )

    @router.get("/api/recordings/{recording_id}", response_model=ApiResponse)
    async def get_recording(recording_id: str):
        status = context.recording_lifecycle.status(recording_id)
        view = status.model_dump(mode="json")
        with context.uow_factory() as work:
            job = work.jobs.get_by_recording(recording_id)
        if job is not None and job.state in {
            JobState.SUCCEEDED,
            JobState.FAILED,
            JobState.CANCELLED,
        }:
            context.recording_credentials.clear(recording_id)
        view["job"] = job.model_dump(mode="json") if job else None
        view["supplement_choices"] = []
        if (status.recording.state is RecordingState.PENDING_REVIEW
                and status.recording.purpose in {RecordingPurpose.OBSERVATION, RecordingPurpose.RECOVERY}
                and status.draft is not None):
            # 候选合法性由准备服务判断，控制面只暴露现有步骤的业务标签。
            steps = {step.id: step for step in status.draft.steps}
            purpose_label = "结果证明" if status.recording.purpose is RecordingPurpose.OBSERVATION else "恢复方式"
            for ordinal, candidate in enumerate(context.preparation_bindings.candidates(recording_id), 1):
                step = steps.get(candidate.step_id)
                if step is None:
                    raise JiejianError(ErrorCode.RECORD_DRAFT_REFERENCE, "补录候选与当前草稿不一致")
                label = " ".join(step.name.split())[:160] or f"{purpose_label} {ordinal}"
                view["supplement_choices"].append({"step_id": step.id, "label": label})
        view.update(_recording_metadata(context, status.recording))
        return data_response(view)

    @router.post("/api/recordings/{recording_id}/discard", response_model=ApiResponse)
    async def discard_recording(recording_id: str, body: FinalizeRequest):
        view = context.recording_lifecycle.discard_review(recording_id, now_us=time.time_ns() // 1_000)
        return data_response(view.model_dump(mode="json"))

    @router.post("/api/recordings/{recording_id}/capture/start", response_model=ApiResponse)
    async def start_recording(recording_id: str):
        view = context.recording_lifecycle.start_capture(recording_id)
        return data_response(view.model_dump(mode="json"))

    @router.post("/api/recordings/{recording_id}/capture/stop", response_model=ApiResponse)
    async def stop_recording(recording_id: str):
        view = context.recording_lifecycle.stop_capture(recording_id)
        return data_response(view.model_dump(mode="json"))

    @router.get(
        "/api/projects/{project_id}/recordings", response_model=ApiResponse
    )
    async def list_recordings(project_id: str):
        context.projects.get(project_id)
        with context.uow_factory() as work:
            recordings = work.recordings.list_for_project(project_id)
        # 列表只返回定位和生命周期摘要，浏览器事件不是页面列表的数据来源。
        fields = {
            "recording_id", "project_id", "flow_id", "business_action_id", "action_revision",
            "test_identity_id", "state", "purpose", "parent_recording_id", "effect_id",
            "created_at_us", "updated_at_us",
        }
        return data_response([item.model_dump(mode="json", include=fields) for item in recordings])

    @router.post(
        "/api/recordings/{recording_id}/review", response_model=ApiResponse
    )
    async def review_recording(recording_id: str, body: ReviewRequest):
        command = parse_flow_draft_review_command(
            json.dumps(body.command, ensure_ascii=False).encode("utf-8")
        )
        view = context.recording_lifecycle.review(recording_id, command)
        return data_response(view.model_dump(mode="json"))

    @router.post(
        "/api/recordings/{recording_id}/finalize", response_model=ApiResponse
    )
    async def finalize_recording(
        recording_id: str,
        body: FinalizeRequest | None = None,
    ):
        view = context.recording_lifecycle.finalize(
            recording_id,
            var_dir=context.var_dir,
            now_us=time.time_ns() // 1_000,
        )
        data = view.model_dump(mode="json")
        data.update(_recording_metadata(context, view.recording))
        return data_response(data)

    return router

# Recording 请求模型。

from typing import Any, Literal

from pydantic import Field, model_validator

from product.backend.api.envelope import ApiModel


class RecordingCreateRequest(ApiModel):
    schema_version: Literal["2"]
    business_action_id: str = Field(pattern=r"^bac_[0-9a-f]{32}$")
    action_revision: int = Field(ge=1)
    test_identity_id: str = Field(pattern=r"^tid_[0-9a-f]{32}$")
    duration_seconds: int = Field(default=60, ge=1, le=3_600)
    idempotency_key: str = Field(min_length=1, max_length=128)
    purpose: Literal["TARGET", "OBSERVATION", "RECOVERY"] = "TARGET"
    parent_recording_id: str | None = Field(
        default=None,
        pattern=r"^rec_[0-9a-f]{32}$",
    )
    effect_id: str | None = Field(default=None, pattern=r"^bef_[0-9a-f]{32}$")

    @model_validator(mode="after")
    def validate_purpose(self):
        if (self.purpose == "TARGET") != (self.parent_recording_id is None):
            raise ValueError("补录必须关联原业务录制")
        if (self.purpose == "OBSERVATION") != (self.effect_id is not None):
            raise ValueError("结果证明必须指定已确认的业务效果")
        return self


class ReviewRequest(ApiModel):
    schema_version: Literal["1"]
    command: dict[str, Any]


class FinalizeRequest(ApiModel):
    schema_version: Literal["1"]


def _identity_option(identity) -> dict[str, str]:
    """仅投影录制选择所需字段，避免把 secret_ref 带到产品响应。"""

    return {
        "test_identity_id": identity.identity_id,
        "label": identity.label,
        "actor_display_name": identity.actor_display_name,
    }


def _action_option(action) -> dict[str, object]:
    return {
        "business_action_id": action.action_id,
        "action_revision": action.revision,
        "display_name": action.display_name,
    }


def _recording_metadata(context: ApplicationCore, recording) -> dict[str, object]:
    """按录制冻结的业务 revision 读取展示标签，不读取秘密或借用当前候选身份。"""

    with context.uow_factory() as work:
        action = work.business_boundaries.action_revision(recording.business_action_id, recording.action_revision)
    test_identity_id = recording.test_identity_id
    try:
        identity = context.test_identities.get(test_identity_id)
    except JiejianError as exc:
        if exc.code != ErrorCode.TEST_IDENTITY_NOT_FOUND.value:
            raise
        identity = None
    return {
        "action": _action_option(action) if action is not None else None,
        "test_identity": (
            _identity_option(identity)
            if identity is not None
            else {
                "test_identity_id": test_identity_id,
                "label": "已删除的测试账号",
                "actor_display_name": "已删除",
            }
        ),
    }
