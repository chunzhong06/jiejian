# 八个有限MCP准备工具：可保存候选和预检查，读取授权与采用仍只能由本机GUI确认。
import json
from typing import Any, Literal
from mcp.server.mcpserver import Context
from product.backend.workflows.agent_access.service import MCPAccessLevel
from product.backend.workflows.preparation.proof_commands import SaveProofSource,StartProofPreflight,CancelProofPreflight


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

    @server.tool(name='jiejian_preparation_context',structured_output=True)
    def preparation_context(ctx:Context, project_id:str)->dict[str,Any]:
        """读取可复用动作、账号、资源与来源缺口；只读，不访问目标。"""
        require_level(access,ctx,MCPAccessLevel.READ,project_id=project_id)
        value = invoke(lambda:context.preparation_guidance.context(project_id))
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
        return public_preparation(invoke(lambda:service.save(project_id,
            SaveProofSource.model_validate_json(json.dumps(candidate,allow_nan=False)),submitted_via='MCP',
            client_name=(client_name() or 'MCP Agent')[:80])))

    @server.tool(name='jiejian_proof_source_show',structured_output=True)
    def source_show(ctx:Context,project_id:str,source_id:str)->dict[str,Any]:
        require_level(access,ctx,MCPAccessLevel.READ,project_id=project_id)
        return public_preparation(invoke(lambda:service.show(project_id,source_id)))

    @server.tool(name='jiejian_proof_preflight_start',structured_output=True)
    def preflight_start(ctx:Context,project_id:str,request:dict[str,Any])->dict[str,Any]:
        """在既有GUI读取授权内排队预检查；不执行TARGET或恢复，不产生权限结论。"""
        require_level(access,ctx,MCPAccessLevel.EXECUTE,project_id=project_id)
        return public_preparation(invoke(lambda:service.start(project_id,
            StartProofPreflight.model_validate_json(json.dumps(request,allow_nan=False)),
            authority_id=access.execution_authority(project_id))))

    @server.tool(name='jiejian_proof_preflight_status',structured_output=True)
    def preflight_status(ctx:Context,project_id:str,preflight_id:str)->dict[str,Any]:
        require_level(access,ctx,MCPAccessLevel.READ,project_id=project_id)
        return public_preparation(invoke(lambda:service.status(project_id,preflight_id)))

    @server.tool(name='jiejian_proof_preflight_cancel',structured_output=True)
    def preflight_cancel(ctx:Context,project_id:str,preflight_id:str,operation_id:str)->dict[str,Any]:
        require_level(access,ctx,MCPAccessLevel.EXECUTE,project_id=project_id)
        return public_preparation(invoke(lambda:service.cancel(project_id,
            CancelProofPreflight(operation_id=operation_id,preflight_id=preflight_id))))

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
