"""把准确业务要求组织为只读验证方案；能力、材料与待确认问题各自保留依据。"""
from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from product.backend.domain.boundaries.entities import BoundaryModel, boundary_sha256
from product.backend.domain.boundaries.candidate_scope import scope_items


class ValidationEffect(BoundaryModel):
    configured_path: str | None = None
    configuration_present: bool = False
    capability_status: Literal['CONFIGURED', 'NEEDS_CONFIGURATION', 'NEEDS_RECHECK', 'UNSUPPORTED'] = 'NEEDS_CONFIGURATION'
    item_id: str
    label: str
    kind: str
    requirement: str
    supported_paths: tuple[str, ...]
    protected_fields: tuple[str, ...]
    material_status: str
    reason_codes: tuple[str, ...] = ()


class ValidationRequirement(BoundaryModel):
    definition_changes: tuple[str, ...] = ()
    environment_summary: str = ''
    preparation_summary: str = ''
    item_id: str
    intent_id: str | None
    revision: int | None
    action_id: str | None
    action_item_id: str
    action_label: str
    sentence: str
    expectation: str
    relation: str
    conditions: dict | None
    effects: tuple[ValidationEffect, ...]
    normal_control: str
    preparation_requirements: tuple[str, ...]
    preparation_url: str
    current_materials: tuple[dict, ...]


class ValidationQuestion(BoundaryModel):
    requirement_id: str
    fingerprint: str
    action_item_id: str
    dimension: str
    question: str
    basis: str
    source_excerpt: str
    status: Literal['NEEDS_DECISION', 'DEFERRED', 'EXCLUDED', 'IN_REVIEW', 'RECHECK']
    review_url: str | None = None
    decision_reason: str | None = None


class ValidationPlan(BoundaryModel):
    project_id: str
    basis_id: str
    fingerprint: str
    candidate_id: str | None
    candidate_revision: int | None
    state: Literal['CURRENT', 'STALE']
    requirements: tuple[ValidationRequirement, ...]
    questions: tuple[ValidationQuestion, ...]
    scope: str
    draft_fingerprint: str | None = None


class OpenValidationQuestion(BoundaryModel):
    operation_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    expected_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    question_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    candidate_id: str | None = Field(default=None, pattern=r'^rcd_[0-9a-f]{32}$')
    revision: int | None = Field(default=None, ge=1)

    @model_validator(mode='after')
    def exact_candidate(self):
        if (self.candidate_id is None) != (self.revision is None):
            raise ValueError('candidate and revision must be supplied together')
        return self


# 这里只声明已有证明合同的用途，来源存在及当前可用性由原准备服务现场核对。
PROOF_REQUIREMENTS = {
    'DATA_DISCLOSURE': ('所有者独立只读参照与目标响应对应同一资源，核对已声明的受保护字段。',
                        ('HTTP_ENTITY_QUERY', 'RESOURCE_FIELDS_V1')),
    'STATE_MUTATION': ('读取本次受保护字段的完整提交事实；禁止场景需要确认未发生独立提交，正常场景确认预期修改。',
                       ('TRANSACTION_HISTORY_V2',)),
    'OBJECT_CREATION': ('将本次新对象关联到真实主体与资源，并取得完整创建记录。', ('OBJECT_CREATION_V1',)),
    'FILE_CONTENT_DELIVERY': ('核对实际交付文件与受保护内容参照、关联和完整性；异步交付还需有界等待与任务对应。',
                              ('FILE_RESPONSE_CONTENT_V1',)),
}


