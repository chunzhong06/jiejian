# 当前检查提交与状态接口；只接受冻结计划指纹，执行及发布由独立 Worker 承担。
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, Request, HTTPException, Depends
from pydantic import Field

from product.backend.interfaces.http.envelope import ApiModel, ApiResponse, data_response
from product.backend.bootstrap import ApplicationCore
from product.backend.domain.identifiers import RUN_ID_PATTERN
from product.backend.domain.lifecycle import RunLifecycle, RunVerdict
from product.backend.domain.errors import ErrorCode,JiejianError
from product.backend.application.checks.history import MaintainHistory
from product.protocols.checks.execution_request import PermissionReference
from product.backend.application.checks.service import ExternalRecheckCommand
from product.protocols.checks.scenarios import ScenarioReference
from product.protocols.checks.routine_reference import RoutineReference
from product.backend.application.checks.reading.results import CheckRunStatus, CheckRunView, CheckJobView, CheckHistoryPage, CheckContinuation


class RunSubmissionProjection(ApiModel):
    run: CheckRunView
    job: CheckJobView


async def require_local_history_session(request:Request):
    guard=getattr(request.app.state,'local_control_guard',None)
    if guard is None or not guard.authorize(request).allowed:raise HTTPException(status_code=403,detail='历史整理需要当前本机控制会话')


class RunCreateRequest(ApiModel):
    schema_version: Literal["2"]
    expected_plan_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=128)
    change_id: str | None = Field(default=None,pattern=r"^chg_[0-9a-f]{32}$")
    selected_permissions: list[PermissionReference] | None = Field(default=None, min_length=1, max_length=4096)
    external_recheck: ExternalRecheckCommand | None = None
    scenario: ScenarioReference | None = None
    routine: RoutineReference | None = None


def build_runs_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.post("/api/projects/{project_id}/runs", response_model=ApiResponse[RunSubmissionProjection], status_code=202)
    def create_run(project_id: str, body: RunCreateRequest):
        submitted = context.checks.submit(project_id, expected_plan_fingerprint=body.expected_plan_fingerprint,
            idempotency_key=body.idempotency_key,change_id=body.change_id,
            selected_permissions=None if body.selected_permissions is None else tuple(body.selected_permissions),external_recheck=body.external_recheck,
            scenario_reference=body.scenario, routine_reference=body.routine)
        status = context.check_results.status(submitted.run.run_id, project_id=project_id)
        return data_response(RunSubmissionProjection(run=status.run, job=status.job),
            projection=RunSubmissionProjection, status_code=202)

    @router.get("/api/projects/{project_id}/runs", response_model=ApiResponse)
    def list_runs(project_id: str, active_only: bool = False):
        if active_only:
            # 当前页只需要活动检查；历史通过已有分页入口严格读取，避免轮询全量旧包。
            active = context.check_results.active_for_project(project_id)
            return data_response([] if active is None else [active.model_dump(mode="json")])
        return data_response([item.model_dump(mode="json") for item in context.check_results.list_for_project(project_id)])

    @router.get('/api/projects/{project_id}/check-requests/{operation_id}', response_model=ApiResponse)
    def check_request(project_id: str, operation_id: str):
        with context.uow_factory() as work:
            job = work.jobs.get_by_idempotency(project_id, 'CHECK', operation_id)
        return data_response(None if job is None else context.check_results.status(job.run_id, project_id=project_id).model_dump(mode='json'))

    @router.get('/api/projects/{project_id}/runs/{run_id}/continuation', response_model=ApiResponse[CheckContinuation])
    def continuation(project_id: str, run_id: str):
        return data_response(context.check_results.continuation(project_id, run_id, repair_contracts=context.check_repairs.contracts), projection=CheckContinuation)

    @router.get("/api/projects/{project_id}/check-history", response_model=ApiResponse[CheckHistoryPage])
    def check_history(project_id: str, limit: int = Query(25, ge=1, le=50),
                      before_created_at_us: int | None = Query(None, ge=0),
                      before_run_id: str | None = Query(None, pattern=RUN_ID_PATTERN),
                      query: str | None = Query(None, max_length=128),
                      verdict: RunVerdict | None = None, lifecycle: RunLifecycle | None = None,
                      intent_id:str|None=Query(None,max_length=36),revision:int|None=Query(None,ge=1),intent_hash:str|None=Query(None,pattern=r'^[0-9a-f]{64}$')):
        parts=(intent_id,revision,intent_hash)
        if any(item is not None for item in parts) and not all(item is not None for item in parts):raise JiejianError(ErrorCode.INPUT_INVALID,'规则筛选需要准确的标识、修订和摘要')
        return data_response(context.check_results.history(project_id, limit=limit,
            before_created_at_us=before_created_at_us, before_run_id=before_run_id,
            query=query, verdict=verdict, lifecycle=lifecycle,rule_reference=parts if intent_id is not None else None), projection=CheckHistoryPage)

    @router.get('/api/projects/{project_id}/check-history/rules',response_model=ApiResponse)
    def history_rules(project_id:str,limit:int=Query(25,ge=1,le=50),after:str|None=Query(None,max_length=64),include_archived:bool=False):
        return data_response(context.check_history.rules(project_id,limit=limit,after=after,include_archived=include_archived))

    @router.get('/api/projects/{project_id}/check-history/index-status',response_model=ApiResponse)
    def history_index_status(project_id:str):return data_response(context.check_history.status(project_id))

    @router.post('/api/projects/{project_id}/check-history/index-maintenance',response_model=ApiResponse,dependencies=[Depends(require_local_history_session)])
    def history_index_maintenance(project_id:str,command:MaintainHistory):return data_response(context.check_history.maintain(project_id,command))

    @router.get('/api/projects/{project_id}/check-history/index-maintenance/{operation_id}',response_model=ApiResponse)
    def history_index_receipt(project_id:str,operation_id:str):return data_response(context.check_history.receipt(project_id,operation_id))

    @router.get("/api/runs/{run_id}", response_model=ApiResponse[CheckRunStatus])
    def get_run(run_id: str):
        return data_response(context.check_results.status(run_id), projection=CheckRunStatus)

    return router
