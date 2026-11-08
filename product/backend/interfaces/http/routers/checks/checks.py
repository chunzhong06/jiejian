# 当前全部业务动作的只读检查预览，保留未准备动作及其缺口。
from fastapi import APIRouter, Query
from pydantic import Field

from product.backend.interfaces.http.envelope import ApiModel, ApiResponse, data_response
from product.backend.bootstrap import ApplicationCore
from product.protocols.checks.execution_request import PermissionReference
from product.backend.application.checks.routines import SaveCheckRoutine
from product.backend.application.checks.service import ExternalRecheckCommand
from product.protocols.checks.scenarios import ScenarioReference
from product.protocols.checks.routine_reference import RoutineReference
from product.backend.application.checks.routine_execution import SaveRoutineRevision, BindRoutine


class CheckScopeRequest(ApiModel):
    selected_permissions: list[PermissionReference] | None = Field(default=None,min_length=1,max_length=4096)
    scenario: ScenarioReference | None = None
    routine: RoutineReference | None = None


def build_checks_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.post('/api/projects/{project_id}/external-recheck-preview',response_model=ApiResponse)
    def external_preview(project_id:str,body:ExternalRecheckCommand):
        return data_response(context.checks.preview(project_id,external_recheck=body))

    @router.get('/api/projects/{project_id}/check-routines', response_model=ApiResponse)
    def routines(project_id: str):
        return data_response(context.check_routines.list(project_id))

    @router.get('/api/projects/{project_id}/check-comparison', response_model=ApiResponse)
    def comparison(project_id: str, baseline: str = Query(...,pattern=r'^run_[0-9a-f]{32}$'),
        current: str = Query(...,pattern=r'^run_[0-9a-f]{32}$'), earlier: str | None = Query(None,pattern=r'^run_[0-9a-f]{32}$'),
        after: str | None = Query(None,pattern=r'^[0-9a-f]{64}$'), limit: int = Query(25,ge=1,le=50)):
        return data_response(context.check_comparison.compare(project_id,baseline,current,earlier=earlier,after=after,limit=limit))

    @router.get('/api/projects/{project_id}/check-comparison/{key}', response_model=ApiResponse)
    def comparison_detail(project_id: str, key: str, baseline: str = Query(...,pattern=r'^run_[0-9a-f]{32}$'),
        current: str = Query(...,pattern=r'^run_[0-9a-f]{32}$')):
        return data_response(context.check_comparison.detail(project_id,baseline,current,key))

    @router.get('/api/projects/{project_id}/check-routines/catalog', response_model=ApiResponse)
    def routine_catalog(project_id: str, after: str | None = Query(None, pattern=r'^csp_[0-9a-f]{32}$'),
        limit: int = Query(50, ge=1, le=50)):
        return data_response(context.check_routines.revisions.catalog(project_id, after, limit))

    @router.post('/api/projects/{project_id}/check-routines/revisions', response_model=ApiResponse)
    def save_routine_revision(project_id: str, body: SaveRoutineRevision):
        return data_response(context.check_routines.revisions.save(project_id, body))

    @router.get('/api/projects/{project_id}/check-routines/{routine_id}/revisions', response_model=ApiResponse)
    def routine_history(project_id: str, routine_id: str, before: int | None = None):
        return data_response(context.check_routines.revisions.history(project_id, routine_id, before))

    @router.get('/api/projects/{project_id}/check-routines/{routine_id}/revisions/{revision}', response_model=ApiResponse)
    def read_routine_revision(project_id: str, routine_id: str, revision: int):
        return data_response(context.check_routines.revisions.read(project_id, routine_id, revision))

    @router.get('/api/projects/{project_id}/check-routines/{routine_id}/binding-preview', response_model=ApiResponse)
    def routine_binding_preview(project_id: str, routine_id: str, revision: int):
        return data_response(context.check_routines.revisions.binding_preview(project_id, routine_id, revision))

    @router.get('/api/projects/{project_id}/check-routines/{routine_id}/bindings', response_model=ApiResponse)
    def routine_bindings(project_id: str, routine_id: str, revision: int):
        return data_response(context.check_routines.revisions.bindings(project_id, routine_id, revision))

    @router.post('/api/projects/{project_id}/check-routines/{routine_id}/bindings', response_model=ApiResponse)
    def bind_routine(project_id: str, routine_id: str, body: BindRoutine):
        return data_response(context.check_routines.revisions.bind(project_id, routine_id, body))

    @router.get('/api/projects/{project_id}/check-routines/{routine_id}/requests/{operation_id}', response_model=ApiResponse)
    def routine_request(project_id: str, routine_id: str, operation_id: str, revision: int, binding_id: str, fingerprint: str):
        reference = RoutineReference(routine_id=routine_id, revision=revision, binding_id=binding_id)
        result = context.checks.routine_receipt(project_id, reference, fingerprint, operation_id)
        return data_response(None if result is None else context.check_results.status(result.run.run_id, project_id=project_id))

    @router.post('/api/projects/{project_id}/check-routines', response_model=ApiResponse)
    def save_routine(project_id: str, body: SaveCheckRoutine):
        return data_response(context.check_routines.save(project_id, body))

    @router.delete('/api/projects/{project_id}/check-routines/{routine_id}', response_model=ApiResponse)
    def delete_routine(project_id: str, routine_id: str):
        context.check_routines.delete(project_id, routine_id)
        return data_response({'deleted': True})

    @router.get("/api/projects/{project_id}/check-preview", response_model=ApiResponse)
    def check_preview(project_id: str, change_id: str | None = None):
        return data_response(context.checks.preview(project_id,change_id=change_id).model_dump(mode="json"))

    @router.post("/api/projects/{project_id}/check-preview", response_model=ApiResponse)
    def selected_preview(project_id: str, body: CheckScopeRequest):
        if body.selected_permissions is None and body.scenario is None and body.routine is None:
            from product.backend.domain.errors import ErrorCode,JiejianError
            raise JiejianError(ErrorCode.INPUT_INVALID,'请选择规则范围或业务场景')
        return data_response(context.checks.preview(project_id,selected_permissions=None if body.selected_permissions is None else tuple(body.selected_permissions),
            scenario_reference=body.scenario, routine_reference=body.routine).model_dump(mode="json"))

    return router
