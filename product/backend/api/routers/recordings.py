# 录制 API 路由
# 将创建、审阅和完成请求交给 Recording 应用服务，路由不直接操作浏览器或状态机。

from __future__ import annotations

import json
import time
from uuid import uuid4

from fastapi import APIRouter

from product.backend.workflows.context import ApplicationCore
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import RecordingBudget, RecordingRunnerRequest, RecordingSessionRef, parse_flow_draft_review_command
from product.backend.workflows.recording.submission import SubmitRecording
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
        profile = context.execution.current(body.profile_id, project_id=project_id)
        selected = next(
            (
                item
                for item in profile.identities
                if item.identity_id == body.identity_id
            ),
            None,
        )
        if selected is None:
            raise JiejianError(ErrorCode.INPUT_INVALID, "录制身份选择无效")
        now_us = time.time_ns() // 1_000
        request = RecordingRunnerRequest(
            schema_version="1",
            recording_id=f"rec_{uuid4().hex}",
            project_id=project_id,
            created_at_us=now_us,
            target_scope=profile.target.scope,
            sessions=(
                RecordingSessionRef(
                    schema_version="1",
                    identity_id=selected.identity_id,
                    session_ref=f"session_{uuid4().hex}",
                    expires_at_us=now_us + body.duration_seconds * 1_000_000,
                ),
            ),
            budget=RecordingBudget(
                schema_version="1",
                max_duration_us=body.duration_seconds * 1_000_000,
                max_contexts=1,
            ),
            headless=False,
            trace_enabled=False,
        )
        result = context.recording_submission.submit(
            SubmitRecording(
                schema_version="1",
                request=request,
                flow_id=profile.profile_id,
                idempotency_key=body.idempotency_key,
                now_us=now_us,
                available_at_us=now_us,
            )
        )
        return data_response(
            {
                "job": result.job.model_dump(mode="json"),
                "recording": result.recording.model_dump(mode="json"),
                "identity_options": _identity_options(profile),
            },
            status_code=202,
        )

    @router.get(
        "/api/projects/{project_id}/recordings/setup", response_model=ApiResponse
    )
    async def recording_setup(project_id: str, profile_id: str):
        profile = context.execution.current(profile_id, project_id=project_id)
        return data_response(
            {
                "profile_id": profile.profile_id,
                "project_id": profile.project_id,
                "identity_options": _identity_options(profile),
            }
        )

    @router.get("/api/recordings/{recording_id}", response_model=ApiResponse)
    async def get_recording(recording_id: str):
        view = context.recording_lifecycle.status(recording_id).model_dump(
            mode="json"
        )
        with context.uow_factory() as work:
            job = work.jobs.get_by_recording(recording_id)
        view["job"] = job.model_dump(mode="json") if job else None
        return data_response(view)

    @router.post("/api/recordings/{recording_id}/capture/start", response_model=ApiResponse)
    @router.post("/api/recordings/{recording_id}/start", response_model=ApiResponse)
    async def start_recording(recording_id: str):
        view = context.recording_lifecycle.start_capture(recording_id)
        return data_response(view.model_dump(mode="json"))

    @router.post("/api/recordings/{recording_id}/capture/stop", response_model=ApiResponse)
    @router.post("/api/recordings/{recording_id}/stop", response_model=ApiResponse)
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
        view = context.recording_lifecycle.review(
            recording_id, command, bindings=body.bindings
        )
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
            bindings=body.bindings if body is not None else None,
        )
        return data_response(view.model_dump(mode="json"))

    return router

# Recording 请求模型。

from typing import Any

from pydantic import Field

from product.backend.api.envelope import ApiModel


class RecordingCreateRequest(ApiModel):
    profile_id: str = Field(min_length=1, max_length=64)
    identity_id: str = Field(min_length=1, max_length=64)
    duration_seconds: int = Field(default=60, ge=1, le=3_600)
    idempotency_key: str = Field(min_length=1, max_length=128)


class ReviewRequest(ApiModel):
    command: dict[str, Any]
    bindings: dict[str, dict[str, str]] | None = None


class FinalizeRequest(ApiModel):
    bindings: dict[str, dict[str, str]] | None = None


def _identity_options(profile) -> list[dict[str, str]]:
    """仅投影身份 ID 与可读角色，避免把 secret_ref 带到产品响应。"""

    return [
        {"identity_id": identity.identity_id, "role": identity.role}
        for identity in profile.identities
    ]
