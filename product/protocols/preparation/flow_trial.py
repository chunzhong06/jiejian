"""场景调试的冻结授权与有限观察，不携带权限结论或响应原文。"""
from typing import Literal
from pydantic import Field, model_validator
from product.protocols.web.base import ProtocolModel
from product.protocols.preparation.operation_flow import OperationFlow
from product.protocols.checks.check_runtime import CheckBudget
from product.protocols.checks.identity import CheckIdentity
from product.protocols.web.target import WebTargetScope
from product.protocols.web.request import HttpRequestTemplate


class TrialCase(ProtocolModel):
    case_id: str = Field(pattern=r'^trial_[0-9a-f]{32}$')
    resource_id: str = Field(min_length=1,max_length=256)
    subject_test_identity_id: str = Field(pattern=r'^tid_[0-9a-f]{32}$')
    resource_owner_test_identity_id: str = Field(pattern=r'^tid_[0-9a-f]{32}$')


class FlowTrialRuntime(ProtocolModel):
    project_id: str
    target: WebTargetScope
    budget: CheckBudget
    identities: tuple[CheckIdentity,...] = Field(min_length=1,max_length=2)


class FlowTrialPlan(ProtocolModel):
    schema_version: Literal['1'] = '1'
    flow: OperationFlow
    runtime: FlowTrialRuntime
    case: TrialCase
    identity_updated_at_us: dict[str,int]
    recovery_request: HttpRequestTemplate | None = None
    state_changing: bool
    mode: Literal['TRIAL','RESTORE'] = 'TRIAL'
    origin_trial_id: str | None = Field(default=None,pattern=r'^ftr_[0-9a-f]{32}$')

    @model_validator(mode='after')
    def associations(self):
        identities={item.identity_id:item for item in self.runtime.identities}
        required={self.case.subject_test_identity_id,self.case.resource_owner_test_identity_id}
        if (self.runtime.project_id!=self.flow.project_id or self.runtime.target!=self.flow.target_scope
            or set(identities)!=required or set(self.identity_updated_at_us)!=required
            or any(item.verification is None for item in identities.values())):
            raise ValueError('trial identities or target differ from frozen flow')
        if (self.mode=='RESTORE')!=(self.origin_trial_id is not None):
            raise ValueError('restore requires its original trial')
        if (self.state_changing or self.mode=='RESTORE') and (self.flow.recovery is None or self.recovery_request is None):
            raise ValueError('mutable trial requires an explicit recovery request')
        target=next(i for i,step in enumerate(self.flow.steps) if step.id==self.flow.target_step_id)
        if target!=len(self.flow.steps)-1:
            raise ValueError('trial target must be last; move later preparation before the target')
        return self


class FlowTrialRequest(ProtocolModel):
    schema_version: Literal['1'] = '1'
    trial_id: str = Field(pattern=r'^ftr_[0-9a-f]{32}$')
    operation_id: str = Field(min_length=1,max_length=128,pattern=r'^[A-Za-z0-9._:-]+$')
    created_at_us: int = Field(ge=0)
    control_session_id: str = Field(pattern=r'^pcs_[0-9a-f]{32}$')
    plan: FlowTrialPlan


class FlowTrialRunnerInput(ProtocolModel):
    schema_version: Literal['1'] = '1'
    job_id: str = Field(pattern=r'^job_[0-9a-f]{32}$')
    attempt: Literal[1] = 1
    fencing_token: int = Field(ge=1)
    lease_owner: str = Field(min_length=1,max_length=128)
    request_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    request: FlowTrialRequest


class FlowTrialStep(ProtocolModel):
    step_id: str = Field(min_length=1,max_length=128)
    purpose: Literal['SETUP','TARGET','RESTORE']
    status_code: int | None = Field(default=None,ge=100,le=599)
    response_bytes: int | None = Field(default=None,ge=0)
    classification: Literal['ACCEPTED','DENIED','UNKNOWN']
    error_code: str | None = Field(default=None,pattern=r'^[A-Z][A-Z0-9_]{0,127}$')


class FlowTrialReport(ProtocolModel):
    schema_version: Literal['1'] = '1'
    trial_id: str = Field(pattern=r'^ftr_[0-9a-f]{32}$')
    job_id: str = Field(pattern=r'^job_[0-9a-f]{32}$')
    request_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    attempt: Literal[1] = 1
    fencing_token: int = Field(ge=1)
    lease_owner: str = Field(min_length=1,max_length=128)
    steps: tuple[FlowTrialStep,...] = Field(max_length=33)
    identity_status: Literal['MATCH','MISMATCH','UNKNOWN']
    target_attempted: bool
    flow_attempted: bool
    recovery: Literal['NOT_REQUIRED','NOT_ATTEMPTED','REQUEST_ACCEPTED','REQUEST_DENIED','UNCONFIRMED']
    error_code: str | None = Field(default=None,pattern=r'^[A-Z][A-Z0-9_]{0,127}$')
    finished_at_us: int = Field(ge=0)
