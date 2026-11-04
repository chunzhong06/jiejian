"""只委托共同用例；HTTP处理器不执行目标请求。"""
from fastapi import APIRouter
from product.backend.application.preparation.flow_trials import TrialSelection,StartFlowTrial
from product.backend.interfaces.http.envelope import ApiResponse,data_response


def build_flow_trials_router(context):
    router=APIRouter(prefix='/api/projects/{project_id}/flow-trials')

    @router.post('/preview',response_model=ApiResponse)
    def preview(project_id:str,body:TrialSelection):
        return data_response(context.flow_trials.preview(project_id,body))

    @router.post('',response_model=ApiResponse)
    def start(project_id:str,body:StartFlowTrial):
        return data_response(context.flow_trials.start(project_id,body))

    @router.get('',response_model=ApiResponse)
    def history(project_id:str):
        return data_response(context.flow_trials.history(project_id))

    @router.get('/operations/{operation_id}',response_model=ApiResponse)
    def requested(project_id:str,operation_id:str):
        return data_response(context.flow_trials.requested(project_id,operation_id))

    @router.get('/{trial_id}',response_model=ApiResponse)
    def read(project_id:str,trial_id:str):
        return data_response(context.flow_trials.read(project_id,trial_id))

    @router.post('/{trial_id}/cancel',response_model=ApiResponse)
    def cancel(project_id:str,trial_id:str):
        return data_response(context.flow_trials.cancel(project_id,trial_id))

    return router
