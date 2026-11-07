"""业务场景只读/修订接口；目标操作统一提交既有 CHECK Job。"""
from fastapi import APIRouter,Request
from starlette.concurrency import run_in_threadpool
from product.backend.interfaces.http.body import read_bounded_body
from pydantic import ValidationError
from product.backend.domain.errors import ErrorCode,JiejianError
from product.backend.interfaces.http.envelope import ApiResponse,data_response
from product.protocols.checks.scenarios import BusinessScenarioRevision


def build_business_scenarios_router(context):
    router=APIRouter()

    @router.get('/api/projects/{project_id}/business-scenarios',response_model=ApiResponse)
    def listing(project_id:str):
        return data_response(context.business_scenarios.listing(project_id))

    @router.get('/api/projects/{project_id}/business-scenarios/context',response_model=ApiResponse)
    def preparation(project_id:str):
        return data_response(context.business_scenarios.context(project_id))

    @router.get('/api/projects/{project_id}/business-scenarios/{scenario_id}/{revision}',response_model=ApiResponse)
    def read(project_id:str,scenario_id:str,revision:int):
        return data_response(context.business_scenarios.read(project_id,scenario_id,revision).model_dump(mode='json'))

    @router.put('/api/projects/{project_id}/business-scenarios',response_model=ApiResponse)
    async def save(project_id:str,request:Request):
        raw=await read_bounded_body(request,limit=262144,message='业务场景超出大小限制')
        try:
            document=BusinessScenarioRevision.model_validate_json(raw)
        except ValidationError:
            raise JiejianError(ErrorCode.INPUT_INVALID,'请核对实验顺序、准确权限及批量输入位置') from None
        result=await run_in_threadpool(context.business_scenarios.save,project_id,document)
        return data_response(result.model_dump(mode='json'))

    return router
