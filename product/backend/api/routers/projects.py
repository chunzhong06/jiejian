# 项目 API 路由：暴露应用接入、发现候选与来源理解的受控 HTTP 边界。
# 正式业务边界由独立 Business Boundary Router 承担，本路由不写权限事实。

from __future__ import annotations

from typing import Literal
from fastapi import APIRouter
from pydantic import Field

from product.backend.composition import ApplicationCore
from product.backend.core.applications.models import ActionRiskHint, CandidateDecision, CandidateSelection
from product.backend.api.envelope import data_response
from product.backend.api.envelope import ApiResponse
from product.backend.api.envelope import ApiModel


def build_projects_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.post('/api/projects/{project_id}/controlled-runtime/preview', response_model=ApiResponse)
    def runtime_preview(project_id: str, body: RuntimePreviewRequest):
        return data_response(context.node_runtime.preview(project_id,**body.model_dump()).model_dump(mode='json'))

    @router.post('/api/projects/{project_id}/controlled-runtime/start', response_model=ApiResponse)
    def runtime_start(project_id: str, body: RuntimeStartRequest):
        return data_response(context.node_runtime.start(project_id,**body.model_dump()),status_code=202)

    @router.get('/api/projects/{project_id}/controlled-runtime', response_model=ApiResponse)
    def runtime_state(project_id: str):
        return data_response(context.node_runtime.state(project_id))

    @router.get('/api/projects/{project_id}/controlled-runtime/operations/{operation_id}', response_model=ApiResponse)
    def runtime_operation(project_id: str, operation_id: str):
        return data_response(context.node_runtime.operation(project_id,operation_id))

    @router.post('/api/projects/{project_id}/controlled-runtime/operations/{operation_id}/cancel', response_model=ApiResponse)
    def runtime_cancel(project_id: str, operation_id: str):
        return data_response(context.node_runtime.cancel(project_id,operation_id))

    @router.post('/api/projects/{project_id}/controlled-runtime/stop', response_model=ApiResponse)
    def runtime_stop(project_id: str, body: RuntimeStopRequest):
        return data_response(context.node_runtime.stop(project_id,instance_id=body.instance_id))

    @router.post("/api/applications/connect", response_model=ApiResponse)
    def connect_application(body: ApplicationConnectRequest):
        result = context.application_understanding.connect(
            body.source_root,
            project_name=body.project_name,
        )
        return data_response(result.model_dump(mode="json"), status_code=201)

    @router.get("/api/projects", response_model=ApiResponse)
    async def list_projects(include_archived: bool = False):
        return data_response(context.projects.list_for_display(include_archived=include_archived))

    @router.get("/api/projects/{project_id}", response_model=ApiResponse)
    async def get_project(project_id: str):
        return data_response(context.projects.get(project_id).model_dump(mode="json"))

    @router.delete("/api/projects/{project_id}", response_model=ApiResponse)
    async def archive_project(project_id: str):
        """移除普通应用视图，保留 Project 及全部历史结果。"""

        return data_response(
            context.project_lifecycle.archive(project_id).model_dump(mode="json")
        )

    @router.get(
        "/api/projects/{project_id}/application-understanding",
        response_model=ApiResponse,
    )
    def get_application_understanding(project_id: str):
        return data_response(
            context.application_understanding.get(project_id).model_dump(mode="json")
        )

    @router.post(
        "/api/projects/{project_id}/endpoint-candidates",
        response_model=ApiResponse,
    )
    def discover_endpoint_candidates(project_id: str):
        return data_response(
            context.application_understanding.discover_endpoints(project_id).model_dump(
                mode="json"
            )
        )

    @router.put(
        "/api/projects/{project_id}/endpoint",
        response_model=ApiResponse,
    )
    def confirm_endpoint(project_id: str, body: EndpointConfirmationRequest):
        return data_response(
            context.application_understanding.confirm_endpoint(
                project_id,
                endpoint=body.endpoint,
                revision=body.revision,
            ).model_dump(mode="json")
        )

    @router.put(
        "/api/projects/{project_id}/source-analysis-authorization",
        response_model=ApiResponse,
    )
    def authorize_source_analysis(
        project_id: str,
        body: SourceAnalysisAuthorizationRequest,
    ):
        return data_response(
            context.application_understanding.authorize_source_analysis(
                project_id,
                revision=body.revision,
            ).model_dump(mode="json")
        )

    @router.post(
        "/api/projects/{project_id}/source-analysis",
        response_model=ApiResponse,
    )
    def analyze_source(project_id: str, body: SourceAnalysisRequest):
        return data_response(
            context.application_understanding.analyze_source(
                project_id,
                revision=body.revision,
            ).model_dump(mode="json")
        )

    @router.put("/api/projects/{project_id}/candidate-decisions", response_model=ApiResponse)
    def decide_candidates(project_id: str, body: CandidateBatchDecisionRequest):
        return data_response(context.application_understanding.decide_candidates(
            project_id, revision=body.revision, decisions=tuple(body.decisions),
        ).model_dump(mode="json"))

    @router.put(
        "/api/projects/{project_id}/roles/{candidate_id}",
        response_model=ApiResponse,
    )
    def decide_role(
        project_id: str,
        candidate_id: str,
        body: CandidateDecisionRequest,
    ):
        return data_response(
            context.application_understanding.decide_role(
                project_id,
                candidate_id,
                revision=body.revision,
                decision=CandidateDecision(body.decision),
                display_name=body.display_name,
            ).model_dump(mode="json")
        )

    @router.post(
        "/api/projects/{project_id}/roles",
        response_model=ApiResponse,
    )
    def add_manual_role(project_id: str, body: ManualRoleRequest):
        return data_response(
            context.application_understanding.add_manual_role(
                project_id,
                revision=body.revision,
                display_name=body.display_name,
            ).model_dump(mode="json"),
            status_code=201,
        )

    @router.put(
        "/api/projects/{project_id}/actions/{candidate_id}",
        response_model=ApiResponse,
    )
    def decide_action(
        project_id: str,
        candidate_id: str,
        body: CandidateDecisionRequest,
    ):
        return data_response(
            context.application_understanding.decide_action(
                project_id,
                candidate_id,
                revision=body.revision,
                decision=CandidateDecision(body.decision),
                display_name=body.display_name,
            ).model_dump(mode="json")
        )

    @router.post(
        "/api/projects/{project_id}/actions",
        response_model=ApiResponse,
    )
    def add_manual_action(project_id: str, body: ManualActionRequest):
        return data_response(
            context.application_understanding.add_manual_action(
                project_id,
                revision=body.revision,
                display_name=body.display_name,
                risk_hint=ActionRiskHint(body.risk_hint),
            ).model_dump(mode="json"),
            status_code=201,
        )

    return router


