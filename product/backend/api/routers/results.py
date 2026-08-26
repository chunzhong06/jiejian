# 结果 API 路由
# 只读取完整性已确认的报告、Evidence 与 Finding，不重新执行 Verification。

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from product.backend.workflows.context import ApplicationCore
from product.backend.workflows.results.published import PublishedResultReader
from product.backend.api.envelope import data_response
from product.backend.api.envelope import ApiResponse


class GateReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["1"]
    gate_result_id: str = Field(pattern=r"^gate_[0-9a-f]{32}$")


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

    @router.get("/api/runs/{run_id}/result-status", response_model=ApiResponse)
    async def get_result_status(run_id: str):
        return data_response(context.result_finalizer.status(run_id).model_dump(mode="json"))

    @router.get("/api/runs/{run_id}/presentation", response_model=ApiResponse)
    async def get_result_presentation(run_id: str):
        return data_response(
            context.result_presentation.build(run_id).model_dump(mode="json")
        )

    @router.get("/api/projects/{project_id}/results/history", response_model=ApiResponse)
    async def get_result_history(project_id: str):
        context.projects.get(project_id)
        return data_response(
            context.result_history.build(project_id).model_dump(mode="json")
        )

    @router.post("/api/runs/{run_id}/result-repair", response_model=ApiResponse)
    async def repair_result(run_id: str):
        return data_response(context.result_finalizer.repair(run_id).model_dump(mode="json"))

    @router.get("/api/runs/{run_id}/reports", response_model=ApiResponse)
    async def list_reports(run_id: str):
        return data_response(context.reports.list(run_id))

    @router.post("/api/runs/{run_id}/reports/gate", response_model=ApiResponse)
    async def create_gate_report(run_id: str, request: GateReportRequest):
        return data_response(context.reports.generate_gate(run_id, request.gate_result_id).model_dump(mode="json"))

    @router.get("/api/runs/{run_id}/reports/{report_id}", response_model=ApiResponse)
    async def get_permission_report(run_id: str, report_id: str):
        return data_response(context.reports.read(run_id, report_id))

    @router.get("/api/runs/{run_id}/reports/{report_id}/view")
    async def view_permission_report(run_id: str, report_id: str):
        return Response(
            content=context.reports.read_format(run_id, report_id, "html"),
            media_type="text/html; charset=utf-8",
            headers={
                "Content-Disposition": 'inline; filename="report.html"',
                "Content-Security-Policy": (
                    "default-src 'none'; style-src 'unsafe-inline'; script-src 'none'; "
                    "img-src 'none'; font-src 'none'; connect-src 'none'; media-src 'none'; "
                    "object-src 'none'; frame-src 'none'; child-src 'none'; form-action 'none'; "
                    "base-uri 'none'; frame-ancestors 'self'"
                ),
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
            },
        )

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