def _question_specs(action, permissions):
    """只沿已经出现的关系提出相邻问题；不枚举所有角色、资源和条件的组合。"""
    result = []
    by_subject = {}
    for rule in permissions:
        by_subject.setdefault(rule.subject_actor_item_id, []).append(rule)
    for subject, rows in by_subject.items():
        owns = [row for row in rows if row.relation == 'OWNS']
        if any(not any(other.relation == 'SAME_ROLE_OTHER_ACCOUNT' and other.conditions == own.conditions
            and set(other.protected_effect_item_ids) >= set(own.protected_effect_item_ids) for other in rows) for own in owns):
            result.append(('OTHER_ACCOUNT:' + subject, '同角色的另一个账号能否对他人的这类资源执行该操作？',
                           '已有本人资源要求，尚未说明同角色其他账号访问该资源的边界。'))
        tenants = {row.conditions.tenant for row in rows if row.conditions is not None and row.conditions.tenant}
        if tenants in ({'SAME'}, {'DIFFERENT'}):
            result.append(('TENANT_BOUNDARY:' + subject, '同组织与跨组织或租户时，这项操作的权限边界分别是什么？',
                           '当前只说明了' + ('同租户' if tenants == {'SAME'} else '跨租户') + '条件，另一种情况尚待核对。'))
        if any(row.conditions is not None and row.conditions.resource_states for row in rows) and len({row.expectation for row in rows}) == 1:
            result.append(('RESOURCE_STATE:' + subject, '资源进入其他业务状态后，这项允许或禁止要求是否仍然适用？',
                           '已有明确资源状态条件，需要核对状态变化后的业务边界。'))
        relationships = [rel for row in rows if row.conditions for rel in row.conditions.relationships]
        for kind, label in (('SHARING', '共享'), ('DELEGATION', '委托'), ('ORGANIZATION', '组织关系'), ('ROLE_INHERITANCE', '角色继承')):
            states = {rel.state for rel in relationships if rel.kind == kind}
            if 'ACTIVE' in states and not states.intersection({'ABSENT', 'REVOKED', 'EXPIRED'}):
                result.append((kind + ':' + subject, label + '不再有效时，这项访问应当怎样处理？',
                               '已有有效' + label + '条件，尚未说明关系失效后的访问。'))
    return result


def validation_questions(work, project_id, draft, *, candidate=None):
    actors = {item.item_id: item for item in draft.actors}
    result = []
    heads = work.rule_candidates.head_references(project_id)
    reviewed = [work.rule_candidates.get(project_id, head['candidate_id'], head['revision']) for head in heads]
    understanding = work.application_understanding.get(project_id)
    for action in draft.actions:
        if action.effective_state != 'ACTIVE':
            continue
        rules = tuple(item for item in draft.permissions if item.effective_state == 'ACTIVE' and item.business_action_item_id == action.item_id)
        actor_ids = {key for rule in rules for key in (rule.subject_actor_item_id, rule.resource_owner_actor_item_id)}
        related = {'action': action.model_dump(mode='json'), 'rules': [item.model_dump(mode='json') for item in rules],
                   'actors': [actors[key].model_dump(mode='json') for key in sorted(actor_ids)]}
        source_ids = set(action.source_candidate_ids) | {key for actor_id in actor_ids for key in actors[actor_id].source_candidate_ids}
        related['sources'] = [] if understanding is None else [item.model_dump(mode='json')
            for item in (*understanding.role_candidates, *understanding.action_candidates) if item.candidate_id in source_ids]
        for dimension, question, reason in _question_specs(action, rules):
            requirement_id = 'req_' + boundary_sha256([action.item_id, dimension])[:16]
            fingerprint = boundary_sha256([requirement_id, related])
            excerpt = '权限边界核对 ' + requirement_id + ' / ' + fingerprint
            prior = []
            for value in reviewed:
                for item in scope_items(value):
                    if item['source'].requirement_id == requirement_id:
                        prior.append((value, item))
            same = [(value, item) for value, item in prior if item['source'].source_excerpt == excerpt]
            matched = max(same, key=lambda pair: pair[0].created_at_us, default=None)
            status, url, decision_reason = ('RECHECK' if prior else 'NEEDS_DECISION'), None, None
            if matched:
                value, item = matched
                decision = item['decision']
                status = 'EXCLUDED' if item['status'] == 'CONFIRMED' and decision.disposition == 'OUT_OF_SCOPE' else 'DEFERRED' if decision is not None and decision.disposition == 'DEFER' else 'IN_REVIEW'
                decision_reason = None if decision is None else decision.reason
                url = '/permissions?project_id=' + project_id + '&candidate_id=' + value.candidate_id + '&revision=' + str(value.revision)
            result.append(ValidationQuestion(requirement_id=requirement_id, fingerprint=fingerprint,
                action_item_id=action.item_id, dimension=dimension, question=question,
                basis=action.display_name + '：' + reason, source_excerpt=excerpt,
                status=status, review_url=url, decision_reason=decision_reason))
    return tuple(result)


