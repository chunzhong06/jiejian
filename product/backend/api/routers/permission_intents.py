# =============================================================================
# 普通权限设置控制面 API
#
# 定位
#   中文权限矩阵与 PermissionIntent、确定性编译器之间的本地 HTTP 适配层。
#
# 职责
#   读取逐动作矩阵｜确认允许/拒绝/未确认｜显式生成内部检查配置。
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
from pydantic import Field

from product.backend.api.envelope import ApiModel, ApiResponse, data_response
from product.backend.core.permission_intent import PermissionIntentRelation
from product.backend.core.verification.permissions import PermissionExpectation
from product.backend.workflows.context import ApplicationCore


class PermissionIntentConfirmRequest(ApiModel):
    schema_version: Literal["1"]
    expectation: Literal["ALLOW", "DENY"] | None = None
    actor: str = Field(min_length=1, max_length=128)


class SecuritySetupCompileRequest(ApiModel):
    schema_version: Literal["1"]
    actor: str = Field(min_length=1, max_length=128)


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

    @router.put(
        "/api/projects/{project_id}/permission-intents/{action_id}/"
        "{subject_role_id}/{owner_role_id}/{relation}",
        response_model=ApiResponse,
    )
    async def confirm_permission_intent(
        project_id: str,
        action_id: str,
        subject_role_id: str,
        owner_role_id: str,
        relation: PermissionIntentRelation,
        body: PermissionIntentConfirmRequest,
    ):
        expectation = (
            None
            if body.expectation is None
            else PermissionExpectation(body.expectation)
        )
        return data_response(
            context.permission_intents.confirm(
                project_id,
                action_id,
                subject_role_id,
                owner_role_id,
                relation,
                expectation=expectation,
                actor=body.actor,
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
        return data_response(
            context.security_setup.compile(
                project_id,
                actor=body.actor,
            ).model_dump(mode="json")
        )

    return router


__all__ = ["build_permission_intents_router"]
