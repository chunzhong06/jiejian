"""只从同次已验证报告整理交付清单，逐项保留要求、正常功能及原题引用。"""
from typing import Literal
from urllib.parse import urlencode
from product.protocols.checks.execution_request import WireModel, PermissionReference


class DeliveryItem(WireModel):
    review_url: str | None = None
    source_key: str | None = None
    historical_name_available: bool = True
    kind: Literal['PERMISSION', 'NORMAL', 'REPAIR', 'UNCHECKED', 'UNRESOLVED', 'RUNTIME']
    label: str
    result: str
    case_ids: tuple[str, ...] = ()
    permission: PermissionReference | None = None
    source_run_id: str | None = None
    source_case_id: str | None = None


def delivery_items(story, historical_labels=None):
    """结果文字复制正式事实；不合成额外通过率、分数或发布结论。"""
    items = []
    historical_labels = historical_labels or {}
    requirements = {scope.candidate_id+'@'+str(scope.revision)+'/'+item.requirement_id:item.requirement
        for scope in story.requirement_scope for item in scope.requirements}
    requirement_urls = {scope.candidate_id+'@'+str(scope.revision)+'/'+item.requirement_id:
        '/permissions?'+urlencode(dict(candidate_id=scope.candidate_id,revision=scope.revision))
        for scope in story.requirement_scope for item in scope.requirements}
    for action in story.actions:
        rule = action.permission
        subject = action.fact_comparison.planned_identity.label or action.fact_comparison.planned_identity.actor_label or '本次主体'
        label = subject + ' · ' + action.display_name + ' · ' + (action.fact_comparison.resource_id or '本次资源')
        items.append(DeliveryItem(kind='NORMAL' if rule.expectation == 'ALLOW' else 'PERMISSION',
            label=label, result=action.judgement, case_ids=(action.case_id,),
            permission=PermissionReference(intent_id=rule.intent_id, revision=rule.revision, intent_hash=rule.intent_hash)))
    for review in story.repair_reviews:
        items.append(DeliveryItem(kind='REPAIR', label='原问题修复', result=review.verification.status,
            source_run_id=review.reference.source_run_id, source_case_id=review.reference.source_case_id,
            case_ids=tuple(dict.fromkeys(row.after_case_id for row in review.comparison if row.after_case_id is not None))))
    if story.selection is not None:
        for rule in story.selection.omitted:
            label=historical_labels.get((rule.intent_id,rule.revision,rule.intent_hash))
            items.append(DeliveryItem(kind='UNCHECKED', label=label or '历史要求名称未保存 · 修订 '+str(rule.revision),
                result='本次主动未选，未执行', permission=rule, historical_name_available=label is not None,
                review_url='/permissions?'+urlencode(dict(rule_id=rule.intent_id,revision=rule.revision,intent_hash=rule.intent_hash))))
        for key in story.selection.uncovered_requirements:
            items.append(DeliveryItem(kind='UNCHECKED', label=requirements.get(key,'历史业务要求名称未保存'), source_key=key,
                result='已确认要求未由本次范围覆盖',historical_name_available=key in requirements,review_url=requirement_urls.get(key)))
        for key in story.selection.pending_review_ids:
            # 旧冻结选择只保存 issue_id 时无法反推出历史候选，不能把当前首项当成原审阅。
            items.append(DeliveryItem(kind='UNRESOLVED', label=requirements.get(key,'待审业务要求（历史名称未保存）'), source_key=key,
                result='业务要求仍待审阅，未纳入本次判断'+('；历史审阅对象未保存，请按原事项引用核对' if key not in requirement_urls else ''),
                historical_name_available=key in requirements,review_url=requirement_urls.get(key)))
    discovery = story.discovery_coverage
    if discovery is not None:
        items.extend(DeliveryItem(kind='UNRESOLVED', label=item.label,
            source_key=item.key, review_url=('/application?'+urlencode(dict(view='sources',source_id=item.source_id,request_id=item.request_id))
                if item.kind=='REQUEST' else '/application?'+urlencode(dict(view='business',candidate_id=item.candidate_id or ''))),
            result='待核对业务含义' if item.status == 'PENDING' else '来源变化，需要重核')
            for item in discovery.items if item.status in {'PENDING', 'RECHECK'})
        if discovery.omitted_count:
            items.append(DeliveryItem(kind='UNRESOLVED', label='线索清单其余项目', review_url='/application?view=business', result='摘要省略 ' + str(discovery.omitted_count) + ' 项，请阅读本报告的完整计数'))
    items.append(DeliveryItem(kind='RUNTIME', label='实际运行与交付对应',
        result={'MATCHED':'运行代码已核对', 'UNCONFIRMED':'运行对应尚未确认', 'UNSUPPORTED':'本次没有独立运行对应证明'}[story.runtime_status]))
    return tuple(items)


def historical_permission_labels(work, project_id, references):
    """名称只取准确历史修订；当前重命名或缺少历史都不能补写成当时事实。"""
    labels={}
    for reference in references:
        rule=work.permission_intents.get_revision(reference.intent_id,reference.revision)
        if rule is None or rule.project_id!=project_id or rule.intent_hash!=reference.intent_hash:
            continue
        actor=work.business_boundaries.actor_revision(rule.subject_actor_id,rule.subject_actor_revision)
        owner=work.business_boundaries.actor_revision(rule.resource_owner_actor_id,rule.resource_owner_actor_revision)
        action=work.business_boundaries.action_revision(rule.business_action_id,rule.action_revision)
        if actor is None or owner is None or action is None:
            continue
        resource='自己的' if rule.relation=='OWNS' else '同角色其他账号的' if rule.relation=='SAME_ROLE_OTHER_ACCOUNT' else owner.display_name+'的'
        label=actor.display_name+('可以' if rule.expectation=='ALLOW' else '不得')+'对'+resource+action.primary_resource_concept+'执行“'+action.display_name+'”'
        if rule.conditions is not None and rule.conditions.resource_states:
            label+='；适用状态：'+'、'.join(rule.conditions.resource_states)
        labels[reference.intent_id,reference.revision,reference.intent_hash]=label
    return labels