def build_validation_plan(work, draft, preparation, *, candidate=None, intent_id=None, formal=None):
    """评估配置需求而非执行事实；候选改义时不借用正式动作的就绪状态。"""
    project_id = draft.project_id
    actors = {item.item_id: item for item in draft.actors}
    actions = {item.item_id: item for item in draft.actions}
    prepared = {} if preparation is None else {item.action_id: item for item in preparation.actions}
    formal = formal or draft
    formal_actions = {item.item_id: item for item in formal.actions}
    formal_rules = {item.item_id: item for item in formal.permissions}
    understanding = work.application_understanding.get(project_id)
    environment = None if understanding is None else understanding.environment
    items = []
    for rule in draft.permissions:
        if rule.effective_state != 'ACTIVE' or intent_id is not None and rule.intent_id != intent_id:
            continue
        if candidate is not None and rule.item_id not in {item.item_id for item in candidate.content.permissions}:
            continue
        action = actions[rule.business_action_item_id]
        current = prepared.get(action.action_id)
        formal_action, formal_rule = formal_actions.get(action.item_id), formal_rules.get(rule.item_id)
        changes = []
        if action != formal_action:
            changes.append('操作或受保护结果定义变化')
        if formal_rule is None:
            changes.append('新增权限要求，需核对现有材料的适用范围')
        else:
            for names, label in (
                (('subject_actor_item_id','resource_owner_actor_item_id','relation'), '操作主体或资源归属变化'),
                (('expectation','protected_effect_item_ids'), '业务预期或受保护结果变化'),
                (('conditions',), '适用条件变化，需补对应样本及条件观察')):
                if any(getattr(rule,name) != getattr(formal_rule,name) for name in names):
                    changes.append(label)
        exact = not changes
        # 原配置可继续阅读；变更后的定义不得继承旧材料的就绪结论。
        current = current if current is not None and current.action_revision == action.expected_current_revision else None
        effects = []
        for effect in action.effects:
            if effect.item_id not in rule.protected_effect_item_ids:
                continue
            requirement, paths = PROOF_REQUIREMENTS.get(effect.effect_kind.value, ('需要独立的完整业务事实来源；当前通用准备入口没有对应的证明合同。', ()))
            material = None if current is None else next((item for item in current.effect_evidence if item.effect_id == effect.effect_id), None)
            binding = None if action.action_id is None or action.expected_current_revision == 0 or effect.effect_id is None else work.action_preparation.evidence(action.action_id, action.expected_current_revision, effect.effect_id)
            configured = None if binding is None else binding.kind.value
            status = 'NEEDS_SOURCE' if material is None else material.status.value
            reasons = () if material is None else material.reason_codes
            if not exact and material is not None:
                status, reasons = 'STALE', (*reasons, 'REQUIREMENT_CHANGED')
            if not paths and material is not None and material.status == 'SATISFIED':
                paths = ('REGISTERED_OBSERVER',)
            elif not paths:
                status = 'UNSUPPORTED'
            incompatible_http = configured == 'HTTP_ENTITY_QUERY' and effect.effect_kind.value != 'DATA_DISCLOSURE'
            capability = 'UNSUPPORTED' if not paths or incompatible_http else 'NEEDS_CONFIGURATION' if binding is None else 'CONFIGURED' if status == 'SATISFIED' else 'NEEDS_RECHECK'
            if incompatible_http:
                requirement += ' 当前仅配置 HTTP 实体查询，需另补对应提交或历史事实来源。'
            effects.append(ValidationEffect(item_id=effect.item_id, label=effect.business_label, kind=effect.effect_kind.value,
                configured_path=configured, configuration_present=binding is not None, capability_status=capability,
                requirement=requirement, supported_paths=paths, protected_fields=effect.protected_projection or
                    (() if effect.field_mutation is None else (effect.field_mutation.path,)), material_status=status, reason_codes=reasons))
        subject, owner = actors[rule.subject_actor_item_id].display_name, actors[rule.resource_owner_actor_item_id].display_name
        resource = '自己的' if rule.relation == 'OWNS' else '同角色其他账号的' if rule.relation == 'SAME_ROLE_OTHER_ACCOUNT' else owner + '的'
        needs = ['核验操作主体与资源所有者', '取得准确资源及归属', '准备业务操作流程']
        if rule.conditions is not None:
            needs.append('独立采集该要求声明的身份、租户、状态或关系条件')
        if action.state_changing:
            needs.append('准备可核对的业务恢复方式')
        materials = () if current is None else tuple({**item.model_dump(mode='json'),
            'compatible_with_definition': exact} for item in preparation.impacts
            if item.action_id == current.action_id and (rule.intent_id in item.permission_ids or not exact))
        existing = sum(item.get('handling') == 'KEEP' for item in materials)
        pending = sum(item.get('handling') != 'KEEP' for item in materials)
        controls = [other for other in draft.permissions if other.effective_state == 'ACTIVE'
            and other.expectation == 'ALLOW' and other.business_action_item_id == rule.business_action_item_id
            and other.resource_owner_actor_item_id == rule.resource_owner_actor_item_id
            and set(other.protected_effect_item_ids) >= set(rule.protected_effect_item_ids)
            and not (other.conditions is not None and rule.conditions is not None and any(
                left.kind == right.kind and left.kind in {'SHARING', 'DELEGATION'} and left.state != right.state
                for left in other.conditions.relationships for right in rule.conditions.relationships))]
        normal = ('本要求作为正常场景，确认预期业务结果。' if rule.expectation == 'ALLOW' else
            '缺少覆盖相同受保护结果的允许要求，需要先补充正常对照。' if not controls else
            '已有 ' + str(len(controls)) + ' 项覆盖相同受保护结果的允许要求；准备时按准确引用核对并选择正常对照。')
        items.append(ValidationRequirement(item_id=rule.item_id, intent_id=rule.intent_id,
            definition_changes=tuple(changes),
            environment_summary='尚未确认本次检查连接' if environment is None else '已保存连接：' + environment.target.base_url + '；实际可用性在执行前核验',
            preparation_summary=('已列 ' + str(len(materials)) + ' 项材料需求；其中 ' + str(existing) + ' 项当前满足、' + str(pending) + ' 项需补齐或重核。已有配置的保留与处理见下方明细。' +
                ('定义已变，新条件需重新核对。' if not exact else '')) if materials else '尚无可对应材料，需准备账号、具体资源、操作与证明。',
            revision=rule.expected_current_revision, action_id=action.action_id, action_item_id=action.item_id,
            action_label=action.display_name, sentence=subject + ('可以' if rule.expectation == 'ALLOW' else '不得') + '对' + resource + action.primary_resource_concept + '执行“' + action.display_name + '”。',
            expectation=rule.expectation.value, relation=rule.relation.value,
            conditions=None if rule.conditions is None else rule.conditions.model_dump(mode='json'), effects=tuple(effects),
            normal_control=normal,
            preparation_requirements=tuple(needs), current_materials=materials,
            preparation_url='/reports?view=plan&project_id=' + project_id + ('&rule_id=' + rule.intent_id if rule.intent_id else '')))
    basis = 'rb_' + draft.boundary_state_fingerprint
    state = 'STALE' if candidate is not None and candidate.basis_id != basis else 'CURRENT'
    questions = validation_questions(work, project_id, draft, candidate=candidate)
    if intent_id is not None or candidate is not None:
        action_ids = {item.action_item_id for item in items}
        questions = tuple(item for item in questions if item.action_item_id in action_ids)
    fingerprint = boundary_sha256({'basis': basis, 'candidate': None if candidate is None else candidate.model_dump(mode='json'),
        'environment': None if understanding is None or understanding.environment is None else understanding.environment.model_dump(mode='json'),
        'preparation': None if preparation is None else preparation.basis_fingerprint,
        'requirements': [item.model_dump(mode='json') for item in items], 'questions': [item.model_dump(mode='json') for item in questions]})
    return ValidationPlan(project_id=project_id, basis_id=basis, fingerprint=fingerprint,
        candidate_id=None if candidate is None else candidate.candidate_id,
        candidate_revision=None if candidate is None else candidate.revision, state=state,
        requirements=tuple(items), questions=questions,
        scope='只说明所列要求的验证方式与当前准备依据；实际检查继续使用原预览与冻结提交。')
