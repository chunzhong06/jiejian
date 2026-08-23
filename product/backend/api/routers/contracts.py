# Contract API Router
# 只适配 HTTP Schema 并调用共享 ContractWorkbench，不复制契约治理逻辑。

from __future__ import annotations

from fastapi import APIRouter, Query

from product.backend.workflows.context import ApplicationCore
from product.backend.api.envelope import data_response
from product.backend.api.envelope import ApiResponse


def build_contracts_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/projects/{project_id}/contract-governance",
        response_model=ApiResponse,
    )
    async def contract_governance_snapshot(project_id: str):
        return data_response(context.contract_workbench.snapshot(project_id).model_dump(mode="json"))

    @router.post(
        "/api/projects/{project_id}/contract-governance/requirements",
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
        "/api/projects/{project_id}/contract-governance/candidates/derive",
        response_model=ApiResponse,
    )
    async def derive_contract_candidates(
        project_id: str, body: CandidateDeriveRequest
    ):
        result = context.contract_workbench.derive_candidates(
            project_id,
            requirement_ids=tuple(body.requirement_ids),
            actor=body.actor,
        )
        return data_response(result.model_dump(mode="json"))

    @router.post(
        "/api/projects/{project_id}/contract-governance/candidates/llm",
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
        "/api/projects/{project_id}/contract-governance/contracts",
        response_model=ApiResponse,
    )
    async def create_governance_contract(
        project_id: str, body: ContractDraftRequest
    ):
        version = context.contract_workbench.create_draft(
            project_id,
            body.contract_id,
            snapshot=body.snapshot,
            candidate_ids=tuple(body.candidate_ids),
            requirement_ids=tuple(body.requirement_ids),
            actor=body.actor,
        )
        return data_response(version.model_dump(mode="json"))

    @router.post(
        "/api/projects/{project_id}/contract-governance/contracts/{contract_id}/revisions",
        response_model=ApiResponse,
    )
    async def revise_governance_contract(
        project_id: str, contract_id: str, body: ContractRevisionRequest
    ):
        version = context.contract_workbench.revise_active(
            project_id,
            contract_id,
            snapshot=body.snapshot,
            candidate_ids=tuple(body.candidate_ids),
            requirement_ids=tuple(body.requirement_ids),
            actor=body.actor,
        )
        return data_response(version.model_dump(mode="json"))

    @router.get(
        "/api/projects/{project_id}/contract-governance/contracts/{contract_id}/versions",
        response_model=ApiResponse,
    )
    async def list_governance_versions(project_id: str, contract_id: str):
        versions = context.contract_workbench.list_versions(project_id, contract_id)
        return data_response([item.model_dump(mode="json") for item in versions])

    @router.post(
        "/api/projects/{project_id}/contract-governance/contracts/{contract_id}/versions/{version}/submit",
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
        "/api/projects/{project_id}/contract-governance/contracts/{contract_id}/versions/{version}/reject",
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
        "/api/projects/{project_id}/contract-governance/contracts/{contract_id}/versions/{version}/activate",
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
        "/api/projects/{project_id}/contract-governance/contracts/{contract_id}/versions/{version}/assessment",
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
        "/api/projects/{project_id}/contract-governance/contracts/{contract_id}/versions/{version}/diff",
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
        "/api/projects/{project_id}/contract-governance/contracts/{contract_id}/versions/{version}/drift",
        response_model=ApiResponse,
    )
    async def drift_governance_version(
        project_id: str, contract_id: str, version: int
    ):
        report = context.contract_workbench.drift(project_id, contract_id, version)
        return data_response(report.model_dump(mode="json"))

    @router.get("/api/runs/{run_id}/contract", response_model=ApiResponse)
    async def get_run_contract(run_id: str):
        resolution = context.contract_workbench.history(run_id)
        return data_response(resolution.model_dump(mode="json"))

    return router

# Contract 治理请求模型。

import json
from typing import Literal

from pydantic import Field, field_validator

from product.backend.api.envelope import ApiModel
from product.backend.core.verification.permissions import PermissionContract, parse_permission_contract


class RequirementCreateRequest(ApiModel):
    schema_version: Literal["1"]
    text: str = Field(min_length=1, max_length=16_384)
    security_tags: list[str] = Field(default_factory=list, max_length=64)
    actor: str = Field(min_length=1, max_length=128)


class CandidateDeriveRequest(ApiModel):
    schema_version: Literal["1"]
    requirement_ids: list[str] = Field(min_length=1, max_length=512)
    actor: str = Field(min_length=1, max_length=128)


class LLMCandidateRequest(ApiModel):
    schema_version: Literal["1"]
    requirement_ids: list[str] = Field(min_length=1, max_length=512)
    actor: str = Field(min_length=1, max_length=128)
    profile_name: str | None = Field(default=None, min_length=1, max_length=128)


class ContractDraftRequest(ApiModel):
    schema_version: Literal["1"]
    contract_id: str = Field(min_length=1, max_length=128)
    snapshot: PermissionContract
    candidate_ids: list[str] = Field(default_factory=list, max_length=512)
    requirement_ids: list[str] = Field(default_factory=list, max_length=512)
    actor: str = Field(min_length=1, max_length=128)

    @field_validator("snapshot", mode="before")
    @classmethod
    def parse_snapshot(cls, value):
        return value if isinstance(value, PermissionContract) else parse_permission_contract(json.dumps(value))


class ContractRevisionRequest(ApiModel):
    schema_version: Literal["1"]
    snapshot: PermissionContract
    candidate_ids: list[str] = Field(default_factory=list, max_length=512)
    requirement_ids: list[str] = Field(default_factory=list, max_length=512)
    actor: str = Field(min_length=1, max_length=128)

    @field_validator("snapshot", mode="before")
    @classmethod
    def parse_snapshot(cls, value):
        return value if isinstance(value, PermissionContract) else parse_permission_contract(json.dumps(value))


class GovernanceActorRequest(ApiModel):
    schema_version: Literal["1"]
    actor: str = Field(min_length=1, max_length=128)
