const reasons: Record<string,string> = {
    TEST_IDENTITY_REQUIRED:'尚未建立对应的测试账号', TEST_IDENTITY_LOGIN_REQUIRED:'需要先完成账号登录',
    TEST_IDENTITY_REVIEW_REQUIRED:'保存的登录状态已不可用', TEST_ACTOR_SOURCE_STALE:'账号角色或其源码对应已经变化',
    ACTION_EXECUTION_REQUIRED:'尚未采用本项操作的录制', ACTION_RESOURCE_REQUIRED:'尚未绑定这次检查所用的资源',
    EFFECT_EVIDENCE_REQUIRED:'尚未绑定该业务结果的证明', ACTION_RECOVERY_REQUIRED:'尚未确定操作后的恢复方式',
    ACTION_BINDING_SOURCE_STALE:'操作、账号、运行来源或实现对应已经变化', RECORDING_SOURCE_STALE:'原录制与当前条件不再对应',
    RESOURCE_INJECTION_STALE:'资源位置与当前录制不一致', EFFECT_REFERENCE_STALE:'业务结果定义已经变化',
    RESOURCE_OWNER_SOURCE_STALE:'资源所有者的登录状态需要重新核对',
    REGISTERED_OBSERVER_UNAVAILABLE:'原证明来源当前不可用', ACTION_FLOW_UNAVAILABLE:'原操作记录无法完整读取',
    ACTION_FLOW_STALE:'原操作记录与当前账号或资源不再对应', SUPPLEMENT_RESOURCE_STALE:'补充材料所依赖的资源已经变化',
    SUPPLEMENT_REQUEST_STALE:'补充记录与当前请求不一致', REFERENCE_CAPTURE_IN_PROGRESS:'资源正在取样，需等待操作收尾',
};
export function materialReasons(codes:string[]) {
    return [...new Set(codes.map(code=>reasons[code]??'当前材料需要重新核对，原记录仍保留'))];
}
