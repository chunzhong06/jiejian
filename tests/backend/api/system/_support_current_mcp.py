# 所属业务域的共享测试构造器；不导入测试用例。

TOOLS = {"jiejian_project_list","jiejian_project_show","jiejian_application_understanding","jiejian_business_boundary",
    "jiejian_preparation_context", "jiejian_proof_source_save", "jiejian_proof_source_show",
    "jiejian_proof_preflight_start", "jiejian_proof_preflight_status", "jiejian_proof_preflight_cancel",
    "jiejian_proof_adoption_preview", "jiejian_preparation_receipt",
    "jiejian_rule_context", "jiejian_rule_candidate_save", "jiejian_rule_candidate_show", "jiejian_rule_operation",
    "jiejian_intent_show","jiejian_identity_list","jiejian_system_status","jiejian_change_show","jiejian_check_status",
    "jiejian_result_show","jiejian_repair_show","jiejian_change_submit","jiejian_change_registration_preview","jiejian_change_register","jiejian_check_run","jiejian_check_cancel",
    "jiejian_task_list", "jiejian_task_show", "jiejian_task_context", "jiejian_task_create", "jiejian_task_accept", "jiejian_receipt_show"}


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
