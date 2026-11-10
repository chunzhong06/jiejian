# 变化与修复的固定产品用语；状态、范围和验收事实由确定性服务提供。

REPAIR_STATUS_LABELS = {
    "REPAIR_REQUIRED": "需要修复已确认的问题",
    "CHANGE_SUBMITTED": "修改已登记，仍需核对复验条件",
    "READY_TO_VERIFY": "已具备重新检查原问题的条件",
    "VERIFIED": "原问题已修复，正常业务验证通过",
    "NOT_VERIFIED": "原问题仍然存在",
    "INCONCLUSIVE": "修复证据不足，尚不能确认",
    "STALE": "原权限或复验依据已变化，需要重新确认",
}
CHANGE_IMPACT_LABELS = {
    "DIRECTLY_AFFECTED": "实现关联的代码发生变化，需要重新验证",
    "MAPPING_REVIEW_REQUIRED": "需要核对业务操作与代码的对应关系",
    "NO_DIRECT_EVIDENCE": "未发现直接实现关联；这不代表不存在其他影响",
}
REPAIR_REQUIREMENTS = {
    "disappear": "原规则禁止的业务后果必须在新的检查中消失。",
    "remain": "继续检查原来允许的操作，以及此前已通过的其他正常功能。",
    "permission": "保持原权限规则、操作账号和资源归属。",
    "evidence": "沿用原来的取证和判断标准，不能通过减少证据要求让检查通过。",
    "new_run": "登记修改不代表修复完成，需要针对原问题发起新的检查。",
}
CURRENT_TASK_TEXT = {
    "PREPARE_AGENT_REPAIR": ("继续处理已确认的权限问题", "原问题和正常功能要求已经保留。完成应用修改或部署准备后，按原条件再次验证。", "核对原问题，选择适用的处理方式，再确认复验范围。"),
    "REGISTER_SOURCE_CHANGE": ("登记当前代码变化", "代码已变化，需要先重新核对实际修改。", "说明本次修改的目的。"),
    "VERIFY_REPAIR": ("检查原问题是否已解决", "修改和准备条件已就绪，修复仍需新的检查证明。", "确认重新检查原问题，以及要求保留的正常功能。"),
    "RUN_CURRENT_CHECK": ("检查当前权限要求", "检查材料已准备好，实际执行后再根据结果判断。", "确认开始本次检查。"),
    "VIEW_CURRENT_RESULT": ("查看已保存的检查结果", "检查结果已发布，可以查看。", "查看结论和依据，决定后续处理。"),
}
