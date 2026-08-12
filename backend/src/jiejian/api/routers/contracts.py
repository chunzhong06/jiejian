# =============================================================================
# Contract API Router
#
# 定位
#   HTTP Contract 请求到共享 ContractWorkbench 的薄控制面适配器
#
# 职责
#   校验 Wire Schema｜调用治理和分析能力｜返回统一 API envelope
#
# 调用链
#   FastAPI → contracts router → ApplicationContext.contract_workbench
# =============================================================================

from __future__ import annotations

from fastapi import APIRouter, Query

from ...application.context import ApplicationContext
from ..responses import data_response
from ..schemas.common import ApiResponse
from ..schemas.contracts import (
    CandidateDeriveRequest,
    ContractDraftRequest,
    ContractRevisionRequest,
    GovernanceActorRequest,
    LLMCandidateRequest,
    RequirementCreateRequest,
)


def build_contracts_router(context: ApplicationContext) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/v1/projects/{project_id}/contract-governance",
        response_model=ApiResponse,
    )
    async def contract_governance_snapshot(project_id: str):
        return data_response(context.contract_workbench.snapshot(project_id).model_dump(mode="json"))

    @router.post(
        "/api/v1/projects/{project_id}/contract-governance/requirements",
        response_model=ApiResponse,
    )
    async def create_contract_requirement(
        project_id: str, body: RequirementCreateRequest
    ):
        requirement = context.contract_workbench.create_requirement(
            project_id,
            text=body.text,
            security_tags=tuple(body.security_tags),
            actor=body.actor,
        )
        return data_response(requirement.model_dump(mode="json"))

    @router.post(
        "/api/v1/projects/{project_id}/contract-governance/candidates/derive",
        response_model=ApiResponse,
    )
    async def derive_contract_candidates(
        project_id: str, body: CandidateDeriveRequest
    ):
        result = context.contract_workbench.derive_candidates(
            project_id,
            requirement_ids=tuple(body.requirement_ids),
            include_flow=body.include_flow,
            actor=body.actor,
        )
        return data_response(result.model_dump(mode="json"))

    @router.post(
        "/api/v1/projects/{project_id}/contract-governance/candidates/llm",
        response_model=ApiResponse,
    )
    async def generate_llm_candidates(project_id: str, body: LLMCandidateRequest):
        result = context.contract_workbench.generate_llm(
            project_id,
            requirement_ids=tuple(body.requirement_ids),
            actor=body.actor,
            profile_name=body.profile_name,
        )
        return data_response(result.model_dump(mode="json"))

    @router.post(
        "/api/v1/projects/{project_id}/contract-governance/contracts",
        response_model=ApiResponse,
    )
    async def create_governance_contract(
        project_id: str, body: ContractDraftRequest
    ):
        version = context.contract_workbench.create_draft(
            project_id,
            body.contract_id,
            candidate_ids=tuple(body.candidate_ids),
            actor=body.actor,
        )
        return data_response(version.model_dump(mode="json"))

    @router.post(
        "/api/v1/projects/{project_id}/contract-governance/contracts/{contract_id}/revisions",
        response_model=ApiResponse,
    )
    async def revise_governance_contract(
        project_id: str, contract_id: str, body: ContractRevisionRequest
    ):
        version = context.contract_workbench.revise_active(
            project_id,
            contract_id,
            candidate_ids=tuple(body.candidate_ids),
            actor=body.actor,
        )
        return data_response(version.model_dump(mode="json"))

    @router.get(
        "/api/v1/projects/{project_id}/contract-governance/contracts/{contract_id}/versions",
        response_model=ApiResponse,
    )
    async def list_governance_versions(project_id: str, contract_id: str):
        versions = context.contract_workbench.list_versions(project_id, contract_id)
        return data_response([item.model_dump(mode="json") for item in versions])

    @router.post(
        "/api/v1/projects/{project_id}/contract-governance/contracts/{contract_id}/versions/{version}/submit",
        response_model=ApiResponse,
    )
    async def submit_governance_version(
        project_id: str,
        contract_id: str,
        version: int,
        body: GovernanceActorRequest,
    ):
        item = context.contract_workbench.submit_review(
            project_id, contract_id, version, actor=body.actor
        )
        return data_response(item.model_dump(mode="json"))

    @router.post(
        "/api/v1/projects/{project_id}/contract-governance/contracts/{contract_id}/versions/{version}/reject",
        response_model=ApiResponse,
    )
    async def reject_governance_version(
        project_id: str,
        contract_id: str,
        version: int,
        body: GovernanceActorRequest,
    ):
        item = context.contract_workbench.reject_review(
            project_id, contract_id, version, actor=body.actor
        )
        return data_response(item.model_dump(mode="json"))

    @router.post(
        "/api/v1/projects/{project_id}/contract-governance/contracts/{contract_id}/versions/{version}/activate",
        response_model=ApiResponse,
    )
    async def activate_governance_version(
        project_id: str,
        contract_id: str,
        version: int,
        body: GovernanceActorRequest,
    ):
        item = context.contract_workbench.activate_review(
            project_id, contract_id, version, actor=body.actor
        )
        return data_response(item.model_dump(mode="json"))

    @router.get(
        "/api/v1/projects/{project_id}/contract-governance/contracts/{contract_id}/versions/{version}/assessment",
        response_model=ApiResponse,
    )
    async def assess_governance_version(
        project_id: str, contract_id: str, version: int
    ):
        assessment = context.contract_workbench.assessment(
            project_id, contract_id, version
        )
        return data_response(assessment.model_dump(mode="json"))

    @router.get(
        "/api/v1/projects/{project_id}/contract-governance/contracts/{contract_id}/versions/{version}/diff",
        response_model=ApiResponse,
    )
    async def diff_governance_version(
        project_id: str,
        contract_id: str,
        version: int,
        from_version: int = Query(..., ge=1),
    ):
        diff = context.contract_workbench.diff(
            project_id, contract_id, version, from_version
        )
        return data_response(diff.model_dump(mode="json"))

    @router.get(
        "/api/v1/projects/{project_id}/contract-governance/contracts/{contract_id}/versions/{version}/drift",
        response_model=ApiResponse,
    )
    async def drift_governance_version(
        project_id: str, contract_id: str, version: int
    ):
        report = context.contract_workbench.drift(project_id, contract_id, version)
        return data_response(report.model_dump(mode="json"))

    @router.get("/api/v1/runs/{run_id}/contract", response_model=ApiResponse)
    async def get_run_contract(run_id: str):
        resolution = context.contract_workbench.history(run_id)
        return data_response(resolution.model_dump(mode="json"))

    return router
