# 将Workspace主任务、材料和来源事实组织为GUI/MCP共享建议；只读，不另算安全结论。
from urllib.parse import urlencode

from product.backend.workflows.preparation.guidance.models import PreparationGuidance, PreparationMaterialAdvice, PreparationNextAction, ProofSourceAdvice


PREPARATION_TASKS = frozenset({'SELECT_ALLOW_CONTROL', 'REVIEW_RECORDING', 'PREPARE_TEST_IDENTITY',
    'DEMONSTRATE_ACTION', 'PREPARE_ACTION_RESOURCE', 'COMPLETE_EFFECT_EVIDENCE', 'COMPLETE_RECOVERY'})
REASONS = {
    'TEST_IDENTITY_REQUIRED': '所需测试账号尚未准备，请先补齐当前业务角色的账号。',
    'TEST_IDENTITY_LOGIN_REQUIRED': '该账号缺少当前可用的登录状态，请重新登录后核对原材料。',
    'TEST_IDENTITY_REVIEW_REQUIRED': '账号与当前角色依据需要重新核对；不是要求删除账号或重做其他材料。',
    'TEST_IDENTITY_INSPECTION_UNAVAILABLE': '账号状态暂时未能核对，请先读取账号情况，不推测登录是否失效。',
    'RESOURCE_OWNER_SOURCE_STALE': '资源所有者的账号或角色依据已变化，请核对资源所属账号。',
    'TEST_ACTOR_SOURCE_STALE': '操作账号的角色或实现依据已变化，请核对账号与角色。',
    'RECORDING_SOURCE_STALE': '原录制及其审阅来源已无法匹配。原记录保留，请核对并更新这项录制。',
    'SUPPLEMENT_RESOURCE_STALE': '这项材料依赖的资源已变化，先核对测试资源，再更新证明或恢复方式。',
    'RESOURCE_INJECTION_STALE': '动作录制与资源参数不再匹配，请核对动作使用的具体资源。',
    'ACTION_BINDING_SOURCE_STALE': '材料与当前业务来源不一致，请核对应用、业务修订与实现。',
    'REGISTERED_OBSERVER_UNAVAILABLE': '原证明来源当前不可用，请核对该来源；现有信息不足以判断具体原因。',
    'PROOF_CAPABILITY_UNAVAILABLE': '当前证明能力尚未满足这一业务结果，请核对支持范围和材料。',
    'EVIDENCE_SNAPSHOT_CHANGED': '证明材料在读取期间发生变化，请重新核对这一项。',
    'ACTION_EXECUTION_REQUIRED': '尚缺当前动作的操作演示，请用正常允许账号录制这项业务操作。',
    'ACTION_RESOURCE_REQUIRED': '尚缺动作对应的测试资源，请核对资源与所有者。',
    'EFFECT_EVIDENCE_REQUIRED': '尚缺这一业务结果的证明，只需补齐该结果的材料。',
    'ACTION_RECOVERY_REQUIRED': '当前动作会改变状态，需要准备对应的恢复操作。',
    'IDENTITY_SESSION_MISSING': '测试账号缺少可用登录状态，需要重新准备账号。',
    'ACTUAL_IDENTITY_MISMATCH': '实际账号或角色与配置不一致，请核对登录账号及角色对应。',
    'MAPPING_MISSING': '配置指向的字段没有读到，请让Agent核对当前字段位置。',
    'MAPPING_TYPE_INVALID': '实际字段类型与证明要求不一致，请核对业务字段及配置。',
    'MAPPING_REQUIRED': '缺少必要字段映射，请让Agent补齐当前来源配置。',
    'PROTECTED_FIELD_MISSING': '受保护的内容字段没有读到，请核对所选字段与实际响应。',
    'RESOURCE_OWNER_MISMATCH': '来源中的资源或所有者与已确认材料不一致，需要核对资源对应。',
    'RECORD_PROVIDER_UNAVAILABLE': '记录组件或源码与运行实例的对应尚未确认，请核对受控运行。',
    'RECORD_SOURCE_UNAVAILABLE': '记录来源暂时无法读取，请核对实例与来源；现有信息不足以判断具体原因。',
    'READ_AUTHORITY_UNAVAILABLE': '读取授权或当前实例需要重新核对，不能沿用这次读取结果。',
    'SOURCE_READ_DENIED': '当前账号未能读取来源，请核对账号和读取范围。',
    'CONTRACT_UNVERIFIED': '尚不能确认该资源由受支持的记录组件实际保存，请核对接入方式。',
    'SOURCE_REQUIRES_MIGRATION': '旧来源不再用于新的完整证明，需要按通用记录方式重新准备。',
}


def _url(route, project, **references):
    return '#' + route + '?' + urlencode({'project_id': project, **{k: v for k, v in references.items() if v is not None}})


