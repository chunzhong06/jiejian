"""发送前核对已冻结场景及当前身份、环境和业务修订，不执行目标请求。"""
from product.backend.domain.identities.models import identity_source_fingerprint
from product.backend.domain.lifecycle import ProjectStatus


def trial_inputs_current(work,request):
    plan,flow=request.plan,request.plan.flow
    project=work.projects.get(flow.project_id)
    if project is None or project.status is ProjectStatus.ARCHIVED:return False
    current=work.operation_flows.get(flow.id,flow.revision)
    understanding=work.application_understanding.get(flow.project_id)
    action=work.business_boundaries.action(flow.business_action_id)
    if (current!=flow or understanding is None or action is None or action.current_revision!=flow.action_revision
        or understanding.source_fingerprint!=flow.source_fingerprint or understanding.environment!=flow.environment
        or understanding.confirmed_endpoint!=flow.target_scope.base_url):return False
    for item in plan.runtime.identities:
        record=work.test_identities.get(item.identity_id)
        actor=work.business_boundaries.actor(item.actor_id)
        if (record is None or record.project_id!=flow.project_id or record.prepared_at_us is None
            or record.updated_at_us!=plan.identity_updated_at_us[item.identity_id]
            or identity_source_fingerprint(record)!=item.identity_fingerprint
            or actor is None or actor.current_revision!=item.actor_revision):return False
    if flow.source_request is not None:
        import hashlib
        from product.protocols.codec import encode_json
        reference=flow.source_request
        latest=next(iter(work.api_sources.latest(flow.project_id,reference.source_id)),None)
        original=latest if latest is not None and latest.revision==reference.revision else work.api_sources.revision(flow.project_id,reference.source_id,reference.revision)
        for source in ((latest,) if original is latest else (original,latest)):
            value=None if source is None else next((item for item in source.requests if item.item_id==reference.item_id),None)
            if value is None or hashlib.sha256(encode_json(value.model_dump(mode='json'))).hexdigest()!=reference.request_fingerprint:return False
    return True
