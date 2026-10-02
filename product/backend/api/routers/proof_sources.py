# GUI证明准备入口：既受app.py统一中间件保护，也显式要求当前本机会话和写请求同源校验。
from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Literal
from product.backend.api.envelope import ApiResponse, data_response
from product.backend.workflows.preparation.proof_commands import SaveProofSource,StartProofPreflight,GrantProofScope,AdoptProofSource,CancelProofPreflight,RevokeProofScope


async def require_local_proof_session(request: Request):
    """拒绝脱离主应用安全门单独挂载的路由；API写入只接受GUI会话，不接受MCP凭据。"""
    guard = getattr(request.app.state,'local_control_guard',None)
    if guard is None or not guard.authorize(request).allowed:
        raise HTTPException(status_code=403, detail='本地控制请求未通过当前实例校验')


def build_proof_sources_router(context):
    router = APIRouter(prefix='/api/projects/{project_id}/proof-preparation',
        dependencies=[Depends(require_local_proof_session)])
    service = context.proof_preparation

    @router.get('',response_model=ApiResponse)
    async def preparation_context(project_id:str):
        return data_response(service.context(project_id))

    @router.post('/sources',response_model=ApiResponse)
    async def save_source(project_id:str,body:SaveProofSource):
        return data_response(service.save(project_id,body))

    @router.get('/sources/{source_id}',response_model=ApiResponse)
    async def source_show(project_id:str,source_id:str):
        return data_response(service.show(project_id,source_id))

    @router.post('/read-scopes',response_model=ApiResponse)
    async def grant_scope(project_id:str,body:GrantProofScope):
        return data_response(service.grant_scope(project_id,body))

    @router.post('/read-scopes/revoke',response_model=ApiResponse)
    async def revoke_scope(project_id:str,body:RevokeProofScope):
        return data_response(service.revoke_scope(project_id,body))

    @router.post('/preflights',response_model=ApiResponse)
    async def start_preflight(project_id:str,body:StartProofPreflight):
        return data_response(service.start(project_id,body))

    @router.get('/preflights/{preflight_id}',response_model=ApiResponse)
    async def preflight_status(project_id:str,preflight_id:str):
        return data_response(service.status(project_id,preflight_id))

    @router.post('/preflights/cancel',response_model=ApiResponse)
    async def cancel_preflight(project_id:str,body:CancelProofPreflight):
        return data_response(service.cancel(project_id,body))

    @router.get('/sources/{source_id}/adoption-preview',response_model=ApiResponse)
    async def adoption_preview(project_id:str,source_id:str,preflight_id:str):
        return data_response(service.adoption_preview(project_id,source_id,preflight_id))

    @router.post('/adoptions',response_model=ApiResponse)
    async def adopt_source(project_id:str,body:AdoptProofSource):
        return data_response(service.adopt(project_id,body))

    @router.get('/receipts/{kind}/{operation_id}',response_model=ApiResponse)
    async def receipt(project_id:str,kind:Literal['SAVE_SOURCE','GRANT_SCOPE','REVOKE_SCOPE','START_PREFLIGHT','CANCEL_PREFLIGHT','ADOPT_SOURCE'],operation_id:str):
        return data_response(service.receipt(project_id,kind,operation_id))

    return router
