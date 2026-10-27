# 所属业务域的共享测试构造器；不导入测试用例。

from tests.support.contracts import MCP_TOOL_LEVELS

TOOLS = set(MCP_TOOL_LEVELS)


async def start_task(client, project_id):
    from uuid import uuid4
    created = await client.call_tool("jiejian_task_create", {"project_id": project_id, "operation_id": uuid4().hex,
        "title": "验证交付流程", "goal": "保持已确认权限并完成一批修改"})
    assert not created.is_error
    task = created.structured_content
    accepted = await client.call_tool("jiejian_task_accept", {"project_id": project_id, "task_id": task["task_id"],
        "operation_id": uuid4().hex, "expected_version": task["task_version"], "context_id": task["context_id"]})
    assert not accepted.is_error
    receipt = accepted.structured_content
    return {"task_id": receipt["task_id"], "context_id": receipt["context_id"], "expected_version": receipt["task_version"], "operation_id": uuid4().hex}
