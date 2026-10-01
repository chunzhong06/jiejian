# 本机 GUI 的轻量开发任务入口；接收回执只由真实客户端操作产生，结束不等于检查通过。
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import Field

from product.backend.api.envelope import ApiModel, ApiResponse, data_response
from product.backend.core.development import OperationId, OperationKind


class TaskCreateRequest(ApiModel):
    schema_version: Literal["1"]
    operation_id: OperationId
    expected_version: Literal[0] = 0
    title: str = Field(min_length=1, max_length=120)
    goal: str = Field(min_length=1, max_length=4000)


class TaskReviseRequest(ApiModel):
    schema_version: Literal["1"]
    operation_id: OperationId
    expected_version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=120)
    goal: str = Field(min_length=1, max_length=4000)


class TaskFinishRequest(ApiModel):
    schema_version: Literal["1"]
    operation_id: OperationId
    expected_version: int = Field(ge=1)
    action: Literal["CLOSE", "CANCEL"]


class RuntimeLoadRequest(ApiModel):
    schema_version: Literal["1"]
    operation_id: OperationId
    expected_version: int = Field(ge=1)


def build_development_router(context):
    router = APIRouter()
    service = context.development

    @router.get("/api/projects/{project_id}/development/history", response_model=ApiResponse)
    def task_history(project_id: str, before_task_id: str | None = None, limit: int = Query(default=20, ge=1, le=50)):
        return data_response(service.history(project_id, before_task_id=before_task_id, limit=limit))

    @router.get("/api/projects/{project_id}/development/tasks/{task_id}/deliveries", response_model=ApiResponse)
    def task_deliveries(project_id: str, task_id: str, before_ordinal: int | None = Query(default=None, ge=1), limit: int = Query(default=20, ge=1, le=50)):
        return data_response(service.delivery_page(project_id, task_id, before_ordinal=before_ordinal, limit=limit))

    @router.get("/api/projects/{project_id}/development/changes/{change_id}", response_model=ApiResponse)
    def delivery_details(project_id: str, change_id: str):
        return data_response(service.delivery_details(project_id, change_id))

    @router.get("/api/projects/{project_id}/development/tasks", response_model=ApiResponse)
    def task_list(project_id: str, limit: int = Query(default=50, ge=1, le=100)):
        return data_response([item.model_dump(mode="json") for item in service.list(project_id, limit=limit)])

    @router.get("/api/projects/{project_id}/development/current", response_model=ApiResponse)
    def current_task(project_id: str):
        value = service.active(project_id)
        return data_response(None if value is None else service.view(project_id, value.task_id))

    @router.post("/api/projects/{project_id}/development/tasks", response_model=ApiResponse, status_code=201)
    def task_create(project_id: str, body: TaskCreateRequest):
        result = service.create(project_id, **body.model_dump(exclude={"schema_version"}))
        return data_response(result.model_dump(mode="json"), status_code=201)

    @router.get("/api/projects/{project_id}/development/tasks/{task_id}", response_model=ApiResponse)
    def task_show(project_id: str, task_id: str):
        return data_response(service.view(project_id, task_id))

    @router.post("/api/projects/{project_id}/development/tasks/{task_id}/revisions", response_model=ApiResponse)
    def task_revise(project_id: str, task_id: str, body: TaskReviseRequest):
        result = service.revise(project_id, task_id, **body.model_dump(exclude={"schema_version"}))
        return data_response(result.model_dump(mode="json"))

    @router.post("/api/projects/{project_id}/development/tasks/{task_id}/finish", response_model=ApiResponse)
    def task_finish(project_id: str, task_id: str, body: TaskFinishRequest):
        result = service.finish(project_id, task_id, operation_id=body.operation_id,
            expected_version=body.expected_version, cancel=body.action == "CANCEL")
        return data_response(result.model_dump(mode="json"))

    @router.get("/api/projects/{project_id}/development/receipts/{kind}/{operation_id}", response_model=ApiResponse)
    def receipt_show(project_id: str, kind: OperationKind, operation_id: OperationId):
        receipt = service.receipt(project_id, kind, operation_id)
        return data_response(None if receipt is None else receipt.model_dump(mode="json"))

    @router.post("/api/projects/{project_id}/development/deliveries/{delivery_id}/runtime", response_model=ApiResponse)
    def runtime_load(project_id: str, delivery_id: str, body: RuntimeLoadRequest):
        result = context.runtime_activation.activate(project_id, delivery_id, operation_id=body.operation_id, expected_version=body.expected_version)
        return data_response(result.model_dump(mode="json"))

    @router.get("/api/projects/{project_id}/development/deliveries/{delivery_id}", response_model=ApiResponse)
    def delivery_show(project_id: str, delivery_id: str):
        return data_response(service.delivery_verification(project_id, delivery_id))

    @router.get("/api/projects/{project_id}/development/runtime-operations/{operation_id}", response_model=ApiResponse)
    def runtime_receipt(project_id: str, operation_id: OperationId):
        result = context.runtime_activation.receipt(project_id, operation_id)
        return data_response(None if result is None else result.model_dump(mode="json"))

    return router
