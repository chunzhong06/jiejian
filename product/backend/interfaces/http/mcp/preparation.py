# 有限MCP准备工具：可保存材料建议、来源和预检查，读取授权与采用仍只能由本机GUI确认。
import json
from typing import Any, Literal
from mcp.server.mcpserver import Context
from product.backend.application.agent_access.service import MCPAccessLevel
from product.backend.application.preparation.proofs.commands import SaveProofSource, StartProofPreflight, CancelProofPreflight
from product.backend.domain.preparation.suggestions import SavePreparationSuggestion


def public_preparation(value):
    """只输出产品投影和不透明操作依据，不泄露执行fence、源码摘要或环境引用。"""
    hidden = {'request_fingerprint','source_fingerprint','binding_fingerprint','lease_owner','fencing_token','attempt',
        'control_session_id','authority_id','runtime_reference','identities','contract'}
    if isinstance(value,dict):
        return {key:public_preparation(item) for key,item in value.items() if key not in hidden}
    if isinstance(value,(tuple,list)):
        return [public_preparation(item) for item in value]
    return value


def register_preparation_tools(server, context, access, *, require_level, invoke, client_name):
    service = context.proof_preparation

    @server.tool(name='jiejian_preparation_batch_plan',structured_output=True)
    def batch_plan(ctx:Context, project_id:str, mode:Literal['OFFICIAL','REVIEWED']='REVIEWED')->dict[str,Any]:
        """只读固定材料清单；开始批次必须由用户在界鉴确认，MCP不能代为批准。"""
        require_level(access,ctx,MCPAccessLevel.READ,project_id=project_id)
        return invoke(lambda:context.preparation_batches.preview(project_id,mode).model_dump(mode='json'))

    @server.tool(name='jiejian_preparation_batch_status',structured_output=True)
    def batch_status(ctx:Context,project_id:str,operation_id:str|None=None)->dict[str,Any]:
        """续查已批准的后台批次；任务自动续行，BLOCKED必须回界鉴重新核对，不重发未知步骤。"""
        require_level(access,ctx,MCPAccessLevel.READ,project_id=project_id)
        return {'batch':invoke(lambda:context.preparation_batches.show(project_id,operation_id))}

    @server.tool(name='jiejian_preparation_batch_cancel',structured_output=True)
    def batch_cancel(ctx:Context,project_id:str,operation_id:str)->dict[str,Any]:
        """停止后续准备并等待本批子任务收口，保留已经形成的材料。"""
        require_level(access,ctx,MCPAccessLevel.EXECUTE,project_id=project_id)
        return invoke(lambda:context.preparation_batches.cancel(project_id,operation_id))

    @server.tool(name='jiejian_preparation_suggestion_save',structured_output=True)
    def suggestion_save(ctx:Context,project_id:str,suggestion:dict[str,Any])->dict[str,Any]:
        """保存五类材料的有限建议，不创建账号、执行代码、采用材料或宣称准备完成。"""
        require_level(access,ctx,MCPAccessLevel.PREPARE,project_id=project_id)
        command = invoke(lambda:SavePreparationSuggestion.model_validate_json(json.dumps(suggestion,allow_nan=False)),
            input_model=SavePreparationSuggestion,input_root='suggestion')
        return public_preparation(invoke(lambda:context.preparation_suggestions.save(project_id, command, submitted_via='MCP'),
            diagnostic_context={'tool':'preparation_suggestion_save','project_id':project_id}))

    @server.tool(name='jiejian_preparation_suggestion_show',structured_output=True)
    def suggestion_show(ctx:Context,project_id:str,suggestion_id:str,revision:int|None=None)->dict[str,Any]:
        require_level(access,ctx,MCPAccessLevel.READ,project_id=project_id)
        return public_preparation(invoke(lambda:context.preparation_suggestions.show(project_id,suggestion_id,revision)))

    @server.tool(name='jiejian_preparation_suggestion_receipt',structured_output=True)
    def suggestion_receipt(ctx:Context,project_id:str,operation_id:str)->dict[str,Any]:
        """建议保存响应未知时查询原键；UNKNOWN不能作为重新写入的依据。"""
        require_level(access,ctx,MCPAccessLevel.READ,project_id=project_id)
        return public_preparation(invoke(lambda:context.preparation_suggestions.receipt(project_id,operation_id)))

    @server.tool(name='jiejian_preparation_context',structured_output=True)
    def preparation_context(ctx:Context, project_id:str)->dict[str,Any]:
        """读取可复用动作、账号、资源与来源缺口；只读，不访问目标。"""
        require_level(access,ctx,MCPAccessLevel.READ,project_id=project_id)
        value = invoke(lambda:context.preparation_guidance.context(project_id), diagnostic_context={'tool':'preparation_context','project_id':project_id})
        # 身份列表只含界鉴账号ID和标签；不包含CheckIdentity或秘密引用。
        identities = value.pop('identities')
        return public_preparation(value) | {'available_identities':identities,
            'source_input_schema':SaveProofSource.model_json_schema(),
            'preflight_input_schema':StartProofPreflight.model_json_schema(),
            'next_step':value['guidance']['next_action'],
            'next_step_note':value['guidance']['note']}

    @server.tool(name='jiejian_proof_source_save',structured_output=True)
    def source_save(ctx:Context,project_id:str,candidate:dict[str,Any])->dict[str,Any]:
        """保存候选，不激活来源。响应未知时只按原operation_id查询回执。"""
        require_level(access,ctx,MCPAccessLevel.PREPARE,project_id=project_id)
        command = invoke(lambda:SaveProofSource.model_validate_json(json.dumps(candidate,allow_nan=False)),input_model=SaveProofSource)
        return public_preparation(invoke(lambda:service.save(project_id, command,submitted_via='MCP',
            client_name=(client_name() or 'MCP Agent')[:80])))

    @server.tool(name='jiejian_proof_source_show',structured_output=True)
    def source_show(ctx:Context,project_id:str,source_id:str)->dict[str,Any]:
        require_level(access,ctx,MCPAccessLevel.READ,project_id=project_id)
        return public_preparation(invoke(lambda:service.show(project_id,source_id)))

    @server.tool(name='jiejian_proof_preflight_start',structured_output=True)
    def preflight_start(ctx:Context,project_id:str,request:dict[str,Any])->dict[str,Any]:
        """在既有GUI读取授权内排队预检查；不执行TARGET或恢复，不产生权限结论。"""
        require_level(access,ctx,MCPAccessLevel.EXECUTE,project_id=project_id)
        command = invoke(lambda:StartProofPreflight.model_validate_json(json.dumps(request,allow_nan=False)),input_model=StartProofPreflight,input_root='request')
        return public_preparation(invoke(lambda:service.start(project_id, command,
            authority_id=access.execution_authority(project_id))))

    @server.tool(name='jiejian_proof_preflight_status',structured_output=True)
    def preflight_status(ctx:Context,project_id:str,preflight_id:str)->dict[str,Any]:
        require_level(access,ctx,MCPAccessLevel.READ,project_id=project_id)
        return public_preparation(invoke(lambda:service.status(project_id,preflight_id)))

    @server.tool(name='jiejian_proof_preflight_cancel',structured_output=True)
    def preflight_cancel(ctx:Context,project_id:str,preflight_id:str,operation_id:str)->dict[str,Any]:
        require_level(access,ctx,MCPAccessLevel.EXECUTE,project_id=project_id)
        command = invoke(lambda:CancelProofPreflight(operation_id=operation_id,preflight_id=preflight_id),input_model=CancelProofPreflight,input_root='request')
        return public_preparation(invoke(lambda:service.cancel(project_id, command)))

    @server.tool(name='jiejian_proof_adoption_preview',structured_output=True)
    def adoption_preview(ctx:Context,project_id:str,source_id:str,preflight_id:str)->dict[str,Any]:
        """只读查看采用影响与GUI入口；不能批准权限或采用来源。"""
        require_level(access,ctx,MCPAccessLevel.READ,project_id=project_id)
        return public_preparation(invoke(lambda:service.adoption_preview(project_id,source_id,preflight_id)))

    @server.tool(name='jiejian_preparation_receipt',structured_output=True)
    def receipt(ctx:Context,project_id:str,kind:Literal['SAVE_SOURCE','START_PREFLIGHT','CANCEL_PREFLIGHT'],operation_id:str)->dict[str,Any]:
        """未知写入仅查询原操作。未找到回执不能作为改用新键重发的依据。"""
        require_level(access,ctx,MCPAccessLevel.READ,project_id=project_id)
        return public_preparation(invoke(lambda:service.receipt(project_id,kind,operation_id)))
