"""解释既有材料事实的处理与责任；不改变就绪、采用或授权状态。"""

IDENTITY_RECHECK = frozenset({'TEST_IDENTITY_LOGIN_REQUIRED','TEST_IDENTITY_REVIEW_REQUIRED',
    'MATERIAL_SUBJECT_CHANGED','MATERIAL_OWNER_CHANGED','RESOURCE_OWNER_CHANGED','TEST_ACTOR_SOURCE_STALE'})
ENVIRONMENT_RECHECK = frozenset({'MATERIAL_ENDPOINT_CHANGED'})
SOURCE_RECHECK = frozenset({'MATERIAL_ACTION_REVISION_CHANGED','MATERIAL_IMPLEMENTATION_CHANGED','MATERIAL_SOURCE_CHANGED',
    'ACTION_BINDING_SOURCE_STALE','OPERATION_ENTITY_QUERY_STALE','OPERATION_FLOW_SOURCE_STALE','OPERATION_FLOW_UNAVAILABLE',
    'OPERATION_RECOVERY_STALE','ACTION_FLOW_STALE','ACTION_FLOW_UNAVAILABLE','EFFECT_REFERENCE_STALE',
    'RECORDING_SOURCE_STALE','REGISTERED_OBSERVER_UNAVAILABLE','RESOURCE_OWNER_SOURCE_STALE',
    'SUPPLEMENT_REQUEST_STALE','SUPPLEMENT_RESOURCE_STALE','RECHECK_REQUIRED'})
MISSING = frozenset({'ACTION_EXECUTION_REQUIRED','ACTION_RECOVERY_REQUIRED','ACTION_RESOURCE_REQUIRED',
    'ALLOW_RESOURCE_SETUP_REQUIRED','EFFECT_EVIDENCE_REQUIRED','TEST_IDENTITY_REQUIRED'})


def material_handling(kind, item):
    labels = {'identity': '测试账号', 'execution': '操作流程', 'resource': '测试资源', 'evidence': '结果证明', 'recovery': '恢复方式'}
    name = labels[kind]
    reasons = set(item.reason_codes)
    if item.status == 'SATISFIED':
        return dict(handling='KEEP', handler='SYSTEM', explanation=(
            '保留原材料对应的主体，不因新增要求交换账号。' if getattr(item, 'selection_basis', None) == 'CURRENT_MATERIAL' else '当前范围与材料依据相符，可沿用已有' + name + '。'),
            next_step='保留准确引用，提交检查前由原预览重新核对。')
    if item.status == 'BLOCKED':
        return dict(handling='DECIDE', handler='USER', explanation=(
            '旧材料对同一账号槽位给出了冲突的主体，需要确认实际归属。' if 'IDENTITY_MATERIAL_ASSIGNMENT_CONFLICT' in reasons else '当前条件尚不满足，需先处理阻塞原因。'),
            next_step='在原材料入口核对冲突与业务约束，再重新读取本次准备。')
    if item.status == 'STALE' or reasons & (IDENTITY_RECHECK | ENVIRONMENT_RECHECK | SOURCE_RECHECK):
        explanation = '保留已保存配置，重新核对当前' + name + '。'
        if reasons & ENVIRONMENT_RECHECK:
            explanation = '运行实例或访问环境已变化，需要核对本次材料的适用性。'
        elif reasons & IDENTITY_RECHECK:
            explanation = '账号会话或实际主体需要重核，原身份与资源对应继续保留。'
        elif reasons & SOURCE_RECHECK:
            explanation = '源码或来源依据已变化，需核对受影响部分。'
        return dict(handling='RECHECK', handler='USER' if kind == 'identity' else 'AGENT_AND_USER',
                    explanation=explanation, next_step='读取原配置和已保存依据，只处理本次失效条件。')
    # 未知原因不能解释成从零新建；既有配置或执行中状态仍由原能力拥有。
    if not reasons or not reasons <= MISSING:
        return dict(handling='RECHECK', handler='USER' if kind == 'identity' else 'AGENT_AND_USER',
            explanation='本次'+name+'的处理原因仍需核对，保留已有记录。',
            next_step='在原材料入口读取具体原因及原操作进度，再继续当前任务。')
    return dict(handling='ADD', handler='USER' if kind == 'identity' else 'AGENT_AND_USER',
        explanation='本次要求还缺少相应' + name + '。',
        next_step='补充实际账号并核对身份。' if kind == 'identity' else '先整理已有来源和唯一候选，再在原入口补齐并确认使用。')


def material_context(kind, item, action):
    """依赖仅引用本次准备槽位；角色相同的两个账号仍可按槽位与主体区分。"""
    identities=action.identity_requirements.slots
    slot_id=item.requirement.slot_id if kind=='identity' else item.owner_slot_id if kind=='resource' else None
    label=getattr(item,'actor_display_name','') or getattr(item,'business_label','')
    if kind=='identity':
        label += ' · 账号槽位 '+str(item.requirement.ordinal)
        if item.test_identity_id:
            label += ' · '+item.test_identity_id[-8:]
    return dict(slot_id=slot_id,member_label=label,
        prerequisites=tuple(slot.requirement.slot_id for slot in identities if kind!='identity'
            and slot.status!='SATISFIED' and (kind!='resource' or slot.requirement.slot_id==item.owner_slot_id)))
