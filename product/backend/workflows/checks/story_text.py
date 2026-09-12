# 人类结果的固定解释文本；只翻译已发布事实，不生成或修改安全判断。

JUDGEMENTS = {
    "PASS": "本次权限要求已得到验证",
    "BLOCK": "已确认不应发生的业务后果",
    "INCONCLUSIVE": "现有证据不足以完成判断",
}
EXECUTION_LABELS = {
    "ACCEPTED": "业务请求已被接受",
    "DENIED": "业务请求被明确拒绝",
    "UNKNOWN": "无法确认业务请求的完成情况",
    "FAILED": "业务请求未能正常完成",
}
EFFECT_LABELS = {
    "CONFIRMED": "已确认这项业务结果发生",
    "ABSENT": "在已闭合的观察范围内未发生这项业务结果",
    "UNKNOWN": "无法确认这项业务结果是否发生",
}
PRECISION_LABELS = {
    "EXACT": "已定位到首个可证明的断裂位置",
    "RANGE": "断裂位于已确认的两个边界之间",
    "VIOLATION_ONLY": "违规已确认，现有证据不足以进一步定位",
}
CLAIM_BOUNDARIES = {
    "execution": "请求响应只能说明表面处理情况，不能单独证明权限安全。",
    "supporting": "这项材料说明执行过程，不能单独证明受保护业务结果发生或消失。",
    "unknown": "没有观察到充分证据，不等于业务后果没有发生。",
    "identity": "实际账号需要独立确认，不能用计划使用的账号代替。",
    "scope": "本次判断仅覆盖已冻结的权限、账号、资源和观察范围。",
    "immutable": "本次证据与结论将保留；完善条件后需要发起新的检查。",
}
