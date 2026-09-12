# 变化与修复的固定产品用语；状态、范围和验收事实由确定性服务提供。

REPAIR_STATUS_LABELS = {
    "REPAIR_REQUIRED": "需要修复已确认的问题",
    "CHANGE_SUBMITTED": "修改已登记，仍需核对复验条件",
    "READY_TO_VERIFY": "已具备原题复验条件",
    "VERIFIED": "原问题已修复，正常业务验证通过",
    "NOT_VERIFIED": "原问题仍然存在",
    "INCONCLUSIVE": "修复证据不足，尚不能确认",
    "STALE": "原权限或复验依据已变化，需要重新确认",
}
CHANGE_IMPACT_LABELS = {
    "DIRECTLY_AFFECTED": "实现关联的代码发生变化，需要重新验证",
    "MAPPING_REVIEW_REQUIRED": "实现定位需要人工复核",
    "NO_DIRECT_EVIDENCE": "未发现直接实现关联；这不代表不存在其他影响",
}
REPAIR_REQUIREMENTS = {
    "disappear": "原规则禁止的业务后果必须在新的检查中消失。",
    "remain": "原正常对照和先前已通过的全部正常业务验证必须保留。",
    "permission": "保持原权限规则、操作账号和资源归属。",
    "evidence": "保持原决定性观察标准，不以减少证据要求代替修复。",
    "new_run": "登记修改不代表修复完成，需要按原题发起新的检查。",
}
CURRENT_TASK_TEXT = {
    "REGISTER_SOURCE_CHANGE": ("登记当前代码变化", "代码已变化，需要先重新核对实际修改。", "说明本次修改的目的。"),
    "VERIFY_REPAIR": ("按原题验证修复", "修改和准备条件已就绪，修复仍需新的检查证明。", "确认运行原权限和正常业务回归验证。"),
    "RUN_CURRENT_CHECK": ("检查当前权限要求", "当前准备条件已满足，需要通过实际业务后果形成判断。", "确认开始本次检查。"),
    "VIEW_CURRENT_RESULT": ("查看已发布检查结果", "本次检查已经形成可读取的结果。", "核对判断、证据和下一步。"),
}
