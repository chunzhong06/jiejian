# 材料建议只沿精确业务修订和批准映射续接；缺失映射时不按名称猜角色、动作或结果。
from product.backend.domain.errors import ErrorCode, JiejianError


def _invalid(message):
    raise JiejianError(ErrorCode.STATE_PRECONDITION, message)


def _candidate_material_meaning(candidate, target):
    content = candidate.content
    permissions = [item for item in content.permissions if item.business_action_item_id == target.action_item_id]
    actor_ids = {target.actor_item_id}
    actor_ids.update(item.subject_actor_item_id for item in permissions)
    actor_ids.update(item.resource_owner_actor_item_id for item in permissions)
    return {
        'basis': candidate.basis_id, 'original_text': content.original_text,
        'actions': [item.model_dump(mode='json') for item in content.actions if item.item_id == target.action_item_id],
        'actors': sorted((item.model_dump(mode='json') for item in content.actors if item.item_id in actor_ids), key=lambda item:item['item_id']),
        'permissions': sorted((item.model_dump(mode='json') for item in permissions), key=lambda item:item['item_id']),
    }


def approved_target(work, project_id, action_id, revision, actor_id=None, actor_revision=None, effect_id=None):
    action = work.business_boundaries.action_revision(action_id, revision)
    if action is None or action.project_id != project_id:
        _invalid('建议引用的动作修订不存在或不属于当前应用')
    root = work.business_boundaries.action(action_id)
    current = root.current_revision == revision and action.effective_state.value == 'ACTIVE'
    actor = None
    if actor_id is not None:
        actor = work.business_boundaries.actor_revision(actor_id, actor_revision)
        if actor is None or actor.project_id != project_id:
            _invalid('建议引用的角色修订不存在或不属于当前应用')
        actor_root = work.business_boundaries.actor(actor_id)
        current = current and actor_root.current_revision == actor_revision and actor.effective_state.value == 'ACTIVE'
    effect = next((item for item in action.effect_catalog if item.effect_id == effect_id), None)
    if effect_id is not None and effect is None:
        _invalid('建议引用的结果不属于这项动作修订')
    return {'state':'APPROVED' if current else 'STALE', 'action_id':action_id, 'action_revision':revision,
        'action_label':action.display_name, 'actor_id':actor_id, 'actor_revision':actor_revision,
        'actor_label':None if actor is None else actor.display_name, 'effect_id':effect_id,
        'effect_label':None if effect is None else effect.business_label}


