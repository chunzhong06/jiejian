# 将既有准备视图与当前业务标签组合为只读详情；跨读取漂移只影响本次详情。
from typing import Literal

from pydantic import Field

from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.domain.boundaries.entities import BoundaryModel, BusinessActionRevision
from product.backend.application.preparation.models import ActionPreparationView, PreparationStatus


class EffectMaterialSummary(BoundaryModel):
    effect_id: str
    business_label: str
    resource_concept: str
    material_status: PreparationStatus
    binding_fingerprint: str | None = None
    source_kind: Literal["RECORDED_OBSERVATION", "REGISTERED_OBSERVER"] | None = None
    source_label: str = "尚无证明材料"
    registered_source_available: bool | None = None
    closure_supported: bool | None = None
    resource_correlation_supported: bool | None = None
    reason_codes: tuple[str, ...] = ()


class EvidenceMaterialDetail(BoundaryModel):
    project_id: str
    action_id: str
    action_revision: int = Field(ge=1)
    action_label: str
    effects: tuple[EffectMaterialSummary, ...]


def evidence_details(
    project_id: str, prepared: ActionPreparationView | None,
    action: BusinessActionRevision | None, bindings,
) -> EvidenceMaterialDetail:
    if prepared is None or action is None:
        raise JiejianError(ErrorCode.APPLICATION_CANDIDATE_NOT_FOUND, "当前业务动作不存在")
    changed = (prepared.action_revision != action.revision or
               prepared.assurance_contract.action_semantic_fingerprint != action.semantic_fingerprint)
    if not changed and bindings is not None:
        effects = bindings.describe_evidence(action, prepared.effect_evidence)
    else:
        views = {item.effect_id: item for item in prepared.effect_evidence}
        effects = tuple(EffectMaterialSummary(effect_id=effect.effect_id, business_label=effect.business_label,
            resource_concept=effect.resource_concept,
            material_status=PreparationStatus.STALE if changed else views[effect.effect_id].status,
            reason_codes=("EVIDENCE_SNAPSHOT_CHANGED",) if changed else views[effect.effect_id].reason_codes)
            for effect in action.effect_catalog if changed or effect.effect_id in views)
    return EvidenceMaterialDetail(project_id=project_id, action_id=action.action_id,
        action_revision=action.revision, action_label=action.display_name, effects=effects)