class RuntimePreviewRequest(ApiModel):
    entry: str = Field(min_length=1,max_length=512)
    port: int = Field(ge=1024,le=65535)
    revision: int = Field(ge=0)
    consent_source_read: bool = False


class RuntimeStartRequest(ApiModel):
    entry: str = Field(min_length=1,max_length=512)
    port: int = Field(ge=1024,le=65535)
    revision: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    operation_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    consent_execute: bool


class RuntimeStopRequest(ApiModel):
    instance_id: str = Field(pattern=r'^rti_[0-9a-f]{32}$')


class ApplicationConnectRequest(ApiModel):
    schema_version: Literal["1"]
    source_root: str = Field(min_length=1, max_length=32_768)
    project_name: str | None = Field(default=None, min_length=1, max_length=128)


class EndpointConfirmationRequest(ApiModel):
    schema_version: Literal["1"]
    endpoint: str = Field(min_length=1, max_length=2048)
    revision: int = Field(ge=0, le=1_000_000)


class SourceAnalysisAuthorizationRequest(ApiModel):
    schema_version: Literal["1"]
    authorized: Literal[True]
    revision: int = Field(ge=0, le=1_000_000)


class SourceAnalysisRequest(ApiModel):
    schema_version: Literal["1"]
    revision: int = Field(ge=0, le=1_000_000)


class CandidateBatchDecisionRequest(ApiModel):
    schema_version: Literal["1"]
    revision: int = Field(ge=0, le=1_000_000)
    decisions: list[CandidateSelection] = Field(min_length=1, max_length=256)


class CandidateDecisionRequest(ApiModel):
    schema_version: Literal["1"]
    decision: Literal["PROPOSED", "CONFIRMED", "REJECTED"]
    display_name: str | None = Field(default=None, min_length=1, max_length=256)
    revision: int = Field(ge=0, le=1_000_000)


class ManualRoleRequest(ApiModel):
    schema_version: Literal["1"]
    display_name: str = Field(min_length=1, max_length=128)
    revision: int = Field(ge=0, le=1_000_000)


class ManualActionRequest(ApiModel):
    schema_version: Literal["1"]
    display_name: str = Field(min_length=1, max_length=256)
    risk_hint: Literal["READ", "WRITE", "DELETE", "ADMIN", "UNKNOWN"] = "UNKNOWN"
    revision: int = Field(ge=0, le=1_000_000)
