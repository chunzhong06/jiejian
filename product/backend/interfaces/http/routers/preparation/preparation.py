# 投影动作准备只读真源并接受有限 ALLOW 技术选择，不修改权限或运行检查。

from fastapi import APIRouter,Request
from product.protocols.preparation.operation_flow import OperationFlow
from product.backend.domain.errors import ErrorCode,JiejianError
from product.backend.interfaces.http.envelope import ApiResponse, data_response
from product.backend.interfaces.http.envelope import ApiModel
from product.backend.domain.preparation.requirements import PermissionIdentity
from pydantic import Field
from typing import Literal
from product.backend.application.preparation.materials.models import MaterialChange, MaterialReference, PreparationDraft
from product.backend.application.preparation.models import RuleCaseDataSelection


class AllowControlSelectionRequest(ApiModel):
    schema_version: Literal["1"]
    deny_permission: PermissionIdentity
    selected_allow_permission: PermissionIdentity
    expected_selection_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


def build_preparation_router(context) -> APIRouter:
    router = APIRouter()
    from product.backend.interfaces.http.routers.preparation.flow_trials import build_flow_trials_router
    router.include_router(build_flow_trials_router(context))
    from product.backend.interfaces.http.routers.preparation.proof_sources import build_proof_sources_router
    router.include_router(build_proof_sources_router(context))

    @router.get('/api/projects/{project_id}/preparation/rule-data', response_model=ApiResponse)
    def rule_case_data(project_id: str):
        return data_response(context.preparation.case_data(project_id))

    @router.put('/api/projects/{project_id}/preparation/rule-data', response_model=ApiResponse)
    def select_rule_case_data(project_id: str, body: RuleCaseDataSelection):
        return data_response(context.preparation.bind_case_data(project_id, **{
            **body.model_dump(exclude={'permission'}), 'permission': body.permission}))

    @router.post('/api/projects/{project_id}/operation-flows/candidate',response_model=ApiResponse)
    async def operation_candidate(project_id:str,request:Request):
        from product.protocols.preparation.operation_flow import OperationFlowDraft
        from pydantic import ValidationError
        raw=await request.body()
        if len(raw)>262144:raise JiejianError(ErrorCode.INPUT_INVALID,'流程超出大小限制')
        try:draft=OperationFlowDraft.model_validate_json(raw,strict=True)
        except ValidationError:raise JiejianError(ErrorCode.INPUT_INVALID,'请核对步骤、动态值和恢复位置') from None
        return data_response(context.operation_flows.candidate(project_id,draft).model_dump(mode='json'))

    @router.get('/api/projects/{project_id}/operation-flows',response_model=ApiResponse)
    def operation_flows(project_id:str):
        return data_response(context.operation_flows.context(project_id))

    @router.get('/api/projects/{project_id}/operation-flows/{flow_id}/{revision}',response_model=ApiResponse)
    def operation_flow_revision(project_id:str,flow_id:str,revision:int):
        return data_response(context.operation_flows.read(project_id,flow_id,revision).model_dump(mode='json'))

    @router.put('/api/projects/{project_id}/operation-flows',response_model=ApiResponse)
    async def save_operation_flow(project_id:str,request:Request):
        from product.backend.interfaces.http.routers.preparation.proof_sources import json_command
        from pydantic import ValidationError
        raw=await request.body()
        if len(raw)>262144:raise JiejianError(ErrorCode.INPUT_INVALID,'操作流程超出大小限制')
        try:document=OperationFlow.model_validate_json(raw,strict=True)
        except ValidationError:raise JiejianError(ErrorCode.INPUT_INVALID,'请核对操作步骤、资源位置与动态值来源') from None
        return data_response(context.operation_flows.save(project_id,document).model_dump(mode='json'))

    @router.post('/api/projects/{project_id}/operation-flows/{flow_id}/{revision}/adopt',response_model=ApiResponse)
    def adopt_operation_flow(project_id:str,flow_id:str,revision:int):
        return data_response(context.operation_flows.adopt(project_id,flow_id,revision))

    @router.get('/api/projects/{project_id}/operation-flows/recording/{recording_id}',response_model=ApiResponse)
    def recording_candidate(project_id:str,recording_id:str):
        return data_response(context.operation_flows.recording_candidate(project_id,recording_id))

    @router.post('/api/projects/{project_id}/operation-flows/openapi',response_model=ApiResponse)
    async def import_openapi(project_id:str,request:Request):
        import json
        context.operation_flows.context(project_id)
        raw=await request.body()
        if len(raw)>1048576:raise JiejianError(ErrorCode.INPUT_INVALID,'接口文档超出大小限制')
        try:document=json.loads(raw)
        except (ValueError,UnicodeError):raise JiejianError(ErrorCode.INPUT_INVALID,'请选择 JSON 格式的接口文档') from None
        return data_response(context.operation_flows.openapi_candidates(document))

    @router.get("/api/projects/{project_id}/preparation/materials/{action_id}/{kind}", response_model=ApiResponse)
    def material_details(project_id: str, action_id: str, kind: Literal["execution", "resource", "evidence", "recovery"], action_revision: int, member_id: str | None = None):
        ref = MaterialReference(action_id=action_id, action_revision=action_revision, kind=kind, member_id=member_id)
        return data_response(context.preparation_materials.details(project_id, ref))

    @router.post("/api/projects/{project_id}/preparation/changes/preview", response_model=ApiResponse)
    def preview_material(project_id: str, body: MaterialChange):
        return data_response(context.preparation_materials.preview(project_id, body))

    @router.post("/api/projects/{project_id}/preparation/changes", response_model=ApiResponse)
    def save_material(project_id: str, body: MaterialChange):
        return data_response(context.preparation_materials.apply(project_id, body))

    @router.get("/api/projects/{project_id}/preparation/changes/{operation_id}", response_model=ApiResponse)
    def material_receipt(project_id: str, operation_id: str):
        return data_response(context.preparation_materials.receipt(project_id, operation_id))

    @router.get("/api/projects/{project_id}/preparation/draft", response_model=ApiResponse)
    def preparation_draft(project_id: str):
        return data_response(context.preparation_materials.draft(project_id))

    @router.put("/api/projects/{project_id}/preparation/draft", response_model=ApiResponse)
    def save_preparation_draft(project_id: str, body: PreparationDraft):
        return data_response(context.preparation_materials.save_draft(project_id, body))

    @router.get("/api/projects/{project_id}/preparation", response_model=ApiResponse)
    def get_preparation(project_id: str):
        return data_response(context.preparation.get(project_id).model_dump(mode="json"))

    @router.get("/api/projects/{project_id}/preparation/evidence/{action_id}", response_model=ApiResponse)
    def get_evidence_details(project_id: str, action_id: str):
        return data_response(context.preparation.evidence_details(project_id, action_id).model_dump(mode="json"))

    @router.post("/api/projects/{project_id}/preparation/allow-control", response_model=ApiResponse)
    def select_allow_control(project_id: str, body: AllowControlSelectionRequest):
        # 外层 LocalControlGuard 对全部写请求实施当前会话与精确 Origin 防护。
        binding = context.preparation.select_allow_control(
            project_id, deny_permission=body.deny_permission,
            selected_allow_permission=body.selected_allow_permission,
            expected_selection_fingerprint=body.expected_selection_fingerprint,
        )
        return data_response(binding.model_dump(mode="json"))

    return router
