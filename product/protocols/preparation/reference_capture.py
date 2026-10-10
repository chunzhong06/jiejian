# 一次正常取样的冻结计划、授权请求和报告；只建立参照候选，不创建安全检查或Verdict。
from typing import Annotated,Literal
import hashlib
import json
from pydantic import Field,model_validator
from product.protocols.runtime.runtime_identity import RuntimeModel,Digest
from product.protocols.runtime.node_runtime import ProjectId,NodeRuntimeReference
from product.protocols.preparation.proof_artifacts import CaptureId,ArtifactId
from product.protocols.preparation.proof_sources import ManagedIdentityClaim,proof_fingerprint
from product.protocols.checks.business_facts import ArtifactManifestReference
from product.protocols.checks.execution_request import FrozenPermission
from product.protocols.checks.check_runtime import NodeCheckRuntimeBundle,CheckActionConfig,CheckProofConfig,CheckIdentity,CheckBudget
from product.protocols.web.target import WebTargetScope


class CaptureActionConfig(CheckActionConfig):
    proofs:tuple[CheckProofConfig,...]=Field(default=(),max_length=0)


class CaptureRuntimeConfig(RuntimeModel):
    project_id:ProjectId
    source_fingerprint:Digest
    target:WebTargetScope
    budget:CheckBudget
    identities:tuple[CheckIdentity,...]=Field(min_length=1,max_length=3)
    actions:tuple[CaptureActionConfig,...]=Field(min_length=1,max_length=1)
    observers:tuple=Field(default=(),max_length=0)
    runtime_reference:NodeRuntimeReference

    @model_validator(mode='after')
    def runtime_associations(self):
        NodeCheckRuntimeBundle.validate_references_and_limits(self)
        NodeCheckRuntimeBundle.validate_node_runtime(self)
        return self


class CaptureResourceSource(RuntimeModel):
    collection:str=Field(pattern=r'^[A-Za-z][A-Za-z0-9_]{0,63}$')
    identity_claims:tuple[ManagedIdentityClaim,...]=Field(min_length=1,max_length=3)
    max_response_bytes:int=Field(default=262144,ge=1024,le=262144)
    timeout_us:int=Field(default=5_000_000,ge=1000,le=5_000_000)


class CaptureCase(RuntimeModel):
    case_id:Annotated[str,Field(pattern=r'^case_[0-9a-f]{32}$')]
    resource_id:str=Field(min_length=1,max_length=256)
    subject_test_identity_id:Annotated[str,Field(pattern=r'^tid_[0-9a-f]{32}$')]
    resource_owner_test_identity_id:Annotated[str,Field(pattern=r'^tid_[0-9a-f]{32}$')]
    resource_binding_id:Annotated[str,Field(pattern=r'^res_[0-9a-f]{32}$')]
    resource_binding_fingerprint:Digest


class CaptureRecoveryReference(RuntimeModel):
    capture_id:CaptureId
    request_hash:Digest
    baseline_document_sha256:Digest
    baseline_sha256:Digest
    generation:str=Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$')
    resource_id:str=Field(min_length=1,max_length=256)
    owner_identity_id:Annotated[str,Field(pattern=r'^tid_[0-9a-f]{32}$')]
    collection:str=Field(pattern=r'^[A-Za-z][A-Za-z0-9_]{0,63}$')


class ReferenceCaptureBaseline(RuntimeModel):
    schema_version:Literal['1']='1'
    capture_id:CaptureId
    job_id:Annotated[str,Field(pattern=r'^job_[0-9a-f]{32}$')]
    attempt:Literal[1]=1
    fencing_token:int=Field(ge=1)
    lease_owner:str=Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$')
    request_hash:Digest
    baseline_sha256:Digest
    generation:str=Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$')
    resource_id:str=Field(min_length=1,max_length=256)
    owner_identity_id:Annotated[str,Field(pattern=r'^tid_[0-9a-f]{32}$')]
    collection:str=Field(pattern=r'^[A-Za-z][A-Za-z0-9_]{0,63}$')
    observed_at_us:int=Field(ge=0)


