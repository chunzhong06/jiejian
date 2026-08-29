# =============================================================================
# 普通权限设置控制面 API
#
# 定位
#   中文权限矩阵与 PermissionIntent、确定性编译器之间的本地 HTTP 适配层。
#
# 职责
#   读取逐动作矩阵与历史｜执行 human-only 审批｜审阅 Agent 建议｜显式生成内部检查配置。
#
# 边界
#   不接收 HTTP、秘密、Observer、Runner 或 PermissionContract 正文。
#
# 调用链
#   GUI → /api/projects/{project_id}/permission-intents → ApplicationCore
# =============================================================================

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import Field, field_validator
from product.backend.api.envelope import ApiModel, ApiResponse, data_response
from product.backend.core.permission_intent import PermissionIntentRelation
from product.backend.core.verification.permissions import PermissionExpectation
from product.backend.workflows.context import ApplicationCore


class PermissionIntentCellTarget(ApiModel):
    action_candidate_id: str = Field(min_length=1, max_length=64)
    subject_role_candidate_id: str = Field(min_length=1, max_length=64)
    resource_owner_role_candidate_id: str = Field(min_length=1, max_length=64)
    relation: Literal["OWNS", "SAME_ROLE_OTHER_ACCOUNT", "OTHER_ROLE"]


class PermissionIntentApprovalRequest(ApiModel):
    schema_version: Literal["1"]
    target: PermissionIntentCellTarget
    expectation: Literal["ALLOW", "DENY"] | None = None
    reason: str | None = Field(default=None, min_length=1, max_length=512)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str | None) -> str | None:
        if value is not None and (
            value != value.strip() or any(ord(char) < 32 for char in value)
        ):
            raise ValueError("reason must be trimmed printable text")
        return value


class PermissionIntentProposalApprovalRequest(ApiModel):
    schema_version: Literal["1"]
    reason: str | None = Field(default=None, min_length=1, max_length=512)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str | None) -> str | None:
        if value is not None and (
            value != value.strip() or any(ord(char) < 32 for char in value)
        ):
            raise ValueError("reason must be trimmed printable text")
        return value


class PermissionIntentProposalDecisionRequest(ApiModel):
    schema_version: Literal["1"]


class SecuritySetupCompileRequest(ApiModel):
    schema_version: Literal["1"]


def build_permission_intents_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/projects/{project_id}/permission-intents",
        response_model=ApiResponse,
    )
    async def get_permission_intents(project_id: str):
        return data_response(
            context.permission_intents.matrix(project_id).model_dump(mode="json")
        )

    @router.post(
        "/api/projects/{project_id}/permission-intents/approvals",
        response_model=ApiResponse,
    )
    async def approve_permission_intent(
        project_id: str,
        body: PermissionIntentApprovalRequest,
    ):
        expectation = (
            None
            if body.expectation is None
            else PermissionExpectation(body.expectation)
        )
        return data_response(
            context.permission_intents.confirm(
                project_id,
                body.target.action_candidate_id,
                body.target.subject_role_candidate_id,
                body.target.resource_owner_role_candidate_id,
                PermissionIntentRelation(body.target.relation),
                expectation=expectation,
                reason=body.reason or "本机界面确认权限要求",
            ).model_dump(mode="json")
        )

    @router.get(
        "/api/projects/{project_id}/permission-intents/{intent_id}/history",
        response_model=ApiResponse,
    )
    async def get_permission_intent_history(project_id: str, intent_id: str):
        return data_response(
            context.permission_intents.history(project_id, intent_id).model_dump(mode="json")
        )

    @router.get(
        "/api/projects/{project_id}/permission-intent-proposals",
        response_model=ApiResponse,
    )
    async def get_permission_intent_proposals(project_id: str):
        return data_response(
            context.permission_intents.proposals(project_id).model_dump(mode="json")
        )

    @router.post(
        "/api/projects/{project_id}/permission-intent-proposals/{proposal_id}/approve",
        response_model=ApiResponse,
    )
    async def approve_permission_intent_proposal(
        project_id: str,
        proposal_id: str,
        body: PermissionIntentProposalApprovalRequest,
    ):
        return data_response(
            context.permission_intents.approve_proposal(
                project_id,
                proposal_id,
                reason=body.reason or "本机界面批准 Agent 权限建议",
            ).model_dump(mode="json")
        )

    @router.post(
        "/api/projects/{project_id}/permission-intent-proposals/{proposal_id}/reject",
        response_model=ApiResponse,
    )
    async def reject_permission_intent_proposal(
        project_id: str,
        proposal_id: str,
        body: PermissionIntentProposalDecisionRequest,
    ):
        return data_response(
            context.permission_intents.reject_proposal(
                project_id,
                proposal_id,
            ).model_dump(mode="json")
        )

    @router.post(
        "/api/projects/{project_id}/security-setup/compile",
        response_model=ApiResponse,
    )
    async def compile_security_setup(
        project_id: str,
        body: SecuritySetupCompileRequest,
    ):
        return data_response(context.security_setup.compile(project_id).model_dump(mode="json"))

    return router


__all__ = [
    "PermissionIntentApprovalRequest",
    "PermissionIntentCellTarget",
    "PermissionIntentProposalApprovalRequest",
    "PermissionIntentProposalDecisionRequest",
    "build_permission_intents_router",
]