def _workspace_action(project, task):
    if task is None:
        return None
    refs = {}
    if task.proposal_id and task.route == '/permissions':
        refs['proposal_id'] = task.proposal_id
    if task.repair_fingerprint and task.route == '/changes':
        refs['repair_reference'] = task.repair_fingerprint
    elif task.run_id:
        refs['run_id'] = task.run_id
    elif task.change_id and task.route in {'/tests', '/changes'}:
        refs['change_id'] = task.change_id
    if task.route == '/tests' and task.task_kind in PREPARATION_TASKS:
        refs['task_id'] = task.task_id
    tool, level = {'RUN_CURRENT_CHECK': ('jiejian_check_run', 'EXECUTE'),
                   'REGISTER_SOURCE_CHANGE': ('jiejian_change_registration_preview', 'READ')}.get(task.task_kind, (None, None))
    return PreparationNextAction(kind=task.task_kind, title=task.title,
        reason=task.why_now, handler='EITHER' if tool else 'USER',
        gui_url=_url(task.route, project, **refs), mcp_tool=tool, required_level=level,
        action_id=task.business_action_id, action_revision=task.action_revision, effect_id=task.effect_id, task_id=task.task_id)


def _source_advice(context, source):
    config, attempt = source['config'], source['preflight']
    project = context['project_id']
    url = _url('/tests', project, materials=1, proof_sources=1,
               source=source['source_id'], action_id=config['action_id'])
    common = dict(action_id=config['action_id'], action_revision=config['action_revision'], effect_id=config['effect_id'],
        source_id=source['source_id'], source_revision=source['revision'],
        preflight_id=None if attempt is None else attempt['preflight_id'])

    def advice(kind, title, reason, handler='USER', tool=None, level=None, state='NEEDS_ACTION', route=None):
        return ProofSourceAdvice(source_id=source['source_id'], revision=source['revision'], state=state,
            next_action=PreparationNextAction(kind=kind, title=title, reason=reason, handler=handler,
                mcp_tool=tool, required_level=level, gui_url=route or url, **common))

    if not source['supported']:
        return advice('MIGRATE_SOURCE', '重新准备证明来源', REASONS['SOURCE_REQUIRES_MIGRATION'],
                      'AGENT', 'jiejian_proof_source_save', 'PREPARE', 'UNSUPPORTED')
    current_action = next((item for item in context['actions'] if item['action_id'] == config['action_id']), None)
    if (current_action is None or current_action['revision'] != config['action_revision']
            or config['effect_id'] not in {item['effect_id'] for item in current_action['effects']}):
        return advice('REVIEW_RULE_REFERENCE', '重新核对来源对应的权限要求',
            '来源对应的动作或业务结果已有变化。先核对当前规则，再更新来源关联；旧来源和历史证据保留。',
            route=_url('/permissions', project, action_id=config['action_id']))
    if not context['runtime_available']:
        return advice('REVIEW_RUNTIME', '核对当前受控运行',
            '当前源码与受控实例尚未对应；已保存配置和录制保留，先核对应用运行。',
            route=_url('/environment', project))
    if not source['read_scope_confirmed']:
        return advice('CONFIRM_READ_SCOPE', '确认这项来源的读取范围',
            '预检查需要当前账号、资源和路径的读取授权；Agent不能代替你确认。')
    if attempt and attempt['state'] in {'PENDING', 'RUNNING', 'RETRY_WAIT'}:
        return advice('WAIT_PREFLIGHT', '查看正在进行的预检查',
            '已有预检查正在处理，查询原任务即可，不需要再次提交。',
            'SYSTEM', 'jiejian_proof_preflight_status', 'READ', 'WAITING')
    if attempt and attempt['state'] == 'SUCCEEDED' and attempt['current_basis'] and attempt['report']:
        report = attempt['report']
        if report['assessment'] == 'USABLE':
            if source['adopted']:
                return ProofSourceAdvice(source_id=source['source_id'], revision=source['revision'],
                                         state='USABLE', next_action=None)
            return advice('REVIEW_ADOPTION', '核对并采用这项证明来源',
                '技术预检查已可用；请核对采用影响。采用只完成材料准备，不形成安全结论。',
                tool='jiejian_proof_adoption_preview', level='READ')
        codes = [check['code'] for check in report['checks'] if check['status'] != 'CONFIRMED']
        reason = next((REASONS[code] for code in codes if code in REASONS),
                      '预检查尚不能确认来源可用，请查看核对项；不推测未知失败原因。')
        if any(code in {'ACTUAL_IDENTITY_MISMATCH', 'IDENTITY_SESSION_MISSING', 'SOURCE_READ_DENIED'} for code in codes):
            return advice('REVIEW_IDENTITY', '核对测试账号与角色', reason,
                route=_url('/tests', project, materials=1, identities=1, action_id=config['action_id']))
        return advice('REVIEW_SOURCE', '核对这项证明来源的缺口', reason,
            'AGENT', 'jiejian_proof_source_save', 'PREPARE',
            'UNSUPPORTED' if report['assessment'] == 'UNSUPPORTED' else 'NEEDS_ACTION')
    reason = ('权限、账号、材料或实例已变化，旧报告不能代表当前情况。配置保留，重新预检查即可。'
              if attempt and not attempt['current_basis'] else
              '读取范围已确认，可发起有界预检查；它不执行业务动作，也不产生权限结论。')
    if attempt and attempt['state'] in {'FAILED', 'CANCELLED', 'UNKNOWN'}:
        reason = '上次预检查没有形成当前可用报告。原任务已保留，请核对状态后明确重新预检查。'
    return advice('RUN_PREFLIGHT', '重新核对证明来源' if attempt else '预检查证明来源',
                  reason, 'EITHER', 'jiejian_proof_preflight_start', 'EXECUTE')


