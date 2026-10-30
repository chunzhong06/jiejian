# 测试账号控制面 API：创建、查询、重置和删除稳定 Actor 账号。
# 请求不接收秘密，响应不返回 secret_ref 或秘密正文。

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import Field

from product.backend.interfaces.http.envelope import ApiModel, ApiResponse, data_response
from product.backend.bootstrap import ApplicationCore


class TestIdentityCreateRequest(ApiModel):
    schema_version: Literal["1"]
    actor_id: str = Field(pattern=r"^bar_[0-9a-f]{32}$")
    actor_revision: int = Field(ge=1)
    label: str = Field(min_length=1, max_length=128)
    operation_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{32}$')


class TestIdentityResetRequest(ApiModel):
    schema_version: Literal["1"]


class TestIdentityLoginRequest(TestIdentityResetRequest):
    operation_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{32}$')


def build_test_identities_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.get('/api/projects/{project_id}/identity-preparations', response_model=ApiResponse)
    def preparations(project_id: str):
        context.projects.get(project_id)
        return data_response([item.model_dump(mode='json') for item in context.identity_preparations.list(project_id)])

    @router.get(
        "/api/projects/{project_id}/test-identities",
        response_model=ApiResponse,
    )
    def list_test_identities(project_id: str):
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
    def create_test_identity(
        project_id: str,
        body: TestIdentityCreateRequest,
    ):
        created = context.test_identities.create(
            project_id,
            actor_id=body.actor_id,
            actor_revision=body.actor_revision,
            label=body.label,
            operation_id=body.operation_id,
        )
        return data_response(created.model_dump(mode="json"), status_code=201)

    @router.get('/api/projects/{project_id}/test-identity-requests/{operation_id}', response_model=ApiResponse)
    def identity_request(project_id: str, operation_id: str):
        value = context.test_identities.created(project_id, operation_id)
        return data_response(None if value is None else value.model_dump(mode='json'))

    @router.get('/api/test-identities/{identity_id}/preparations/latest', response_model=ApiResponse)
    def latest_preparation(identity_id: str):
        value = context.identity_preparations.latest(identity_id)
        return data_response(None if value is None else value.model_dump(mode='json'))

    @router.get('/api/test-identities/{identity_id}/preparation-requests/{operation_id}', response_model=ApiResponse)
    def requested_preparation(identity_id: str, operation_id: str):
        value = context.identity_preparations.requested(identity_id, operation_id)
        return data_response(None if value is None else value.model_dump(mode='json'))

    @router.get(
        "/api/test-identities/{identity_id}",
        response_model=ApiResponse,
    )
    def get_test_identity(identity_id: str):
        return data_response(
            context.test_identities.get(identity_id).model_dump(mode="json")
        )

    @router.post(
        "/api/test-identities/{identity_id}/reset",
        response_model=ApiResponse,
    )
    def reset_test_identity(
        identity_id: str,
        body: TestIdentityResetRequest,
    ):
        _ = body
        return data_response(
            context.test_identities.reset(identity_id).model_dump(mode="json")
        )

    @router.delete(
        "/api/test-identities/{identity_id}",
        response_model=ApiResponse,
    )
    def delete_test_identity(identity_id: str):
        context.test_identities.delete(identity_id)
        return data_response({"deleted": True, "identity_id": identity_id})

    @router.post("/api/test-identities/{identity_id}/preparations", response_model=ApiResponse)
    def start_preparation(identity_id: str, body: TestIdentityLoginRequest):
        return data_response(context.identity_preparations.start(identity_id, operation_id=body.operation_id).model_dump(mode="json"))

    @router.get("/api/identity-preparations/{preparation_id}", response_model=ApiResponse)
    def get_preparation(preparation_id: str):
        return data_response(context.identity_preparations.status(preparation_id).model_dump(mode="json"))

    @router.post("/api/identity-preparations/{preparation_id}/confirm", response_model=ApiResponse)
    def confirm_preparation(preparation_id: str, body: TestIdentityResetRequest):
        return data_response(context.identity_preparations.confirm(preparation_id).model_dump(mode="json"))

    @router.post("/api/identity-preparations/{preparation_id}/cancel", response_model=ApiResponse)
    def cancel_preparation(preparation_id: str, body: TestIdentityResetRequest):
        return data_response(context.identity_preparations.cancel(preparation_id).model_dump(mode="json"))

    @router.post('/api/identity-preparations/{preparation_id}/cleanup', response_model=ApiResponse)
    def cleanup_preparation(preparation_id: str, body: TestIdentityResetRequest):
        return data_response(context.identity_preparations.retry_cleanup(preparation_id).model_dump(mode='json'))

    return router
