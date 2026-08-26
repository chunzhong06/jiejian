# 录制 API 路由
# 将创建、审阅和完成请求交给 Recording 应用服务，路由不直接操作浏览器或状态机。

from __future__ import annotations

import json
import time
from uuid import uuid4

from fastapi import APIRouter

from product.backend.workflows.context import ApplicationCore
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.application_understanding import CandidateDecision
from product.backend.core.lifecycle import JobState
from product.backend.workflows.test_identities import TestIdentityStatus
from product.protocols import RecordingBudget, RecordingRunnerRequest, parse_flow_draft_review_command
from product.backend.workflows.recording.submission import SubmitRecording, recording_target_scope
from product.backend.workflows.recording.safety_setup import ConfirmActionSafetySetup
from product.backend.api.envelope import data_response
from product.backend.api.envelope import ApiResponse


def build_recordings_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/projects/{project_id}/recordings",
        response_model=ApiResponse,
        status_code=202,
    )
    async def create_recording(project_id: str, body: RecordingCreateRequest):
        understanding = context.application_understanding.get(project_id)
        action = next(
            (
                item
                for item in understanding.action_candidates
                if item.candidate_id == body.action_candidate_id
                and item.decision is CandidateDecision.CONFIRMED
                and not item.stale
            ),
            None,
        )
        if action is None:
            raise JiejianError(ErrorCode.INPUT_INVALID, "录制动作尚未确认或已经失效")
        if understanding.confirmed_endpoint is None:
            raise JiejianError(ErrorCode.APPLICATION_ENDPOINT_INVALID, "请先确认应用运行地址")
        now_us = time.time_ns() // 1_000
        recording_id = f"rec_{uuid4().hex}"
        expires_at_us = now_us + body.duration_seconds * 1_000_000
        session = context.recording_credentials.prepare(
            project_id=project_id,
            test_identity_id=body.test_identity_id,
            recording_id=recording_id,
            session_ref=f"session_{uuid4().hex}",
            now_us=now_us,
            expires_at_us=expires_at_us,
        )
        request = RecordingRunnerRequest(
            schema_version="1",
            recording_id=recording_id,
            project_id=project_id,
            action_candidate_id=action.candidate_id,
            created_at_us=now_us,
            target_scope=recording_target_scope(understanding.confirmed_endpoint),
            sessions=(session,),
            budget=RecordingBudget(
                max_duration_us=body.duration_seconds * 1_000_000,
                max_contexts=1,
            ),
            headless=False,
            trace_enabled=False,
        )
        try:
            result = context.recording_submission.submit(
                SubmitRecording(
                    request=request,
                    flow_id=f"flow-{action.candidate_id.removeprefix('action_')}",
                    idempotency_key=body.idempotency_key,
                    now_us=now_us,
                    available_at_us=now_us,
                )
            )
        except Exception:
            context.recording_credentials.clear(recording_id)
            raise
        return data_response(
            {
                "job": result.job.model_dump(mode="json"),
                "recording": result.recording.model_dump(mode="json"),
                "action": _action_option(action),
                "test_identity": _identity_option(
                    context.test_identities.get(body.test_identity_id)
                ),
            },
            status_code=202,
        )

    @router.get(
        "/api/projects/{project_id}/recordings/setup", response_model=ApiResponse
    )
    async def recording_setup(project_id: str):
        understanding = context.application_understanding.get(project_id)
        return data_response(
            {
                "project_id": understanding.project_id,
                "action_options": [
                    _action_option(item)
                    for item in understanding.action_candidates
                    if item.decision is CandidateDecision.CONFIRMED and not item.stale
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
        view = context.recording_lifecycle.status(recording_id).model_dump(
            mode="json"
        )
        with context.uow_factory() as work:
            job = work.jobs.get_by_recording(recording_id)
        if job is not None and job.state in {
            JobState.SUCCEEDED,
            JobState.FAILED,
            JobState.CANCELLED,
        }:
            context.recording_credentials.clear(recording_id)
        view["job"] = job.model_dump(mode="json") if job else None
        view.update(_recording_metadata(context, job))
        return data_response(view)

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
            return data_response(
                [
                    {
                        **item.model_dump(mode="json"),
                        "job": (
                            job.model_dump(mode="json")
                            if (job := work.jobs.get_by_recording(item.recording_id))
                            else None
                        ),
                    }
                    for item in work.recordings.list_for_project(project_id)
                ]
            )

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
        with context.uow_factory() as work:
            job = work.jobs.get_by_recording(recording_id)
        data.update(_recording_metadata(context, job))
        return data_response(data)

    @router.get(
        "/api/recordings/{recording_id}/safety-setup",
        response_model=ApiResponse,
    )
    async def get_action_safety_setup(recording_id: str):
        """读取有限候选与已确认事实；该查询不会访问目标应用。"""

        view = context.action_safety_setup.preview(recording_id)
        return data_response(view.model_dump(mode="json"))

    @router.put(
        "/api/recordings/{recording_id}/safety-setup",
        response_model=ApiResponse,
    )
    async def confirm_action_safety_setup(
        recording_id: str,
        body: ActionSafetySetupConfirmRequest,
    ):
        view = context.action_safety_setup.confirm(
            recording_id,
            ConfirmActionSafetySetup.model_validate(
                body.model_dump(exclude={"schema_version"}),
                strict=True,
            ),
        )
        return data_response(view.model_dump(mode="json"))

    return router

# Recording 请求模型。

from typing import Any, Literal

from pydantic import Field

from product.backend.api.envelope import ApiModel


class RecordingCreateRequest(ApiModel):
    schema_version: Literal["1"]
    action_candidate_id: str = Field(pattern=r"^action_[0-9a-f]{32}$")
    test_identity_id: str = Field(pattern=r"^tid_[0-9a-f]{32}$")
    duration_seconds: int = Field(default=60, ge=1, le=3_600)
    idempotency_key: str = Field(min_length=1, max_length=128)


class ReviewRequest(ApiModel):
    schema_version: Literal["1"]
    command: dict[str, Any]


class FinalizeRequest(ApiModel):
    schema_version: Literal["1"]


class ActionSafetySetupConfirmRequest(ApiModel):
    schema_version: Literal["1"]
    resource_candidate_id: str = Field(pattern=r"^trc_[0-9a-f]{32}$")
    logical_name: str = Field(min_length=1, max_length=128)
    resource_type: str = Field(min_length=1, max_length=128)
    owner_test_identity_id: str = Field(pattern=r"^tid_[0-9a-f]{32}$")
    observation_candidate_id: str | None = Field(
        default=None,
        pattern=r"^obc_[0-9a-f]{32}$",
    )
    recovery_candidate_id: str | None = Field(
        default=None,
        pattern=r"^rcc_[0-9a-f]{32}$",
    )
    confirm_recovery_not_required: bool = False
    security_effect_candidate_id: str | None = Field(
        default=None,
        pattern=r"^sfc_[0-9a-f]{32}$",
    )


def _identity_option(identity) -> dict[str, str]:
    """仅投影录制选择所需字段，避免把 secret_ref 带到产品响应。"""

    return {
        "test_identity_id": identity.identity_id,
        "label": identity.label,
        "role_display_name": identity.role_display_name,
    }


def _action_option(action) -> dict[str, str]:
    return {
        "action_candidate_id": action.candidate_id,
        "display_name": action.display_name,
        "risk_hint": action.risk_hint.value,
    }


def _recording_metadata(context: ApplicationCore, job) -> dict[str, object]:
    """从持久请求恢复普通页面所需的非秘密动作与录制身份标签。"""

    if job is None:
        return {}
    request = context.recording_request_store.load(
        job.job_id,
        expected_hash=job.request_hash,
    )
    understanding = context.application_understanding.get(request.project_id)
    action = next(
        (
            item
            for item in understanding.action_candidates
            if item.candidate_id == request.action_candidate_id
        ),
        None,
    )
    test_identity_id = request.sessions[0].test_identity_id
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
                "role_display_name": "已删除",
            }
        ),
    }
