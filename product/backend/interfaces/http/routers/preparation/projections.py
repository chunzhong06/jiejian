"""HTTP 工作面投影；嵌套文档复用既有协议，不引入另一套持久化格式。"""
from product.backend.interfaces.http.envelope import ApiModel
from product.protocols.preparation.operation_flow import OperationFlow
from product.protocols.preparation.proof_sources import SourceIdentityClaim, ManagedIdentityClaim
from product.protocols.checks.field_mutation import FieldMutationRequirement


class FlowEffectProjection(ApiModel):
    effect_id: str
    label: str
    kind: str
    protected_projection: list[str]


class FlowActionProjection(ApiModel):
    action_id: str
    revision: int
    label: str
    state_changing: bool
    effects: list[FlowEffectProjection]


class FlowRecordingProjection(ApiModel):
    recording_id: str
    action_id: str
    label: str
    created_at_us: int


class FlowRevisionProjection(ApiModel):
    document: OperationFlow
    adopted: bool
    in_use: bool
    configuration_current: bool


class OperationContextProjection(ApiModel):
    project_id: str
    source_fingerprint: str | None
    endpoint: str | None
    recordings: list[FlowRecordingProjection]
    actions: list[FlowActionProjection]
    flows: list[FlowRevisionProjection]


class ProofAdoptionProjection(ApiModel):
    project_id: str
    basis_id: str
    source_id: str
    revision: int
    preflight_id: str
    action_label: str
    effect_label: str
    replaces_existing: bool
    identity_claims: list[ManagedIdentityClaim | SourceIdentityClaim]
    source_path: str
    read_paths: list[str]
    resource_id: str
    collection: str
    mappings: dict[str, str]
    expected_state: str | None
    protected_projection: list[str]
    field_mutation: FieldMutationRequirement | None
    retained: list[str]
    recheck: list[str]
    gui_url: str
