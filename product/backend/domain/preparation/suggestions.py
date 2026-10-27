# 五类材料的有界整理建议；只保存准备办法和受控引用，不保存准备完成状态或可执行配置。
from __future__ import annotations

from typing import Annotated, Literal
from pydantic import Field, TypeAdapter, model_validator
from product.backend.domain.boundaries.entities import BoundaryModel
from product.backend.domain.identifiers import PROJECT_ID_PATTERN

SUGGESTION_ID_PATTERN = r'^psg_[0-9a-f]{32}$'
SUGGESTION_ITEM_PATTERN = r'^psi_[0-9a-f]{16}$'
SUGGESTION_BASIS_PATTERN = r'^psb_[0-9a-f]{64}$'
ShortText = Annotated[str, Field(min_length=1, max_length=512, pattern=r'\S')]


class ApprovedMaterialTarget(BoundaryModel):
    kind: Literal['APPROVED']
    action_id: str = Field(pattern=r'^bac_[0-9a-f]{32}$')
    action_revision: int = Field(ge=1)
    actor_id: str | None = Field(default=None, pattern=r'^bar_[0-9a-f]{32}$')
    actor_revision: int | None = Field(default=None, ge=1)
    effect_id: str | None = Field(default=None, pattern=r'^bef_[0-9a-f]{32}$')

    @model_validator(mode='after')
    def paired_actor(self):
        if (self.actor_id is None) != (self.actor_revision is None):
            raise ValueError('角色引用必须同时带精确修订')
        return self


class CandidateMaterialTarget(BoundaryModel):
    kind: Literal['CANDIDATE']
    candidate_id: str = Field(pattern=r'^rcd_[0-9a-f]{32}$')
    revision: int = Field(ge=1)
    action_item_id: str = Field(pattern=r'^pactn_[0-9a-f]{16}$')
    actor_item_id: str | None = Field(default=None, pattern=r'^pactr_[0-9a-f]{16}$')
    effect_item_id: str | None = Field(default=None, pattern=r'^peff_[0-9a-f]{16}$')


class SuggestionSource(BoundaryModel):
    classification: Literal['SOURCE_CANDIDATE', 'HYPOTHESIS']
    candidate_ids: tuple[Annotated[str, Field(pattern=r'^(role|action)_[0-9a-f]{32}$')], ...] = Field(default=(), max_length=8)
    explanation: ShortText

    @model_validator(mode='after')
    def source_declaration(self):
        if bool(self.candidate_ids) != (self.classification == 'SOURCE_CANDIDATE'):
            raise ValueError('源码依据必须引用已核验候选，假设不能声称有已核验定位')
        if len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise ValueError('源码候选引用不能重复')
        return self


class IdentitySuggestion(BoundaryModel):
    kind: Literal['identity']
    slot_id: str | None = Field(default=None, min_length=1, max_length=128)
    account_requirement: ShortText
    existing_identity_ids: tuple[Annotated[str, Field(pattern=r'^tid_[0-9a-f]{32}$')], ...] = Field(default=(), max_length=8)


class ExecutionSuggestion(BoundaryModel):
    kind: Literal['execution']
    entry_candidate_id: str | None = Field(default=None, pattern=r'^action_[0-9a-f]{32}$')
    normal_steps: tuple[ShortText, ...] = Field(default=(), max_length=10)
    existing_recording_ids: tuple[Annotated[str, Field(pattern=r'^rec_[0-9a-f]{32}$')], ...] = Field(default=(), max_length=8)


class ResourceFieldRequirement(BoundaryModel):
    field: str = Field(min_length=1, max_length=128, pattern=r'\S')
    requirement: ShortText


class ResourceSuggestion(BoundaryModel):
    kind: Literal['resource']
    resource_concept: str = Field(min_length=1, max_length=128, pattern=r'\S')
    fields: tuple[ResourceFieldRequirement, ...] = Field(default=(), max_length=16)
    preparation_steps: tuple[ShortText, ...] = Field(default=(), max_length=10)
    existing_resource_ids: tuple[Annotated[str, Field(pattern=r'^res_[0-9a-f]{32}$')], ...] = Field(default=(), max_length=8)


class EvidenceSuggestion(BoundaryModel):
    kind: Literal['evidence']
    capability: str | None = Field(default=None, pattern=r'^[A-Z][A-Z0-9_]{0,63}$')
    observable_result: ShortText
    field_hints: tuple[Annotated[str, Field(min_length=1, max_length=128, pattern=r'\S')], ...] = Field(default=(), max_length=16)
    existing_source_ids: tuple[Annotated[str, Field(pattern=r'^psr_[0-9a-f]{32}$')], ...] = Field(default=(), max_length=8)


