# 当前代码变化登记与只读查询 API；来源固定本机 GUI，业务服务重扫并核对项目归属。

from __future__ import annotations
from typing import Literal

from fastapi import APIRouter, Query

from pydantic import Field
from product.backend.api.envelope import ApiModel, ApiResponse, data_response
from product.backend.core.checks.repair import CurrentRepairReference
from product.backend.core.development import ContextId, OperationId, TaskId
from product.protocols.checks.execution_request import Hash
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.composition import ApplicationCore


class SourceChangeCreateRequest(ApiModel):
    schema_version: Literal["2"]
    task_id: TaskId
    context_id: ContextId
    operation_id: OperationId
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1,max_length=512)
    claimed_paths: list[str] = Field(default_factory=list,max_length=128)
    repair_reference: CurrentRepairReference | None = None


class SourceChangeRegistrationRequest(ApiModel):
    schema_version: Literal["1"]
    operation_id: OperationId
    expected_registration_fingerprint: Hash
    reason: str = Field(default="本地源码修改", min_length=1, max_length=512)
    claimed_paths: list[str] = Field(default_factory=list, max_length=128)
    repair_reference: CurrentRepairReference | None = None


def build_source_changes_router(context: ApplicationCore) -> APIRouter:
    """本机 GUI 登记变化声明，业务服务自行重扫；读取始终按项目核对归属。"""

    router = APIRouter()

    @router.get("/api/projects/{project_id}/source-changes/registration-preview", response_model=ApiResponse)
    def registration_preview(project_id: str):
        return data_response(context.development.registration_preview(project_id))

    @router.post("/api/projects/{project_id}/source-changes/register", response_model=ApiResponse, status_code=201)
    def register_change(project_id: str, body: SourceChangeRegistrationRequest):
        receipt = context.development.register_change(project_id, operation_id=body.operation_id,
            expected_registration_fingerprint=body.expected_registration_fingerprint, reason=body.reason,
            claimed_paths=body.claimed_paths, repair_reference=body.repair_reference, submitted_by="LOCAL_GUI")
        return data_response(receipt.model_dump(mode="json"), status_code=201)

    @router.get("/api/projects/{project_id}/source-changes/{change_id}/source-identity", response_model=ApiResponse)
    def change_source_identity(project_id: str, change_id: str):
        return data_response(context.source_identity.for_change(project_id, change_id).model_dump(mode="json"))

    @router.get("/api/projects/{project_id}/runs/{run_id}/source-identity", response_model=ApiResponse)
    def run_source_identity(project_id: str, run_id: str):
        return data_response(context.source_identity.for_run(project_id, run_id).model_dump(mode="json"))

    @router.post("/api/projects/{project_id}/source-changes",response_model=ApiResponse,status_code=201)
    def create_source_change(project_id: str, body: SourceChangeCreateRequest):
        view = context.development.deliver(project_id, body.task_id, context_id=body.context_id,
            operation_id=body.operation_id, expected_version=body.expected_version,
            reason=body.reason,claimed_paths=body.claimed_paths, repair_reference=body.repair_reference,submitted_by="LOCAL_GUI")
        return data_response(view.model_dump(mode="json"),status_code=201)

    @router.get("/api/projects/{project_id}/repair",response_model=ApiResponse)
    def project_repair(project_id: str):
        return data_response(context.project_repair.evaluate(project_id).model_dump(mode="json"))

    @router.get(
        "/api/projects/{project_id}/source-changes",
        response_model=ApiResponse,
    )
    async def source_change_list(
        project_id: str,
        limit: int = Query(default=50, ge=1, le=100),
    ):
        views = context.source_changes.list(project_id, limit=limit)
        return data_response([view.model_dump(mode="json") for view in views])

    @router.get(
        "/api/projects/{project_id}/source-changes/latest",
        response_model=ApiResponse,
    )
    async def latest_source_change(project_id: str):
        latest = context.source_changes.latest(project_id)
        return data_response(None if latest is None else latest.model_dump(mode="json"))

    @router.get(
        "/api/projects/{project_id}/source-changes/{change_id}",
        response_model=ApiResponse,
    )
    async def source_change(project_id: str, change_id: str):
        view = context.source_changes.view(project_id,change_id)
        return data_response(view.model_dump(mode="json"))

    return router
