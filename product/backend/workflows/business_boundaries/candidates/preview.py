# 根据指定修订纯匹配规则，返回命中项与可选业务对象；不执行目标，也不保存任何结果。
from product.backend.core.boundaries.permissions import permission_relation_consistent
from product.backend.core.errors import ErrorCode, JiejianError


def preview_rules(work, project_id, command, candidate_service):
    reference = command.reference
    actor_labels, actions, permissions, revisions = {}, {}, [], {}
    if reference.kind == 'APPROVED':
        for item in reference.rules:
            rule = work.permission_intents.get_revision(item.intent_id, item.revision)
            if rule is None or rule.project_id != project_id:
                raise JiejianError(ErrorCode.RECORD_NOT_FOUND, '指定规则修订不存在')
            for actor_id, revision in ((rule.subject_actor_id, rule.subject_actor_revision),
                                       (rule.resource_owner_actor_id, rule.resource_owner_actor_revision)):
                actor = work.business_boundaries.actor_revision(actor_id, revision)
                if actor_id in revisions and revisions[actor_id] != revision:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, '这些规则引用了不同的角色修订，请分开预览')
                revisions[actor_id] = revision
                actor_labels[actor_id] = actor.display_name
            action = work.business_boundaries.action_revision(rule.business_action_id, rule.action_revision)
            if action.action_id in revisions and revisions[action.action_id] != action.revision:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '这些规则引用了不同的动作修订，请分开预览')
            revisions[action.action_id] = action.revision
            actions[action.action_id] = {'id': action.action_id, 'label': action.display_name,
                'effects': [{'id': effect.effect_id, 'label': effect.business_label} for effect in action.effect_catalog]}
            permissions.append({'subject': rule.subject_actor_id, 'owner': rule.resource_owner_actor_id,
                'action': rule.business_action_id, 'effects': rule.protected_effect_ids, 'relation': rule.relation,
                'expectation': rule.expectation.value, 'active': rule.effective_state.value == 'ACTIVE',
                'reference': {'intent_id': rule.intent_id, 'revision': rule.revision, 'intent_hash': rule.intent_hash}})
    else:
        if reference.kind == 'CANDIDATE':
            value = candidate_service._required(work, project_id, reference.candidate_id, reference.revision)
            draft = candidate_service._boundaries.maintenance_draft(project_id, work=work, allow_empty=True)
            if value.basis_id != 'rb_' + draft.boundary_state_fingerprint:
                return {'availability':'STALE', 'coverage':None, 'matches':[], 'actors':[], 'actions':[]}
            view = candidate_service._view(work, value)
            if any(item['code'] == 'CONTEXT_STALE' for item in view['issues']):
                return {'availability':'STALE', 'coverage':None, 'matches':[], 'actors':[], 'actions':[]}
            if view['issues']:
                return {'availability':'NEEDS_DECISION', 'coverage':None, 'matches':[], 'actors':[], 'actions':[]}
            merged = candidate_service._merge(value, draft)
            source_actors, source_actions, source_permissions = merged.actors, merged.actions, merged.permissions
        else:
            proposal = work.business_boundaries.get_proposal(reference.proposal_id)
            if proposal is None or proposal.project_id != project_id:
                raise JiejianError(ErrorCode.RECORD_NOT_FOUND, '指定提案不存在')
            if proposal.unresolved_questions:
                return {'availability':'NEEDS_DECISION', 'coverage':None, 'matches':[], 'actors':[], 'actions':[]}
            source_actors, source_actions, source_permissions = proposal.proposed_actors, proposal.proposed_actions, proposal.proposed_permissions
        actor_labels = {item.item_id: item.display_name for item in source_actors}
        for action in source_actions:
            effects = action.effects if reference.kind == 'CANDIDATE' else action.effect_catalog
            actions[action.item_id] = {'id':action.item_id, 'label':action.display_name,
                'effects':[{'id':item.item_id, 'label':item.business_label} for item in effects]}
        permissions = [{'subject':item.subject_actor_item_id, 'owner':item.resource_owner_actor_item_id,
            'action':item.business_action_item_id, 'effects':item.protected_effect_item_ids, 'relation':item.relation,
            'expectation':item.expectation.value, 'active':item.effective_state.value == 'ACTIVE',
            'reference':{**reference.model_dump(mode='json'), 'permission_item_id':item.item_id}} for item in source_permissions]
    result = {'availability':'AVAILABLE', 'coverage':None, 'matches':[],
        'actors':[{'id':key,'label':label} for key,label in actor_labels.items()], 'actions':list(actions.values()),
        'reference':reference.model_dump(mode='json')}
    situation = command.situation
    if situation is None:
        return result
    action = actions.get(situation.action_id)
    if situation.subject_id not in actor_labels or situation.owner_id not in actor_labels or action is None or situation.effect_id not in {item['id'] for item in action['effects']}:
        raise JiejianError(ErrorCode.INPUT_INVALID, '情境必须引用指定规则集中的角色、动作与后果')
    if not permission_relation_consistent(situation.relation, (situation.subject_id, 1), (situation.owner_id, 1)):
        raise JiejianError(ErrorCode.INPUT_INVALID, '资源关系与两个角色不一致')
    matches = [item for item in permissions if item['active'] and item['subject'] == situation.subject_id
        and item['owner'] == situation.owner_id and item['action'] == situation.action_id
        and item['relation'] == situation.relation and situation.effect_id in item['effects']]
    expectations = {item['expectation'] for item in matches}
    result['coverage'] = 'UNCOVERED' if not expectations else next(iter(expectations)) if len(expectations) == 1 else 'CONFLICT'
    result['matches'] = [item['reference'] for item in matches]
    return result