def resolve_target(work, project_id, target, candidates, boundaries):
    if target.kind == 'APPROVED':
        return approved_target(work, project_id, target.action_id, target.action_revision,
            target.actor_id, target.actor_revision, target.effect_id)
    candidate = work.rule_candidates.get(project_id, target.candidate_id, target.revision)
    if candidate is None:
        _invalid('建议对应的规则候选修订不存在')
    proposal_id = work.rule_candidates.proposal_id(target.candidate_id, target.revision)
    decision = None if proposal_id is None else work.business_boundaries.decision_for_proposal(proposal_id)
    common = {'candidate_id':target.candidate_id, 'candidate_revision':target.revision}
    if decision is not None and decision.decision.value == 'APPROVED':
        mappings = [item for item in work.rule_candidates.approval_mappings(proposal_id=proposal_id)
            if item['entity_references'] is not None and item['entity_references']['action']['item_id'] == target.action_item_id]
        current_rules = {(rule.intent_id, rule.revision, rule.intent_hash) for rule in boundaries.view(project_id, work=work).permission_intents}
        if any((item['intent_id'], item['revision'], item['intent_hash']) not in current_rules for item in mappings):
            _invalid('建议对应的已批准权限已经改变，请核对当前规则含义')
        references = [item['entity_references'] for item in mappings]
        actions = {(item['action']['action_id'], item['action']['revision']) for item in references}
        actors = {(actor['actor_id'], actor['revision']) for item in references for actor in item['actors'] if actor['item_id'] == target.actor_item_id}
        effects = {effect['effect_id'] for item in references for effect in item['effects'] if effect['item_id'] == target.effect_item_id}
        if len(actions) != 1 or (target.actor_item_id and len(actors) != 1) or (target.effect_item_id and len(effects) != 1):
            return {**common, 'state':'ASSOCIATION_UNAVAILABLE', 'action_label':'已批准候选中的动作',
                'action_id':None,'action_revision':None,'actor_id':None,'actor_revision':None,'effect_id':None,
                'actor_label':None,'effect_label':None}
        action_id, revision = next(iter(actions))
        actor_id, actor_revision = next(iter(actors)) if target.actor_item_id else (None,None)
        effect_id = next(iter(effects)) if target.effect_item_id else None
        return {**approved_target(work, project_id, action_id, revision, actor_id, actor_revision, effect_id), **common}
    head = work.rule_candidates.get(project_id,target.candidate_id)
    if head is None or work.rule_candidates.visibility(target.candidate_id)['archived']:
        _invalid('对应规则候选不可继续处理，请先核对当前候选')
    if head.revision != target.revision:
        # 人保存范围或补其他动作不应废掉本项建立办法；只沿同一候选且业务含义未变的头续接。
        # 已拒绝的提案不能通过续接恢复；批准仍必须有精确实体映射。
        if decision is not None or _candidate_material_meaning(candidate, target) != _candidate_material_meaning(head, target):
            _invalid('对应角色、动作或权限含义已有变化，请重新核对这项建议')
        return resolve_target(work, project_id, target.model_copy(update={'revision':head.revision}), candidates, boundaries)
    draft = boundaries.maintenance_draft(project_id, work=work, allow_empty=True)
    if candidate.basis_id != 'rb_' + draft.boundary_state_fingerprint or (decision and decision.decision.value != 'APPROVED'):
        _invalid('对应规则候选需要重新整理，不能作为当前材料建议的依据')
    merged = candidates._merge(candidate, draft)
    action = next((item for item in merged.actions if item.item_id == target.action_item_id), None)
    actor = next((item for item in merged.actors if item.item_id == target.actor_item_id), None)
    if action is None or (target.actor_item_id is not None and actor is None):
        _invalid('建议的角色或动作局部引用不属于这份候选')
    effect = next((item for item in action.effects if item.item_id == target.effect_item_id), None)
    if target.effect_item_id is not None and effect is None:
        _invalid('建议的结果局部引用不属于这项候选动作')
    return {**common, 'state':'WAITING_APPROVAL', 'action_id':action.action_id,
        'action_revision':action.expected_current_revision, 'action_label':action.display_name,
        'actor_id':None if actor is None else actor.actor_id,
        'actor_revision':None if actor is None else actor.expected_current_revision,
        'actor_label':None if actor is None else actor.display_name,
        'effect_id':None if effect is None else effect.effect_id, 'effect_label':None if effect is None else effect.business_label}


def validate_existing_references(work, project_id, item, target, facts, recording_references):
    """只核对引用属于当前对象；登录、录制审阅和采用仍由原服务判断是否可用。"""
    material = item.material
    if material.kind == 'identity':
        known = {value.identity_id:value for value in facts.identities}
        for identity_id in material.existing_identity_ids:
            identity = known.get(identity_id)
            if identity is None or (identity.actor_id,identity.actor_revision) != (target['actor_id'],target['actor_revision']):
                _invalid('已有账号引用与建议角色不一致')
    if material.kind in {'execution','recovery'}:
        known = {value['recording_id']:value for value in recording_references}
        for recording_id in material.existing_recording_ids:
            record = known.get(recording_id)
            purpose = 'TARGET' if material.kind == 'execution' else 'RECOVERY'
            if record is None or (record['business_action_id'],record['action_revision'],record['purpose']) != (target['action_id'],target['action_revision'],purpose):
                _invalid('现成录制与建议的动作、修订或用途不一致')
    if material.kind == 'resource':
        known = {'res_'+value.binding_fingerprint[:32]:value for value in facts.resources}
        identities = {value.identity_id:value for value in facts.identities}
        for resource_id in material.existing_resource_ids:
            resource = known.get(resource_id)
            owner = None if resource is None else identities.get(resource.resource_owner_test_identity_id)
            if resource is None or owner is None or (resource.business_action_id,resource.action_revision,owner.actor_id,owner.actor_revision) != (target['action_id'],target['action_revision'],target['actor_id'],target['actor_revision']):
                _invalid('现有资源与建议的动作或所有者不一致')
    if material.kind == 'evidence':
        for source_id in material.existing_source_ids:
            source = work.proof_sources.source(project_id,source_id)
            if source is None or (source.config.action_id,source.config.action_revision,source.config.effect_id) != (target['action_id'],target['action_revision'],target['effect_id']):
                _invalid('现有证明来源与建议的动作或结果不一致')
