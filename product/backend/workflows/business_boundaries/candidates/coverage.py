# 将人的覆盖要求映射到精确正式规则、TARGET入口与证明；仅判断检查就绪，不产生安全结论。
import re
from product.backend.core.boundaries.candidate_reviews import boundary_review_items
from product.backend.core.boundaries.candidate_scope import scope_items, only_auxiliary_scope


def coverage_items(value):
    links = {item.issue_id: item for item in getattr(value, 'coverage_links', ())}
    permissions = {item.item_id: item for item in value.content.permissions if item.effective_state.value == 'ACTIVE'}
    result = []
    for review in boundary_review_items(value):
        link = links.get(review['issue_id'])
        if link is None:
            continue
        current = (link.issue_fingerprint == review['issue_fingerprint'] and review['status'] == 'OPEN'
            and review['decision'].output_revision == link.review_revision
            and review['decision'].outcome in {'PREPARATION_DEPENDENCY', 'EVIDENCE_GAP', 'COVERAGE_GAP'}
            and {target.permission_item_id for target in link.targets} <= permissions.keys())
        status = 'STALE' if not current else 'UNSUPPORTED_HISTORY' if link.time_scope == 'HISTORY' else 'DRAFT' if not link.complete else 'PLANNED'
        result.append({'issue_id': review['issue_id'], 'status': status, 'link': link,
            'message': '业务依据已变化，请重新关联' if not current else '任意历史范围仍不受支持，不能转为本次过程检查' if status == 'UNSUPPORTED_HISTORY' else '关联清单尚未确认完整，继续保留阻塞；可补充其他权限与入口' if status == 'DRAFT' else '规则可审阅；批准后逐项核验入口与证明，尚未检查'})
    return result


def path_shape(path):
    # 只规范完整路径段占位，不把setup步骤或前缀匹配当作目标接口。
    return '/'.join('{}' if re.fullmatch(r'\{[A-Za-z_][A-Za-z0-9_]*\}', part) else part for part in path.split('/'))


def coverage_ready(work, value, issue_id, plan, bundle):
    item = next((item for item in coverage_items(value) if item['issue_id'] == issue_id), None)
    if item is None or item['status'] != 'PLANNED':
        return False
    proposal_id = work.rule_candidates.proposal_id(value.candidate_id, value.revision)
    decision = None if proposal_id is None else work.business_boundaries.decision_for_proposal(proposal_id)
    if decision is None or decision.decision.value != 'APPROVED' or plan is None or bundle is None:
        return False
    mappings = {item['permission_item_id']: item for item in work.rule_candidates.approval_mappings(proposal_id=proposal_id)}
    actions = {action.action_id: action for action in bundle.actions}
    for target in item['link'].targets:
        mapping = mappings.get(target.permission_item_id)
        if mapping is None:
            return False
        found = False
        for action in plan.actions:
            if action.gaps:
                continue
            config = actions.get(action.action_id)
            if config is None or (config.action_revision, config.action_semantic_fingerprint) != (action.action_revision, action.action_semantic_fingerprint):
                continue
            if not any(step.purpose == 'TARGET' and step.request.method == target.method and path_shape(step.request.path) == path_shape(target.path) for step in config.steps):
                continue
            cases = [case for case in action.cases if (case.permission.intent_id, case.permission.revision, case.permission.intent_hash) == (mapping['intent_id'], mapping['revision'], mapping['intent_hash'])]
            if not cases:
                continue
            if target.proof == 'PROCESS_RECORD':
                # 普通最终状态快照不能证明曾经发生；要求受控事务记录且至少保护一个状态变化效果。
                states = [proof for proof in config.proofs if proof.effect_kind == 'STATE_MUTATION' and any(proof.effect_id in case.protected_effect_ids for case in cases)]
                if not states or any(not any(source.config.source_kind == 'MANAGED_TRANSACTION_RECORDS'
                    and source.config.action_id == action.action_id and source.config.effect_id == proof.effect_id
                    and source.source_fingerprint == proof.descriptor_fingerprint for source in getattr(bundle, 'json_sources', ())) for proof in states):
                    continue
            found = True
            break
        if not found:
            return False
    return True


def frozen_requirement_scope(work, project_id):
    from product.protocols.checks.execution_request import FrozenRequirementScope, FrozenRequirement, PermissionReference
    result = []
    for head in work.rule_candidates.head_references(project_id):
        value = work.rule_candidates.get(project_id, head['candidate_id'], head['revision'])
        items = scope_items(value)
        if not items:
            continue
        proposal_id = work.rule_candidates.proposal_id(value.candidate_id, value.revision)
        decision = None if proposal_id is None else work.business_boundaries.decision_for_proposal(proposal_id)
        if (decision is None or decision.decision.value != 'APPROVED') and not only_auxiliary_scope(value):
            continue
        mapping = {} if proposal_id is None else {v['permission_item_id']: v for v in work.rule_candidates.approval_mappings(proposal_id=proposal_id)}
        requirements = []
        for item in items:
            if item['status'] != 'CONFIRMED':
                continue
            choice = item['decision']
            # 补充依据不是独立检查要求；原文及其精确人工关联留在本次候选修订供追溯。
            if choice.disposition == 'SUPPORTING':
                continue
            permissions = tuple(PermissionReference(intent_id=mapping[key]['intent_id'], revision=mapping[key]['revision'], intent_hash=mapping[key]['intent_hash'])
                for key in item['source'].permission_item_ids if key in mapping) if choice.disposition == 'IN_SCOPE' else ()
            requirements.append(FrozenRequirement(requirement_id=choice.requirement_id, requirement=choice.requirement,
                disposition=choice.disposition, time_scope=choice.time_scope, permissions=permissions))
        if requirements:
            result.append(FrozenRequirementScope(candidate_id=value.candidate_id, revision=value.revision, requirements=tuple(requirements)))
    return tuple(result)
