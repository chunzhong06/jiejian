# 准备建议的只读交换模型；不保存完成状态，不承载凭据或写入授权。
from typing import Literal

from pydantic import Field

from product.backend.core.boundaries.entities import BoundaryModel


class PreparationNextAction(BoundaryModel):
    kind: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=256)
    reason: str = Field(min_length=1, max_length=1024)
    handler: Literal['USER', 'AGENT', 'EITHER', 'SYSTEM']
    gui_url: str = Field(pattern=r'^#/(application|permissions|tests|changes|environment|history)(\?|$)', max_length=2048)
    mcp_tool: Literal['jiejian_proof_source_save', 'jiejian_proof_preflight_start',
                      'jiejian_proof_preflight_status', 'jiejian_proof_adoption_preview',
                      'jiejian_check_run', 'jiejian_change_registration_preview'] | None = None
    required_level: Literal['READ', 'PREPARE', 'EXECUTE'] | None = None
    action_id: str | None = None
    action_revision: int | None = Field(default=None, ge=1)
    effect_id: str | None = None
    source_id: str | None = None
    source_revision: int | None = Field(default=None, ge=1)
    preflight_id: str | None = None
    task_id: str | None = None


class PreparationMaterialAdvice(BoundaryModel):
    action_id: str
    action_revision: int = Field(ge=1)
    kind: Literal['identity', 'execution', 'resource', 'evidence', 'recovery']
    member_id: str | None = None
    label: str = Field(min_length=1, max_length=512)
    status: Literal['SATISFIED', 'NEEDS_USER', 'STALE', 'BLOCKED', 'NOT_REQUIRED']
    reason: str = Field(min_length=1, max_length=1024)
    reason_codes: tuple[str, ...] = ()
    gui_url: str


class ProofSourceAdvice(BoundaryModel):
    source_id: str
    revision: int = Field(ge=1)
    state: Literal['NEEDS_ACTION', 'WAITING', 'USABLE', 'UNSUPPORTED']
    next_action: PreparationNextAction | None


class PreparationGuidance(BoundaryModel):
    project_id: str
    basis_id: str
    state: Literal['CURRENT', 'NEEDS_REFRESH']
    next_action: PreparationNextAction | None
    materials: tuple[PreparationMaterialAdvice, ...]
    sources: tuple[ProofSourceAdvice, ...]
    note: str
