# =============================================================================
# Recording API Router
#
# 定位
#   Recording 创建、审阅和完成动作的 HTTP 编排边界
#
# 职责
#   提交录制作业｜应用 FlowDraft 审阅命令｜读取一致的 Recording 状态
#
# 调用链
#   FastAPI → recordings router → RecordingApplicationService / RecordingWorkflow
# =============================================================================

from __future__ import annotations

import json
import time
from uuid import uuid4

from fastapi import APIRouter

from ...application.context import ApplicationContext
from ...recording.models import RecordingState
from ...errors import ErrorCode, JiejianError
from ...protocols import (
    RecordingBudgetV1,
    RecordingRunnerRequestV1,
    RecordingSessionRefV1,
    parse_flow_draft_review_command,
)
from ...recording.application import RecordingApplicationService, SubmitRecordingV1
from ...recording.request_store import RecordingRequestStore
from ...recording.workflow import RecordingWorkflow
from ..responses import data_response
from ..schemas.common import ApiResponse
from ..schemas.recordings import RecordingCreateRequest, ReviewRequest


def build_recordings_router(context: ApplicationContext) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/v1/projects/{project_id}/recordings",
        response_model=ApiResponse,
        status_code=202,
    )
    async def create_recording(project_id: str, body: RecordingCreateRequest):
        record, bundle = context.projects.current_bundle(project_id)
        selected = (
            tuple(body.identities)
            if body.identities
            else tuple(item.id for item in bundle.project.identities)
        )
        known = {item.id for item in bundle.project.identities}
        if (
            not selected
            or len(set(selected)) != len(selected)
            or any(item not in known for item in selected)
        ):
            raise JiejianError(ErrorCode.INPUT_INVALID, "录制身份选择无效")
        now_us = time.time_ns() // 1_000
        request = RecordingRunnerRequestV1(
            schema_version="1",
            recording_id=f"rec_{uuid4().hex}",
            project_id=project_id,
            created_at_us=now_us,
            target_scope=bundle.project.target,
            sessions=tuple(
                RecordingSessionRefV1(
                    schema_version="1",
                    identity_id=item,
                    session_ref=f"session_{uuid4().hex}",
                    expires_at_us=now_us + body.duration_seconds * 1_000_000,
                )
                for item in selected
            ),
            budget=RecordingBudgetV1(
                schema_version="1",
                max_duration_us=body.duration_seconds * 1_000_000,
                max_contexts=len(selected),
            ),
            headless=body.headless,
            trace_enabled=False,
        )
        result = RecordingApplicationService(
            context.uow_factory, RecordingRequestStore(context.var_dir)
        ).submit(
            SubmitRecordingV1(
                schema_version="1",
                request=request,
                flow_id=bundle.flow.id,
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

    @router.get("/api/v1/recordings/{recording_id}", response_model=ApiResponse)
    async def get_recording(recording_id: str):
        view = RecordingWorkflow(context.uow_factory).status(recording_id).model_dump(
            mode="json"
        )
        with context.uow_factory() as work:
            job = work.jobs.get_by_recording(recording_id)
        view["job"] = job.model_dump(mode="json") if job else None
        return data_response(view)

    @router.get(
        "/api/v1/projects/{project_id}/recordings", response_model=ApiResponse
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
        "/api/v1/recordings/{recording_id}/review", response_model=ApiResponse
    )
    async def review_recording(recording_id: str, body: ReviewRequest):
        command = parse_flow_draft_review_command(
            json.dumps(body.command, ensure_ascii=False).encode("utf-8")
        )
        view = RecordingWorkflow(context.uow_factory).review(
            recording_id, command, bindings=body.bindings
        )
        return data_response(view.model_dump(mode="json"))

    @router.post(
        "/api/v1/recordings/{recording_id}/finalize", response_model=ApiResponse
    )
    async def finalize_recording(recording_id: str):
        view = RecordingWorkflow(context.uow_factory).finalize(
            recording_id,
            var_dir=context.var_dir,
            now_us=time.time_ns() // 1_000,
        )
        return data_response(view.model_dump(mode="json"))

    return router
