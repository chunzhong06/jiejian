# 将既有准备视图与当前业务标签组合为只读详情；跨读取漂移只影响本次详情。
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.preparation.evidence_models import EvidenceMaterialDetail, EffectMaterialSummary
from product.backend.workflows.preparation.models import PreparationStatus


def evidence_details(service, project_id: str, action_id: str) -> EvidenceMaterialDetail:
    prepared = next((item for item in service.get(project_id).actions if item.action_id == action_id), None)
    boundary = service._business_boundaries.view(project_id)
    action = next((item for item in boundary.actions
                   if item.action_id == action_id and item.project_id == project_id), None)
    if prepared is None or action is None:
        raise JiejianError(ErrorCode.APPLICATION_CANDIDATE_NOT_FOUND, "当前业务动作不存在")
    changed = (prepared.action_revision != action.revision or
               prepared.assurance_contract.action_semantic_fingerprint != action.semantic_fingerprint)
    if not changed and service._bindings is not None:
        effects = service._bindings.describe_evidence(action, prepared.effect_evidence)
    else:
        views = {item.effect_id: item for item in prepared.effect_evidence}
        effects = tuple(EffectMaterialSummary(effect_id=effect.effect_id, business_label=effect.business_label,
            resource_concept=effect.resource_concept,
            material_status=PreparationStatus.STALE if changed else views[effect.effect_id].status,
            reason_codes=("EVIDENCE_SNAPSHOT_CHANGED",) if changed else views[effect.effect_id].reason_codes)
            for effect in action.effect_catalog if changed or effect.effect_id in views)
    return EvidenceMaterialDetail(project_id=project_id, action_id=action.action_id,
        action_revision=action.revision, action_label=action.display_name, effects=effects)
