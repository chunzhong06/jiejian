"""表单交接只接受结构和受控引用；原始参数值及文件留在浏览器。"""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from product.protocols.preparation.proof_sources import RelationshipSourceMapping,AsyncExportMapping
from product.protocols.checks.scenarios import BusinessScenarioRevision


class HandoffInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, hide_input_in_errors=True)


class ParameterHandoff(HandoffInput):
    location: Literal['PATH', 'QUERY', 'HEADER', 'JSON_BODY']
    name: str = Field(max_length=256)
    source: Literal['LITERAL', 'CASE_RESOURCE_ID', 'CASE_SUBJECT_ID', 'PRIOR_STEP_JSON_PATH',
                    'PRIOR_STEP_HEADER', 'PRIOR_STEP_COOKIE', 'PRIOR_STEP_LOCATION']
    secret: bool


class StepHandoff(HandoffInput):
    id: str = Field(pattern=r'^[A-Za-z0-9_.:-]{1,64}$')
    method: Literal['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']
    path: str | None = Field(pattern=r'^/[A-Za-z0-9_./{}~:@%+\-]*$', max_length=2048)
    parameters: list[ParameterHandoff] = Field(max_length=128)


class EvidenceHandoff(HandoffInput):
    effect_id: str = Field(max_length=128)
    request_path: str | None = Field(pattern=r'^/[A-Za-z0-9_./{}~:@%+\-]*$', max_length=2048)
    resource_path: str = Field(max_length=256)
    owner_path: str = Field(max_length=256)
    data_path: str = Field(max_length=256)


class FlowHandoff(HandoffInput):
    kind: Literal['FLOW']
    flow_id: str = Field(pattern=r'^ofl_[0-9a-f]{32}$')
    revision: int = Field(ge=1)
    action_id: str = Field(max_length=128)
    action_revision: int = Field(ge=1)
    subject_identity_id: str | None = Field(default=None, max_length=128)
    owner_identity_id: str | None = Field(default=None, max_length=128)
    target_step_id: str = Field(max_length=64)
    steps: list[StepHandoff] = Field(min_length=1, max_length=32)
    recovery_path: str | None = Field(default=None, pattern=r'^/[A-Za-z0-9_./{}~:@%+\-]*$', max_length=2048)
    evidence_effect_ids: list[str] = Field(default_factory=list, max_length=16)
    evidence_queries: list[EvidenceHandoff] = Field(default_factory=list, max_length=16)



class ProofHandoff(HandoffInput):
    kind: Literal['PROOF']
    basis_id: str = Field(max_length=128)
    action_id: str = Field(max_length=128)
    effect_id: str = Field(max_length=128)
    resource_binding_id: str | None = Field(default=None, max_length=128)
    table: str | None = Field(default=None, max_length=256)
    connection_id: str | None = Field(default=None, pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,62}$')
    collection: str | None = Field(default=None, pattern=r'^[A-Za-z][A-Za-z0-9_]{0,63}$')
    async_export: AsyncExportMapping | None = None
    protected_column: str | None = Field(default=None, max_length=256)
    tenant_column: str | None = Field(default=None, max_length=256)
    state_column: str | None = Field(default=None, max_length=256)
    relationship_mapping: RelationshipSourceMapping | None = None


class ScenarioHandoff(HandoffInput):
    kind: Literal['SCENARIO']
    document: BusinessScenarioRevision


EditorHandoff = Annotated[FlowHandoff | ProofHandoff | ScenarioHandoff, Field(discriminator='kind')]
