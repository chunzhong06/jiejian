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
from fastapi.responses import Response

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

    @router.get("/api/v2/runs/{run_id}/reports", response_model=ApiResponse)
    async def list_reports(run_id: str):
        return data_response(context.reports.list(run_id))

    @router.get("/api/v2/runs/{run_id}/reports/{report_id}", response_model=ApiResponse)
    async def get_v2_report(run_id: str, report_id: str):
        return data_response(context.reports.read(run_id, report_id))

    @router.get("/api/v2/runs/{run_id}/reports/{report_id}/formats/{output_format}")
    async def download_v2_report(run_id: str, report_id: str, output_format: str):
        media_type = {
            "json": "application/json",
            "html": "text/html; charset=utf-8",
            "sarif": "application/sarif+json",
            "junit": "application/xml",
        }.get(output_format)
        if media_type is None:
            from ...errors import ErrorCode, JiejianError

            raise JiejianError(ErrorCode.INPUT_INVALID, "报告格式无效")
        filename = {
            "json": "report.json",
            "html": "report.html",
            "sarif": "report.sarif.json",
            "junit": "report.junit.xml",
        }[output_format]
        return Response(
            content=context.reports.read_format(run_id, report_id, output_format),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.get(
        "/api/v1/runs/{run_id}/evidence/{evidence_id}",
        response_model=ApiResponse,
    )
    async def get_evidence(run_id: str, evidence_id: str):
        view = results.read(run_id)
        return data_response(results.evidence_detail(view, evidence_id))

    return router
