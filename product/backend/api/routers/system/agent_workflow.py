# 原Agent统一只读上下文；本机控制面会话由应用中间件核对。
from typing import Literal
from fastapi import APIRouter
from product.backend.api.envelope import ApiResponse, data_response


def build_agent_workflow_router(context):
    router = APIRouter()

    @router.get('/api/projects/{project_id}/agent-context', response_model=ApiResponse)
    def read(project_id: str, stage: Literal['RULES','MATERIALS','RECORDING','RESULTS','REPAIR']='RULES',
             recording_id: str|None=None, run_id: str|None=None, case_id: str|None=None):
        return data_response(context.agent_workflow.read(project_id,stage,recording_id=recording_id,run_id=run_id,case_id=case_id))

    return router
