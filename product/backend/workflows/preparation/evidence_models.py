# 已保存证明材料的只读边界模型；不暴露运行配置、来源选择或执行能力。
from typing import Literal

from pydantic import Field

from product.backend.core.business_boundary import BoundaryModel
from product.backend.workflows.preparation.models import PreparationStatus


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
