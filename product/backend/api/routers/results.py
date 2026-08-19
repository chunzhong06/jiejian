# Results API Router
# 只读取完整性已确认的报告、Evidence 与 Finding，不重新执行 Verification。

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

from product.backend.workflows.context import ApplicationCore
from product.backend.workflows.results.published import PublishedResultReader
from product.backend.api.envelope import data_response
from product.backend.api.envelope import ApiResponse


def build_results_router(
    context: ApplicationCore, results: PublishedResultReader
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/runs/{run_id}/evidence", response_model=ApiResponse)
    async def list_evidence(run_id: str):
        return data_response(
            [item.model_dump(mode="json") for item in results.read(run_id).evidence]
        )

    @router.get("/api/runs/{run_id}/findings", response_model=ApiResponse)
    async def list_findings(run_id: str):
        return data_response(context.findings.findings_for_run(run_id))

    @router.get("/api/runs/{run_id}/reports", response_model=ApiResponse)
    async def list_reports(run_id: str):
        return data_response(context.reports.list(run_id))

    @router.get("/api/runs/{run_id}/reports/{report_id}", response_model=ApiResponse)
    async def get_permission_report(run_id: str, report_id: str):
        return data_response(context.reports.read(run_id, report_id))

    @router.get("/api/runs/{run_id}/reports/{report_id}/formats/{output_format}")
    async def download_permission_report(run_id: str, report_id: str, output_format: str):
        media_type = {
            "json": "application/json",
            "html": "text/html; charset=utf-8",
            "sarif": "application/sarif+json",
            "junit": "application/xml",
        }.get(output_format)
        if media_type is None:
            from product.backend.core.errors import ErrorCode, JiejianError

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
        "/api/runs/{run_id}/evidence/{evidence_id}",
        response_model=ApiResponse,
    )
    async def get_evidence(run_id: str, evidence_id: str):
        view = results.read(run_id)
        return data_response(results.evidence_detail(view, evidence_id))

    return router
