# GUI证明准备入口：既受app.py统一中间件保护，也显式要求当前本机会话和写请求同源校验。
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
import json
from typing import Annotated,Literal
from product.backend.interfaces.http.envelope import ApiModel, ApiResponse, data_response
from pydantic import BeforeValidator,Field,ValidationError
from product.backend.domain.preparation.suggestions import SavePreparationSuggestion
from product.backend.application.preparation.proofs.commands import SaveProofSource, StartProofPreflight, GrantProofScope, AdoptProofSource, CancelProofPreflight, RevokeProofScope
from product.backend.application.preparation.proofs.artifact_inputs import UploadProofArtifact,CancelProofArtifact
from product.backend.application.preparation.proofs.capture_plan import CaptureSelection
from product.backend.application.preparation.proofs.capture_service import StartReferenceCapture,CancelReferenceCapture
from product.backend.domain.errors import ErrorCode,JiejianError
from product.backend.application.preparation.batches import StartPreparationBatch


async def require_local_proof_session(request: Request):
    """拒绝脱离主应用安全门单独挂载的路由；API写入只接受GUI会话，不接受MCP凭据。"""
    guard = getattr(request.app.state,'local_control_guard',None)
    if guard is None or not guard.authorize(request).allowed:
        raise HTTPException(status_code=403, detail='本地控制请求未通过当前实例校验')


class SavePreparationSuggestionRequest(ApiModel):
    operation_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    expected_basis_id: str = Field(pattern=r'^psb_[0-9a-f]{64}$')
    suggestion_id: str | None = Field(default=None, pattern=r'^psg_[0-9a-f]{32}$')
    expected_revision: int | None = Field(default=None, ge=1)
    content: dict[str,object]

    def to_command(self):
        return SavePreparationSuggestion.model_validate_json(self.model_dump_json())


def json_command(model):
    # HTTP数组按JSON语义进入冻结tuple；仍严格拒绝数字字符串、未知字段和无效嵌套值。
    def parse(value):
        if isinstance(value,model):return value
        return model.model_validate_json(json.dumps(value,allow_nan=False))
    return BeforeValidator(parse)


CaptureSelectionBody=Annotated[CaptureSelection,json_command(CaptureSelection)]
StartReferenceCaptureBody=Annotated[StartReferenceCapture,json_command(StartReferenceCapture)]
SaveProofSourceBody=Annotated[SaveProofSource,json_command(SaveProofSource)]


