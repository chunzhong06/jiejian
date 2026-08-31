# =============================================================================
# 测试账号控制面 API
#
# 定位
#   普通 GUI 与 TestIdentityService 之间的本地受控 HTTP 适配层。
#
# 职责
#   创建和查询测试账号｜显式重置登录状态｜安全删除账号及精确秘密引用。
#
# 边界
#   请求不接收密码、Cookie 或 Token；响应不返回 secret_ref 和秘密正文。
#
# 调用链
#   GUI → /api/test-identities → TestIdentityService
# =============================================================================

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import Field

from product.backend.api.envelope import ApiModel, ApiResponse, data_response
from product.backend.composition import ApplicationCore


class TestIdentityCreateRequest(ApiModel):
    schema_version: Literal["1"]
    role_candidate_id: str = Field(pattern=r"^role_[0-9a-f]{32}$")
    label: str = Field(min_length=1, max_length=128)


class IdentityPreparationCommand(ApiModel):
    schema_version: Literal["1"]


def build_test_identities_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/projects/{project_id}/test-identities",
        response_model=ApiResponse,
    )
    async def list_test_identities(project_id: str):
        return data_response(
            [
                item.model_dump(mode="json")
                for item in context.test_identities.list(project_id)
            ]
        )

    @router.post(
        "/api/projects/{project_id}/test-identities",
        response_model=ApiResponse,
        status_code=201,
    )
    async def create_test_identity(
        project_id: str,
        body: TestIdentityCreateRequest,
    ):
        created = context.test_identities.create(
            project_id,
            role_candidate_id=body.role_candidate_id,
            label=body.label,
        )
        return data_response(created.model_dump(mode="json"), status_code=201)

    @router.get(
        "/api/test-identities/{identity_id}",
        response_model=ApiResponse,
    )
    async def get_test_identity(identity_id: str):
        return data_response(
            context.test_identities.get(identity_id).model_dump(mode="json")
        )

    @router.post(
        "/api/test-identities/{identity_id}/preparations",
        response_model=ApiResponse,
        status_code=201,
    )
    async def start_identity_preparation(
        identity_id: str,
        body: IdentityPreparationCommand,
    ):
        _ = body
        started = context.identity_preparations.start(identity_id)
        return data_response(started.model_dump(mode="json"), status_code=201)

    @router.get(
        "/api/identity-preparations/{preparation_id}",
        response_model=ApiResponse,
    )
    async def get_identity_preparation(preparation_id: str):
        return data_response(
            context.identity_preparations.status(preparation_id).model_dump(mode="json")
        )

    @router.post(
        "/api/identity-preparations/{preparation_id}/confirm",
        response_model=ApiResponse,
    )
    async def confirm_identity_preparation(
        preparation_id: str,
        body: IdentityPreparationCommand,
    ):
        _ = body
        return data_response(
            context.identity_preparations.confirm(preparation_id).model_dump(mode="json")
        )

    @router.post(
        "/api/identity-preparations/{preparation_id}/cancel",
        response_model=ApiResponse,
    )
    async def cancel_identity_preparation(
        preparation_id: str,
        body: IdentityPreparationCommand,
    ):
        _ = body
        return data_response(
            context.identity_preparations.cancel(preparation_id).model_dump(mode="json")
        )

    @router.post(
        "/api/test-identities/{identity_id}/reset",
        response_model=ApiResponse,
    )
    async def reset_test_identity(
        identity_id: str,
        body: IdentityPreparationCommand,
    ):
        _ = body
        return data_response(
            context.test_identities.reset(identity_id).model_dump(mode="json")
        )

    @router.delete(
        "/api/test-identities/{identity_id}",
        response_model=ApiResponse,
    )
    async def delete_test_identity(identity_id: str):
        context.test_identities.delete(identity_id)
        return data_response({"deleted": True, "identity_id": identity_id})

    return router
