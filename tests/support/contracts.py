# 经产品设计接受的当前合同；独立列出预期，不从被测实现复制答案。
WORKER_CAPABILITIES = ("CHECK", "PROOF_PREFLIGHT", "RECORDING", "REFERENCE_CAPTURE")
JOB_TARGET_FIELDS = frozenset({"run_id", "recording_id", "runtime_load_id", "preflight_id", "reference_capture_id"})

# 已公开的 Agent 工具与最低授权；架构和 SDK 验证共用同一独立合同。
MCP_TOOL_LEVELS = dict.fromkeys((
    'jiejian_agent_context','jiejian_check_preview','jiejian_preparation_batch_plan','jiejian_preparation_batch_status',
    'jiejian_project_list','jiejian_project_show','jiejian_application_understanding','jiejian_business_boundary',
    'jiejian_preparation_context','jiejian_proof_source_show','jiejian_preparation_suggestion_show',
    'jiejian_preparation_suggestion_receipt','jiejian_proof_preflight_status','jiejian_proof_adoption_preview',
    'jiejian_preparation_receipt','jiejian_rule_context','jiejian_rule_candidate_show','jiejian_rule_operation',
    'jiejian_rule_preview','jiejian_intent_show','jiejian_identity_list','jiejian_system_status','jiejian_change_show',
    'jiejian_check_status','jiejian_result_show','jiejian_evidence_show','jiejian_repair_show',
    'jiejian_change_registration_preview','jiejian_task_list','jiejian_task_show','jiejian_task_context','jiejian_receipt_show',
), 'READ') | dict.fromkeys((
    'jiejian_proof_source_save','jiejian_preparation_suggestion_save','jiejian_rule_candidate_save',
    'jiejian_change_submit','jiejian_change_register','jiejian_task_create','jiejian_task_accept',
), 'PREPARE') | dict.fromkeys((
    'jiejian_preparation_batch_cancel','jiejian_proof_preflight_start','jiejian_proof_preflight_cancel','jiejian_check_run','jiejian_check_cancel',
), 'EXECUTE')
