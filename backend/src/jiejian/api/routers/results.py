# =============================================================================
# Results API Router
#
# 定位
#   已发布报告、Evidence 与 Finding 的只读 HTTP 适配器
#
# 职责
#   解析结果标识｜调用统一发布读取器｜返回完整性已确认的数据
#
# 调用链
#   FastAPI → results router → PublishedResultReader
# =============================================================================

from __future__ import annotations

from fastapi import APIRouter

from ...application.context import ApplicationContext
from ...results.published import PublishedResultReader
from ..responses import data_response
from ..schemas.common import ApiResponse


def build_results_router(
    context: ApplicationContext, results: PublishedResultReader
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v1/runs/{run_id}/report", response_model=ApiResponse)
    async def get_report(run_id: str):
        return data_response(results.report(results.read(run_id)))

    @router.get("/api/v1/runs/{run_id}/evidence", response_model=ApiResponse)
    async def list_evidence(run_id: str):
        return data_response(
            [item.model_dump(mode="json") for item in results.read(run_id).evidence]
        )

    @router.get("/api/v1/runs/{run_id}/findings", response_model=ApiResponse)
    async def list_findings(run_id: str):
        view = results.read(run_id)
        return data_response(results.findings(view))

    @router.get("/api/v2/runs/{run_id}/findings", response_model=ApiResponse)
    async def list_stable_findings(run_id: str):
        return data_response(context.findings.findings_for_run(run_id))

    @router.get(
        "/api/v1/runs/{run_id}/evidence/{evidence_id}",
        response_model=ApiResponse,
    )
    async def get_evidence(run_id: str, evidence_id: str):
        view = results.read(run_id)
        return data_response(results.evidence_detail(view, evidence_id))

    return router
