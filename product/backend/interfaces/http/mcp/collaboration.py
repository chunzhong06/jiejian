from typing import Annotated, Any, Literal

from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations

from product.backend.application.agent_access.service import MCPAccessLevel
from product.backend.application.agent_access.tasks import (
    CreateCollaboration, CollaborationAction, CollaborationQuestion,
)

# 工具声明与实际命令共享约束，模型不必猜测操作和问题编号的格式。
OperationId = Annotated[str, CreateCollaboration.model_fields['operation_id']]
QuestionId = Annotated[str, CollaborationQuestion.model_fields['question_id']]


def register_collaboration_tools(server, core, access, *, require_level, invoke):
    """暴露有限产品命令；确认执行与业务批准不进入 MCP 工具参数。"""
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
    @server.tool(name='jiejian_collaboration_list', structured_output=True, annotations=read)
    def tasks(ctx: Context, project_id: str) -> dict[str, Any]:
        require_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        return dict(tasks=invoke(lambda: core.collaboration.list(project_id)))

    @server.tool(name='jiejian_collaboration_create', structured_output=True)
    def create(ctx: Context, project_id: str, operation_id: OperationId, goal: str,
        purpose: Literal['CHECK','CHECK_AND_REPAIR','REPAIR','SETUP','RULES','UNDERSTAND','MAINTENANCE']='CHECK',
        references: dict[str, str] | None=None) -> dict[str, Any]:
        require_level(access, ctx, MCPAccessLevel.PREPARE, project_id=project_id)
        command = invoke(lambda: CreateCollaboration(operation_id=operation_id, goal=goal, purpose=purpose, references=references or {}), input_model=CreateCollaboration, input_root='task')
        return invoke(lambda: core.collaboration.create(project_id, command))

    @server.tool(name='jiejian_collaboration_context', structured_output=True, annotations=read)
    def context(ctx: Context, project_id: str, task_id: str) -> dict[str, Any]:
        """读取贯穿接入、运行、账号、流程、证明、检查、修改和恢复的能力及参数。"""
        require_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        return invoke(lambda: core.collaboration.context(project_id, task_id))

    @server.tool(name='jiejian_collaboration_capability', structured_output=True, annotations=read)
    def capability(ctx: Context, project_id: str, key: str) -> dict[str, Any]:
        """按需读取当前动作参数，不在每轮重复发送全部能力的完整Schema。"""
        require_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        item = invoke(lambda: core.agent_capabilities.get(key))
        return dict(key=item.key, title=item.title, level=item.level, requires_review=item.approval,
            arguments=item.model.model_json_schema())

    @server.tool(name='jiejian_collaboration_read', structured_output=True, annotations=read)
    def read_capability(ctx: Context, project_id: str, task_id: str,
        capability: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """只读取能力目录中的既有事实；不能借只读标记登记写入或待审命令。"""
        require_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        return invoke(lambda: core.collaboration.read(project_id, task_id, capability, arguments))

    @server.tool(name='jiejian_collaboration_action', structured_output=True)
    def act(ctx: Context, project_id: str, task_id: str, operation_id: OperationId,
        capability: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """复用产品用例。需人的决定时只登记待审操作；不能借此批准或重放未知请求。"""
        item = invoke(lambda: core.agent_capabilities.get(capability))
        required = MCPAccessLevel.PREPARE if item.approval else MCPAccessLevel(item.level)
        require_level(access, ctx, required, project_id=project_id)
        command = invoke(lambda: CollaborationAction(operation_id=operation_id, capability=capability, arguments=arguments), input_model=CollaborationAction, input_root='action')
        return invoke(lambda: core.collaboration.act(project_id, task_id, command))

    @server.tool(name='jiejian_collaboration_question', structured_output=True)
    def question(ctx: Context, project_id: str, task_id: str, question_id: QuestionId,
        question: str, options: list[str] | None=None) -> dict[str, Any]:
        require_level(access, ctx, MCPAccessLevel.PREPARE, project_id=project_id)
        command = invoke(lambda: CollaborationQuestion(question_id=question_id, question=question, options=options or []), input_model=CollaborationQuestion, input_root='question')
        return invoke(lambda: core.collaboration.ask(project_id, task_id, command))

    @server.tool(name='jiejian_collaboration_receipt', structured_output=True)
    def receipt(ctx: Context, project_id: str, task_id: str, operation_id: str) -> dict[str, Any]:
        """查询业务回执并恢复协作关联；不重发原命令。"""
        require_level(access, ctx, MCPAccessLevel.PREPARE, project_id=project_id)
        return invoke(lambda: core.collaboration.reconcile(project_id, task_id, operation_id))

    @server.tool(name='jiejian_collaboration_control', structured_output=True)
    def control(ctx: Context, project_id: str, task_id: str,
        action: Literal['pause','resume','cancel','finish']) -> dict[str, Any]:
        require_level(access, ctx, MCPAccessLevel.PREPARE, project_id=project_id)
        return invoke(lambda: core.collaboration.control(project_id, task_id, action))