def build_proof_sources_router(context):
    router = APIRouter(prefix='/api/projects/{project_id}/proof-preparation',
        dependencies=[Depends(require_local_proof_session)])
    service = context.proof_preparation

    @router.post('/batches/preview', response_model=ApiResponse)
    def batch_preview(project_id: str, mode: Literal['OFFICIAL','REVIEWED']='REVIEWED'):
        return data_response(context.preparation_batches.preview(project_id, mode).model_dump(mode='json'))

    @router.post('/batches', response_model=ApiResponse, status_code=202)
    def batch_start(project_id: str, body: Annotated[StartPreparationBatch,json_command(StartPreparationBatch)]):
        return data_response(context.preparation_batches.start(project_id, body), status_code=202)

    @router.get('/batches/latest', response_model=ApiResponse)
    def batch_latest(project_id: str):
        return data_response(context.preparation_batches.show(project_id))

    @router.get('/batches/{operation_id}', response_model=ApiResponse)
    def batch_status(project_id: str, operation_id: str):
        return data_response(context.preparation_batches.show(project_id, operation_id))

    @router.post('/batches/{operation_id}/cancel', response_model=ApiResponse)
    def batch_cancel(project_id: str, operation_id: str):
        return data_response(context.preparation_batches.cancel(project_id, operation_id))

    @router.post('/reference-inputs',response_model=ApiResponse)
    async def upload_reference(project_id:str,request:Request):
        header=request.headers.get('x-jiejian-reference','')
        if len(header)>8192:raise JiejianError(ErrorCode.INPUT_INVALID,'参照文件信息超出限制')
        if request.headers.get('content-type','').split(';',1)[0].lower()!='application/octet-stream':
            raise JiejianError(ErrorCode.INPUT_INVALID,'请选择文件上传方式')
        try:command=UploadProofArtifact.model_validate_json(header,strict=True)
        except ValidationError:raise JiejianError(ErrorCode.INPUT_INVALID,'参照文件信息无效') from None
        content=bytearray()
        async for chunk in request.stream():
            if len(content)+len(chunk)>min(command.size,4194304):raise JiejianError(ErrorCode.INPUT_INVALID,'参照文件超出本次声明大小')
            content.extend(chunk)
        return data_response(await run_in_threadpool(context.proof_artifacts.upload,project_id,command,bytes(content)))

    @router.get('/reference-inputs/{asset_id}/file')
    def download_reference(project_id:str,asset_id:str):
        content=context.proof_artifacts.read(project_id,asset_id)
        # 保留固定安全文件名，并按内容标识给示例文件可直接打开的后缀。
        suffix='pdf' if content.startswith(b'%PDF-') else 'zip' if content.startswith(b'PK\x03\x04') else 'bin'
        return Response(content,media_type='application/octet-stream',
            headers={'Content-Disposition':f'attachment; filename="jiejian-reference.{suffix}"','X-Content-Type-Options':'nosniff','Cache-Control':'no-store'})

    @router.post('/reference-inputs/cancel',response_model=ApiResponse)
    def cancel_reference(project_id:str,body:CancelProofArtifact):
        return data_response(context.proof_artifacts.cancel(project_id,body))

    @router.post('/reference-captures/preview',response_model=ApiResponse)
    def preview_reference_capture(project_id:str,body:CaptureSelectionBody):
        return data_response(context.reference_captures.preview(project_id,body).model_dump(mode='json'))

    @router.post('/reference-captures',response_model=ApiResponse)
    def start_reference_capture(project_id:str,body:StartReferenceCaptureBody):
        return data_response(context.reference_captures.start(project_id,body))

    @router.get('/reference-captures/{capture_id}',response_model=ApiResponse)
    def reference_capture_status(project_id:str,capture_id:str):
        return data_response(context.reference_captures.status(project_id,capture_id))

    @router.post('/reference-captures/cancel',response_model=ApiResponse)
    def cancel_reference_capture(project_id:str,body:CancelReferenceCapture):
        return data_response(context.reference_captures.cancel(project_id,body))

    @router.post('/suggestions',response_model=ApiResponse)
    def save_suggestion(project_id:str,body:SavePreparationSuggestionRequest):
        return data_response(context.preparation_suggestions.save(project_id,body.to_command()))

    @router.get('/suggestions/{suggestion_id}',response_model=ApiResponse)
    def show_suggestion(project_id:str,suggestion_id:str,revision:int|None=None):
        return data_response(context.preparation_suggestions.show(project_id,suggestion_id,revision))

    @router.get('/suggestion-receipts/{operation_id}',response_model=ApiResponse)
    def suggestion_receipt(project_id:str,operation_id:str):
        return data_response(context.preparation_suggestions.receipt(project_id,operation_id))

    @router.get('',response_model=ApiResponse)
    def preparation_context(project_id:str,view:Literal['full','sources']='full'):
        # 来源页的轮询只读来源；完整 Agent 建议按需读取，避免反复重算整个工作区。
        return data_response(service.context(project_id) if view=='sources' else context.preparation_guidance.context(project_id))

    @router.post('/sources',response_model=ApiResponse)
    def save_source(project_id:str,body:SaveProofSourceBody):
        return data_response(service.save(project_id,body))

    @router.get('/sources/{source_id}',response_model=ApiResponse)
    def source_show(project_id:str,source_id:str):
        return data_response(service.show(project_id,source_id))

    @router.post('/read-scopes',response_model=ApiResponse)
    def grant_scope(project_id:str,body:GrantProofScope):
        return data_response(service.grant_scope(project_id,body))

    @router.post('/read-scopes/revoke',response_model=ApiResponse)
    def revoke_scope(project_id:str,body:RevokeProofScope):
        return data_response(service.revoke_scope(project_id,body))

    @router.post('/preflights',response_model=ApiResponse)
    def start_preflight(project_id:str,body:StartProofPreflight):
        return data_response(service.start(project_id,body))

    @router.get('/preflights/{preflight_id}',response_model=ApiResponse)
    def preflight_status(project_id:str,preflight_id:str):
        return data_response(service.status(project_id,preflight_id))

    @router.post('/preflights/cancel',response_model=ApiResponse)
    def cancel_preflight(project_id:str,body:CancelProofPreflight):
        return data_response(service.cancel(project_id,body))

    @router.get('/sources/{source_id}/adoption-preview',response_model=ApiResponse)
    def adoption_preview(project_id:str,source_id:str,preflight_id:str):
        return data_response(service.adoption_preview(project_id,source_id,preflight_id))

    @router.post('/adoptions',response_model=ApiResponse)
    def adopt_source(project_id:str,body:AdoptProofSource):
        return data_response(service.adopt(project_id,body))

    @router.get('/receipts/{kind}/{operation_id}',response_model=ApiResponse)
    def receipt(project_id:str,kind:Literal['SAVE_SOURCE','GRANT_SCOPE','REVOKE_SCOPE','START_PREFLIGHT','CANCEL_PREFLIGHT','ADOPT_SOURCE','UPLOAD_REFERENCE','CANCEL_REFERENCE','START_REFERENCE_CAPTURE','CANCEL_REFERENCE_CAPTURE'],operation_id:str):
        return data_response(service.receipt(project_id,kind,operation_id))

    return router