class RecoverySuggestion(BoundaryModel):
    kind: Literal['recovery']
    expected_state: ShortText
    entry_candidate_id: str | None = Field(default=None, pattern=r'^action_[0-9a-f]{32}$')
    existing_recording_ids: tuple[Annotated[str, Field(pattern=r'^rec_[0-9a-f]{32}$')], ...] = Field(default=(), max_length=8)


class PreparationSuggestionItem(BoundaryModel):
    item_id: str = Field(pattern=SUGGESTION_ITEM_PATTERN)
    target: Annotated[ApprovedMaterialTarget | CandidateMaterialTarget, Field(discriminator='kind')]
    material: Annotated[IdentitySuggestion | ExecutionSuggestion | ResourceSuggestion | EvidenceSuggestion | RecoverySuggestion, Field(discriminator='kind')]
    description: str = Field(min_length=1, max_length=1024, pattern=r'\S')
    source: SuggestionSource
    gap: str | None = Field(default=None, min_length=1, max_length=1024, pattern=r'\S')
    depends_on: tuple[Annotated[str, Field(pattern=SUGGESTION_ITEM_PATTERN)], ...] = Field(default=(), max_length=50)
    handler: Literal['USER', 'AGENT', 'SYSTEM']

    @model_validator(mode='after')
    def precise_material_target(self):
        actor = self.target.actor_id if self.target.kind == 'APPROVED' else self.target.actor_item_id
        effect = self.target.effect_id if self.target.kind == 'APPROVED' else self.target.effect_item_id
        if self.material.kind in {'identity', 'resource'} and actor is None:
            raise ValueError('账号与资源建议必须说明对应角色')
        if self.material.kind == 'evidence' and effect is None:
            raise ValueError('结果证明建议必须引用具体业务结果')
        return self


class PreparationSuggestionContent(BoundaryModel):
    items: tuple[PreparationSuggestionItem, ...] = Field(default=(), max_length=50)
    unresolved_questions: tuple[ShortText, ...] = Field(default=(), max_length=10)

    @model_validator(mode='after')
    def dependency_graph(self):
        graph = {item.item_id: item.depends_on for item in self.items}
        if len(graph) != len(self.items):
            raise ValueError('建议项标识不能重复')
        visiting, done = set(), set()
        def visit(key):
            if key not in graph or key in visiting:
                raise ValueError('建议依赖必须引用当前清单且不能形成循环')
            if key in done:
                return
            visiting.add(key)
            for child in graph[key]:
                visit(child)
            visiting.remove(key); done.add(key)
        for key in graph:
            visit(key)
        return self


class PreparationSuggestionRevision(BoundaryModel):
    schema_version: Literal['1'] = '1'
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    suggestion_id: str = Field(pattern=SUGGESTION_ID_PATTERN)
    revision: int = Field(ge=1)
    basis_id: str = Field(pattern=SUGGESTION_BASIS_PATTERN)
    content: PreparationSuggestionContent
    submitted_via: Literal['LOCAL_GUI', 'MCP']
    created_at_us: int = Field(ge=0)

    @model_validator(mode='after')
    def bounded_root(self):
        if len(self.model_dump_json().encode('utf-8')) > 256 * 1024:
            raise ValueError('材料建议根不得超过256KiB')
        return self


class SuggestionItemBasis(BoundaryModel):
    item_id: str = Field(pattern=SUGGESTION_ITEM_PATTERN)
    fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')


class PreparationSuggestionRevisionV2(PreparationSuggestionRevision):
    schema_version: Literal['2'] = '2'
    item_bases: tuple[SuggestionItemBasis, ...] = Field(max_length=50)

    @model_validator(mode='after')
    def complete_bases(self):
        if len({item.item_id for item in self.item_bases}) != len(self.item_bases) or {item.item_id for item in self.item_bases} != {item.item_id for item in self.content.items}:
            raise ValueError('每条建议必须有唯一的依赖依据')
        return self


preparation_suggestion_reader = TypeAdapter(Annotated[
    PreparationSuggestionRevision | PreparationSuggestionRevisionV2, Field(discriminator='schema_version')])


class SavePreparationSuggestion(BoundaryModel):
    operation_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    expected_basis_id: str = Field(pattern=SUGGESTION_BASIS_PATTERN)
    suggestion_id: str | None = Field(default=None, pattern=SUGGESTION_ID_PATTERN)
    expected_revision: int | None = Field(default=None, ge=1)
    content: PreparationSuggestionContent

    @model_validator(mode='after')
    def paired_revision(self):
        if (self.suggestion_id is None) != (self.expected_revision is None):
            raise ValueError('修改建议必须携带精确建议ID和预期修订')
        return self