def _material_advice(project, preparation, identities=()):
    rows = []
    labels = {item['identity_id']: item['label'] for item in identities}
    for action in preparation.actions:
        base = dict(action_id=action.action_id, action_revision=action.action_revision)
        items = [('identity', slot.test_identity_id or slot.requirement.slot_id,
                  labels.get(slot.test_identity_id, slot.actor_display_name + '账号'), slot) for slot in action.identity_requirements.slots]
        items += [('execution', None, action.display_name + ' · 动作录制', action.execution)]
        items += [('resource', item.owner_test_identity_id, action.display_name + ' · 测试资源', item) for item in action.resources]
        items += [('evidence', item.effect_id, action.display_name + ' · 结果证明', item) for item in action.effect_evidence]
        items += [('recovery', None, action.display_name + ' · 恢复方式', action.recovery)]
        for kind, member, label, item in items:
            status = item.status.value
            reason = ('当前材料仍可沿用；正式检查会重新形成独立事实。' if status == 'SATISFIED' else
                      '当前动作不需要此类材料。' if status == 'NOT_REQUIRED' else
                      next((REASONS[code] for code in item.reason_codes if code in REASONS),
                           '已保存材料需要按当前条件复核；其他有效材料继续保留。' if status == 'STALE' else
                           '当前条件尚未满足，请进入这一项核对；不要求重新准备其他有效材料。'))
            rows.append(PreparationMaterialAdvice(**base, kind=kind, member_id=member,
                label=label, status=status, reason=reason, reason_codes=item.reason_codes,
                gui_url=_url('/tests', project, materials=1, action_id=action.action_id,
                             identities=1 if kind == 'identity' else None)))
    return tuple(rows)


class PreparationGuidanceService:
    def __init__(self, *, sources, workspace, preparation):
        self._sources, self._workspace, self._preparation = sources, workspace, preparation

    def context(self, project_id):
        """同一入口供GUI与MCP读取；建议只带引用，实际命令仍由原服务重新核验。"""
        before = self._sources.context(project_id)
        workspace = self._workspace.get(project_id)
        preparation = self._preparation.get(project_id)
        context = self._sources.context(project_id)
        if before['basis_id'] != context['basis_id']:
            guidance = PreparationGuidance(project_id=project_id, basis_id=context['basis_id'], state='NEEDS_REFRESH',
                next_action=None, materials=(), sources=(), note='读取期间应用条件已变化，请重新读取准备情况；本次不提供混合状态的建议。')
        else:
            task = workspace.primary_task
            next_action = _workspace_action(project_id, task)
            sources = tuple(_source_advice(context, item) for item in context['sources'])
            materials = _material_advice(project_id, preparation, context.get('identities', ()))
            if task and task.task_kind == 'PREPARE_TEST_IDENTITY' and task.test_identity_id:
                account = next((item for item in materials if item.kind == 'identity'
                    and item.action_id == task.business_action_id and item.member_id == task.test_identity_id), None)
                if account:
                    next_action = next_action.model_copy(update={
                        'title': ('重新登录：' if 'TEST_IDENTITY_LOGIN_REQUIRED' in account.reason_codes else '核对测试账号：') + account.label[:80],
                        'reason': account.reason})
            # 只有全局任务已经进入结果证明时才细分来源步骤，不能越过业务/身份/录制前置任务。
            if task and task.task_kind == 'COMPLETE_EFFECT_EVIDENCE':
                relevant = {item['source_id'] for item in context['sources']
                    if item['config']['action_id'] == task.business_action_id
                    and item['config']['effect_id'] == task.effect_id}
                candidates = [item for item in sources if item.source_id in relevant and item.next_action]
                if len(relevant) == 1 and len(candidates) == 1:
                    next_action = candidates[0].next_action.model_copy(update={'task_id': task.task_id})
                elif not relevant:
                    next_action = PreparationNextAction(kind='PREPARE_PROOF_SOURCE', title='为当前业务结果准备证明',
                        reason='先让Agent读取当前要求和已有材料。需要新来源时只补这一项，规则与其他有效材料继续沿用。',
                        handler='AGENT', gui_url=_url('/tests', project_id, materials=1, proof_sources=1, action_id=task.business_action_id),
                        mcp_tool='jiejian_proof_source_save', required_level='PREPARE', action_id=task.business_action_id,
                        action_revision=task.action_revision, effect_id=task.effect_id, task_id=task.task_id)
            guidance = PreparationGuidance(project_id=project_id, basis_id=context['basis_id'], state='CURRENT',
                next_action=next_action, materials=materials, sources=sources,
                note='建议依据当前事实生成。打开入口不代表授权执行；准备可用不代表权限已通过检查。')
        return context | {'guidance': guidance.model_dump(mode='json')}
