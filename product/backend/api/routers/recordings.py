# Recording API Router
# 将创建、审阅和完成请求交给 Recording 应用服务，路由不直接操作浏览器或状态机。

from __future__ import annotations

import json
import time
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter

from product.backend.workflows.context import ApplicationCore
from product.backend.core.recording import RecordingState
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import RecordingBudget, RecordingRunnerRequest, RecordingSessionRef, parse_flow_draft_review_command
from product.backend.workflows.recording.submission import SubmitRecording
from product.backend.api.envelope import data_response
from product.backend.api.envelope import ApiResponse
from product.protocols import parse_execution_profile


def build_recordings_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/projects/{project_id}/recordings",
        response_model=ApiResponse,
        status_code=202,
    )
    async def create_recording(project_id: str, body: RecordingCreateRequest):
        try:
            profile = parse_execution_profile(
                Path(body.profile_path).resolve().read_bytes()
            )
        except (OSError, ValueError, JiejianError):
            raise JiejianError(ErrorCode.EXECUTION_PROFILE_INVALID, "录制必须使用有效的当前 ExecutionProfile") from None
        if profile.project_id != project_id:
            raise JiejianError(ErrorCode.EXECUTION_PROFILE_PROJECT_CONFLICT, "录制 Profile 与项目不匹配")
        selected = (
            tuple(body.identities)
            if body.identities
            else tuple(item.id for item in profile.identities)
        )
        known = {item.id for item in profile.identities}
        if (
            not selected
            or len(set(selected)) != len(selected)
            or any(item not in known for item in selected)
        ):
            raise JiejianError(ErrorCode.INPUT_INVALID, "录制身份选择无效")
        now_us = time.time_ns() // 1_000
        request = RecordingRunnerRequest(
            schema_version="1",
            recording_id=f"rec_{uuid4().hex}",
            project_id=project_id,
            created_at_us=now_us,
            target_scope=profile.target.scope,
            sessions=tuple(
                RecordingSessionRef(
                    schema_version="1",
                    identity_id=item,
                    session_ref=f"session_{uuid4().hex}",
                    expires_at_us=now_us + body.duration_seconds * 1_000_000,
                )
                for item in selected
            ),
            budget=RecordingBudget(
                schema_version="1",
                max_duration_us=body.duration_seconds * 1_000_000,
                max_contexts=len(selected),
            ),
            headless=body.headless,
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
            },
            status_code=202,
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
    async def finalize_recording(recording_id: str):
        view = context.recording_lifecycle.finalize(
            recording_id,
            var_dir=context.var_dir,
            now_us=time.time_ns() // 1_000,
        )
        return data_response(view.model_dump(mode="json"))

    return router

# Recording 请求模型。

from typing import Any

from pydantic import Field

from product.backend.api.envelope import ApiModel


class RecordingCreateRequest(ApiModel):
    profile_path: str = Field(min_length=1, max_length=2048)
    # JSON arrays decode to list; tuple conversion belongs at the application boundary.
    identities: list[str] | None = None
    duration_seconds: int = Field(default=60, ge=1, le=3_600)
    headless: bool = True
    idempotency_key: str = Field(min_length=1, max_length=128)


class ReviewRequest(ApiModel):
    command: dict[str, Any]
    bindings: dict[str, dict[str, str]] | None = None
