const reasons: Record<string,string> = {
    CONDITION_SOURCE_REQUIRED:'需要设置租户或数据状态的判断依据', RULE_CASE_DATA_STALE:'这条规则的测试数据需要重新核对',
    PERMISSION_CONDITION_UNKNOWN:'未能确认规则所需的身份、租户或数据状态', PERMISSION_CONDITION_MISMATCH:'这份数据不符合规则的适用条件',
    TEST_IDENTITY_REQUIRED:'尚未建立对应的测试账号', TEST_IDENTITY_LOGIN_REQUIRED:'需要先完成账号登录',
    TEST_IDENTITY_REVIEW_REQUIRED:'保存的登录状态已不可用', TEST_ACTOR_SOURCE_STALE:'账号角色或其源码对应已经变化',
    ACTION_EXECUTION_REQUIRED:'尚未选择检查要执行的操作', ACTION_RESOURCE_REQUIRED:'尚未确认检查所用的数据',
    EFFECT_EVIDENCE_REQUIRED:'尚未设置如何判断业务结果', ACTION_RECOVERY_REQUIRED:'尚未确定操作后的恢复方式',
    ACTION_BINDING_SOURCE_STALE:'操作、账号或运行的源码已有变化', RECORDING_SOURCE_STALE:'原录制与当前条件不再对应',
    RESOURCE_INJECTION_STALE:'录制中使用的数据位置已有变化', EFFECT_REFERENCE_STALE:'业务结果定义已经变化',
    RESOURCE_OWNER_SOURCE_STALE:'资源所有者的登录状态需要重新核对',
    REGISTERED_OBSERVER_UNAVAILABLE:'原证明来源当前不可用', ACTION_FLOW_UNAVAILABLE:'原操作记录无法完整读取',
    ACTION_FLOW_STALE:'原操作记录与当前账号或资源不再对应', SUPPLEMENT_RESOURCE_STALE:'补充材料所依赖的资源已经变化',
    SUPPLEMENT_REQUEST_STALE:'补充记录与当前请求不一致', REFERENCE_CAPTURE_IN_PROGRESS:'资源正在取样，需等待操作收尾',
};
export function materialReasons(codes:string[]) {
    return [...new Set(codes.map(code=>reasons[code]??'当前材料需要重新核对，原记录仍保留'))];
}
