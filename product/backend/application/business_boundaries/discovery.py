"""从现有线索、人工决定与正式关联派生覆盖；不另存进度，不批准权限或产生安全结论。"""
import hashlib
from product.backend.domain.applications.models import CandidateDecision
from product.protocols.codec import encode_json
from product.protocols.checks.discovery import DiscoveryCoverage, DiscoveryItem
from product.backend.application.business_boundaries.candidates.coverage import path_shape


def _fingerprint(value):
    return hashlib.sha256(encode_json(value)).hexdigest()


def discovery_coverage(work, project_id, boundary, *, plan=None, bundle=None, focus_request=None):
    """调用者在同一UoW读取边界和线索；提交冻结时重读，不沿用页面核对结果。"""
    understanding = work.application_understanding.get(project_id)
    items = []
    active_actions = {permission.business_action_id for permission in boundary.permission_intents}
    active_actors = {identity for permission in boundary.permission_intents
        for identity in (permission.subject_actor_id, permission.resource_owner_actor_id)}
    bindings = {'ROLE': boundary.actor_bindings, 'ACTION': boundary.action_bindings}
    candidates = {'ROLE': understanding.role_candidates, 'ACTION': understanding.action_candidates}
    for kind, values in candidates.items():
        for candidate in values:
            # 消失的发现不是新增业务；既有正式实现失效仍由原绑定门禁处理。
            if candidate.stale or kind == 'ACTION' and candidate.evidence and all(e.detector == 'API_SOURCE' for e in candidate.evidence):
                continue
            linked = [binding for binding in bindings[kind] if candidate.candidate_id in binding.source_candidate_ids
                and (binding.actor_id in active_actors if kind == 'ROLE' else binding.action_id in active_actions)]
            status = ('RELATED' if all(binding.status == 'CURRENT' for binding in linked) else 'RECHECK') if linked else (
                'EXCLUDED' if candidate.decision is CandidateDecision.REJECTED else 'RECHECK' if candidate.decision is CandidateDecision.REVIEW_REQUIRED else 'PENDING')
            items.append(DiscoveryItem(key=kind+':'+candidate.candidate_id, kind=kind, label=candidate.display_name,
                status=status, fingerprint=_fingerprint(candidate.model_dump(mode='json')), candidate_id=candidate.candidate_id,
                action_id=linked[0].action_id if kind == 'ACTION' and linked else None))
    annotations = {(item['source_id'], item['item_id']): item for item in work.api_sources.annotations(project_id)}
    action_bindings = {binding.action_id: binding for binding in boundary.action_bindings}
    executed = {} if bundle is None else {action.action_id: {(step.request.method, path_shape(step.request.path))
        for step in action.steps if step.purpose == 'TARGET'} for action in bundle.actions}
    planned = set() if plan is None else {action.action_id for action in plan.actions if action.cases and not action.gaps}
    for source in work.api_sources.latest(project_id):
        for request in source.requests:
            digest = _fingerprint(request.model_dump(mode='json'))
            matches = [candidate for candidate in understanding.action_candidates if not candidate.stale and any(
                evidence.detector == 'API_SOURCE' and evidence.relative_path == 'api-sources/'+source.source_id
                and evidence.symbol == request.pointer and evidence.content_sha256 == digest for evidence in candidate.evidence)]
            annotation = annotations.get((source.source_id, request.item_id))
            action_id = None if annotation is None else annotation['action_id']
            if action_id is None:
                matched_actions = {binding.action_id for binding in boundary.action_bindings
                    if binding.action_id in active_actions and any(candidate.candidate_id in binding.source_candidate_ids for candidate in matches)}
                action_id = next(iter(matched_actions)) if len(matched_actions) == 1 else None
            linked = (action_id in active_actions and bool(matches)
                and action_bindings[action_id].status == 'CURRENT'
                and all(candidate.decision is not CandidateDecision.REJECTED for candidate in matches))
            status = 'RELATED' if linked else 'RECHECK' if action_id else 'EXCLUDED' if any(candidate.decision is CandidateDecision.REJECTED for candidate in matches) else 'PENDING'
            items.append(DiscoveryItem(key='REQUEST:'+source.source_id+':'+request.item_id, kind='REQUEST',
                label=annotation['label'] if annotation and annotation['label'] else request.label, status=status,
                fingerprint=_fingerprint(dict(request=digest, source_revision=source.revision, annotation=annotation,
                    decisions=[(candidate.candidate_id,candidate.decision.value) for candidate in matches])),
                source_id=source.source_id, request_id=request.item_id, action_id=action_id,
                candidate_id=matches[0].candidate_id if matches else None,
                in_execution=None if plan is None else linked and action_id in planned and (
                    request.method, path_shape(request.path)) in executed.get(action_id, set())))
    if not items:
        return None
    # 待处理项优先展示；完整清单仍参与摘要，超过展示预算不是默默丢弃。
    order = {'PENDING': 0, 'RECHECK': 1, 'RELATED': 2, 'EXCLUDED': 3}
    items.sort(key=lambda item: (order[item.status], item.key))
    fingerprint=_fingerprint([item.model_dump(mode='json') for item in items])
    # 详情必须读到指定请求，即使它排在摘要预算之外；展示次序不改变完整清单身份。
    visible=items if focus_request is None else sorted(items,key=lambda item:(item.source_id,item.request_id)!=focus_request)
    return DiscoveryCoverage(fingerprint=fingerprint,
        pending_count=sum(item.status == 'PENDING' for item in items),
        related_count=sum(item.status == 'RELATED' for item in items),
        excluded_count=sum(item.status == 'EXCLUDED' for item in items),
        recheck_count=sum(item.status == 'RECHECK' for item in items),
        unexecuted_request_count=None if plan is None else sum(item.kind == 'REQUEST' and item.status == 'RELATED'
            and not item.in_execution for item in items), items=tuple(visible[:128]), omitted_count=max(0,len(items)-128))