class ReferenceCapturePlan(RuntimeModel):
    schema_version:Literal['1']='1'
    project_id:ProjectId
    basis_id:Annotated[str,Field(pattern=r'^pb_[0-9a-f]{64}$')]
    plan_hash:Digest
    permission:FrozenPermission
    case:CaptureCase
    resource_source:CaptureResourceSource
    runtime:CaptureRuntimeConfig
    restore:CaptureRecoveryReference|None=None
    created_at_us:int=Field(ge=0)

    @model_validator(mode='after')
    def plan_identity(self):
        raw=json.dumps(self.model_dump(mode='json',exclude={'plan_hash'}),ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        if self.plan_hash!=hashlib.sha256(raw).hexdigest():
            raise ValueError('capture plan hash mismatch')
        if self.permission.expectation!='ALLOW' or self.project_id!=self.runtime.project_id:
            raise ValueError('capture requires explicit current allow')
        identities={item.identity_id for item in self.runtime.identities}
        if {item.identity_id for item in self.resource_source.identity_claims}!=identities or not {
            self.case.subject_test_identity_id,self.case.resource_owner_test_identity_id}<=identities:
            raise ValueError('capture identity coverage mismatch')
        if self.case.resource_binding_id!='res_'+self.case.resource_binding_fingerprint[:32]:
            raise ValueError('capture resource binding mismatch')
        if self.restore is not None and (self.restore.resource_id,self.restore.owner_identity_id,self.restore.collection)!=(
            self.case.resource_id,self.case.resource_owner_test_identity_id,self.resource_source.collection):
            raise ValueError('recovery must address the original resource')
        return self


class ReferenceCaptureRequest(RuntimeModel):
    schema_version:Literal['1']='1'
    capture_id:CaptureId
    asset_id:ArtifactId|None=None
    project_id:ProjectId
    operation_id:Annotated[str,Field(pattern=r'^[0-9a-f]{32}$')]
    authorization_id:Annotated[str,Field(pattern=r'^rca_[0-9a-f]{32}$')]
    control_session_id:Annotated[str,Field(pattern=r'^pcs_[0-9a-f]{32}$')]
    submitted_via:Literal['LOCAL_GUI']='LOCAL_GUI'
    plan:ReferenceCapturePlan
    created_at_us:int=Field(ge=0)

    @model_validator(mode='after')
    def exact_project(self):
        if self.project_id!=self.plan.project_id or self.created_at_us<self.plan.created_at_us:
            raise ValueError('capture request plan mismatch')
        if (self.asset_id is None)!=(self.plan.restore is not None):raise ValueError('only normal capture allocates a file input')
        return self


class ReferenceCaptureRunnerInput(RuntimeModel):
    schema_version:Literal['1']='1'
    job_id:Annotated[str,Field(pattern=r'^job_[0-9a-f]{32}$')]
    attempt:Literal[1]=1
    fencing_token:int=Field(ge=1)
    lease_owner:str=Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$')
    request:ReferenceCaptureRequest
    request_hash:Digest

    @model_validator(mode='after')
    def exact_request(self):
        if proof_fingerprint(self.request)!=self.request_hash:raise ValueError('capture input hash mismatch')
        return self


class ReferenceCaptureReport(RuntimeModel):
    schema_version:Literal['1']='1'
    capture_id:CaptureId
    job_id:Annotated[str,Field(pattern=r'^job_[0-9a-f]{32}$')]
    attempt:Literal[1]=1
    fencing_token:int=Field(ge=1)
    lease_owner:str=Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$')
    request_hash:Digest
    plan_hash:Digest
    authorization_id:Annotated[str,Field(pattern=r'^rca_[0-9a-f]{32}$')]
    state:Literal['CANDIDATE','INCOMPLETE','RECOVERED']
    restores_capture_id:CaptureId|None=None
    manifest:ArtifactManifestReference|None=None
    target_may_have_run:bool
    flow_may_have_run:bool=False
    restore_may_have_run:bool=False
    identity_matched:bool
    resource_matched:bool
    runtime_matched:bool
    recovery_verified:bool
    baseline_sha256:Digest|None=None
    restored_sha256:Digest|None=None
    started_at_us:int=Field(ge=0)
    completed_at_us:int=Field(ge=0)
    reason_codes:tuple[Annotated[str,Field(pattern=r'^[A-Z][A-Z0-9_]{0,127}$')],...]=Field(default=(),max_length=16)

    @model_validator(mode='after')
    def candidate_requires_facts(self):
        if self.completed_at_us<self.started_at_us:raise ValueError('capture report time reversed')
        if self.recovery_verified and (self.baseline_sha256 is None or self.baseline_sha256!=self.restored_sha256):
            raise ValueError('verified recovery requires the original state digest')
        if self.target_may_have_run and not self.flow_may_have_run:raise ValueError('target requires a started flow')
        if self.state=='CANDIDATE' and (self.manifest is None or not all((self.target_may_have_run,self.identity_matched,
            self.resource_matched,self.runtime_matched,self.recovery_verified)) or self.baseline_sha256!=self.restored_sha256
            or self.baseline_sha256 is None or self.reason_codes):raise ValueError('candidate requires complete capture facts')
        if self.state!='CANDIDATE' and self.manifest is not None:raise ValueError('incomplete capture cannot publish file')
        if self.state=='RECOVERED' and (self.restores_capture_id is None or self.target_may_have_run or self.flow_may_have_run or not all((
            self.identity_matched,self.resource_matched,self.runtime_matched,self.recovery_verified))
            or self.baseline_sha256 is None or self.baseline_sha256!=self.restored_sha256 or self.reason_codes):
            raise ValueError('recovery requires complete original baseline comparison')
        if self.restores_capture_id is not None and self.state=='CANDIDATE':raise ValueError('recovery cannot publish a new reference file')
        return self
