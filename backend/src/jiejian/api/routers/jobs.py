# =============================================================================
# Job API Router
#
# 定位
#   Job 取消命令和有序 SSE 事件的 HTTP 适配边界
#
# 职责
#   解析事件游标｜提交取消请求｜脱敏并流式输出 Job Event
#
# 调用链
#   FastAPI → jobs router → Execution services / Storage
# =============================================================================

from __future__ import annotations

import json
import time
from typing import Iterator

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import StreamingResponse

from ...application.context import ApplicationContext
from ...domain.lifecycle import JobState
from ...errors import ErrorCode, JiejianError
from ...redaction import redact
from ...execution.models import RequestCancellationV1
from ..responses import data_response
from ..schemas.common import ApiResponse


def _cursor(value: str | None) -> int:
    if value is None:
        return 0
    try:
        return max(int(value), 0)
    except ValueError:
        return 0


def build_jobs_router(context: ApplicationContext) -> APIRouter:
    router = APIRouter()

    @router.post("/api/v1/jobs/{job_id}/cancel", response_model=ApiResponse)
    async def cancel_job(job_id: str):
        result = context.job_queue.request_cancellation(
            RequestCancellationV1(
                schema_version="1",
                job_id=job_id,
                now_us=time.time_ns() // 1_000,
            )
        )
        return data_response(result.model_dump(mode="json"))

    @router.get("/api/v1/jobs/{job_id}/events", response_model=None)
    async def job_events(
        job_id: str,
        request: Request,
        after: int | None = Query(default=None, ge=0),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ):
        after = after if after is not None else _cursor(last_event_id)
        with context.uow_factory() as work:
            if work.jobs.get(job_id) is None:
                raise JiejianError(ErrorCode.JOB_NOT_FOUND, "任务不存在")

        def stream() -> Iterator[str]:
            cursor = after
            while True:
                with context.uow_factory() as work:
                    job = work.jobs.get(job_id)
                    events = work.job_events.list_for_job(job_id) if job else ()
                if job is None:
                    break
                for event in events:
                    if event.sequence <= cursor:
                        continue
                    cursor = event.sequence
                    payload = {
                        "schema_version": "1",
                        "job_id": job_id,
                        "sequence": event.sequence,
                        "event_type": event.event_type,
                        "source_state": event.source_state.value
                        if event.source_state
                        else None,
                        "target_state": event.target_state.value
                        if event.target_state
                        else None,
                        "occurred_at_us": event.occurred_at_us,
                        "metadata": redact(dict(event.metadata)),
                    }
                    yield (
                        f"id: {event.sequence}\n"
                        f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
                    )
                if job.state in {
                    JobState.SUCCEEDED,
                    JobState.FAILED,
                    JobState.CANCELLED,
                }:
                    break
                yield ": keep-alive\n\n"
                time.sleep(0.25)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
