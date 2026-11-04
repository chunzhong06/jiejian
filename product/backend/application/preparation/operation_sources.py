"""只读核对流程修订、采用事实与接口来源；与流程写入服务分开，供材料和执行共用。"""
from product.backend.domain.boundaries.entities import boundary_sha256
from product.backend.domain.errors import ErrorCode, JiejianError


def source_request_current(work, document):
    reference = document.source_request
    if reference is None:
        return True
    import hashlib
    from product.protocols.codec import encode_json
    latest = next(iter(work.api_sources.latest(document.project_id, reference.source_id)), None)
    original = latest if latest is not None and latest.revision == reference.revision else work.api_sources.revision(document.project_id, reference.source_id, reference.revision)
    for source in ((latest,) if original is latest else (original, latest)):
        request = None if source is None else next((item for item in source.requests if item.item_id == reference.item_id),None)
        if request is None or hashlib.sha256(encode_json(request.model_dump(mode='json'))).hexdigest() != reference.request_fingerprint:
            return False
    return True


def load_operation_material(work,binding):
    flow=work.operation_flows.get(binding.operation_flow_id,binding.operation_flow_revision)
    if flow is None or not work.operation_flows.adopted(flow.id,flow.revision):
        raise JiejianError(ErrorCode.STATE_PRECONDITION,'操作流程修订不可用')
    if hasattr(binding,'flow_sha256') and boundary_sha256(flow.model_dump(mode='json'))!=binding.flow_sha256:
        raise JiejianError(ErrorCode.STATE_PRECONDITION,'操作流程内容已变化')
    return flow


