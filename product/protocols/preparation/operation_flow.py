from __future__ import annotations

from typing import Literal
from pydantic import Field,model_validator
from product.protocols.web.base import ProtocolModel
from product.protocols.web.workflow import HttpWorkflowBinding,HttpWorkflowStep
from product.protocols.web.target import WebTargetScope
from product.backend.domain.identifiers import PROJECT_ID_PATTERN,TEST_IDENTITY_ID_PATTERN
from product.backend.domain.boundaries.entities import ACTION_ID_PATTERN
from product.backend.domain.preparation.bindings import RecordedRequestTemplate,ResourceInjection


def operation_resource_injection(workflow):
    from product.backend.domain.preparation.bindings import ResourceInjectionKind
    from product.backend.domain.boundaries.entities import boundary_sha256
    step=next(item for item in workflow.steps if item.id==workflow.target_step_id)
    resources=[slot for slot in step.input_slots if slot.source.value=='CASE_RESOURCE_ID']
    created=[item for item in step.output_extractors if item.extractor_id=='created_resource_id']
    if not resources and len(created)==1 and created[0].kind.value=='JSON_PATH':
        consumer,location='RESPONSE_JSON',created[0].json_path
    elif len(resources)==1 and resources[0].consumer.value=='PATH':
        parts=step.request_template.path.strip('/').split('/')
        marker='{'+resources[0].slot_id+'}'
        if marker not in parts:raise ValueError('resource slot must occupy one path segment')
        consumer,location='PATH','path['+str(parts.index(marker))+']'
    else:raise ValueError('target requires one input resource or a declared created object response')
    return ResourceInjection(consumer=ResourceInjectionKind(consumer),location=location,
        template_fingerprint=boundary_sha256(dict(method=step.request_template.method,path=step.request_template.path,
            query_names=sorted(item.name for item in step.request_template.query),consumer=consumer,location=location)))


class OperationFlow(ProtocolModel):
    """不可变流程修订；来源说明编辑起点，采用绑定另外记录当前材料事实。"""
    document_type: Literal['jiejian.operation-flow']='jiejian.operation-flow'
    schema_version: Literal['1']='1'
    id: str=Field(pattern=r'^ofl_[0-9a-f]{32}$')
    revision: int=Field(ge=1)
    project_id: str=Field(pattern=PROJECT_ID_PATTERN)
    business_action_id: str=Field(pattern=ACTION_ID_PATTERN)
    action_revision: int=Field(ge=1)
    subject_test_identity_id: str=Field(pattern=TEST_IDENTITY_ID_PATTERN)
    resource_owner_test_identity_id: str=Field(pattern=TEST_IDENTITY_ID_PATTERN)
    provenance: Literal['MANUAL','OPENAPI','RECORDING']
    source_recording_id: str|None=Field(default=None,pattern=r'^rec_[0-9a-f]{32}$')
    source_fingerprint: str=Field(pattern=r'^[0-9a-f]{64}$')
    target_scope: WebTargetScope
    workflow: HttpWorkflowBinding
    actual_resource_id: str=Field(pattern=r'^[A-Za-z0-9_-][A-Za-z0-9_.-]{0,255}$')
    resource_injection: ResourceInjection
    recovery: RecordedRequestTemplate|None=None

    @model_validator(mode='after')
    def source_and_execution(self):
        if (self.provenance=='RECORDING')!=(self.source_recording_id is not None):
            raise ValueError('recording provenance requires its actual capture')
        if self.workflow.action_id!=self.business_action_id or self.workflow.source_flow_id!=self.id:
            raise ValueError('workflow must name its business action and flow')
        if self.resource_injection!=operation_resource_injection(self.workflow):
            raise ValueError('resource location must match its frozen target request')
        if any(step.identity_id!='CASE_SUBJECT' or step.purpose.value=='CLEANUP' for step in self.workflow.steps):
            raise ValueError('operation steps use the selected case identity; recovery is explicit')
        if len(self.workflow.steps)>32:
            raise ValueError('operation flow exceeds step budget')
        by_id={step.id:step for step in self.workflow.steps}
        for step in self.workflow.steps:
            for slot in step.input_slots:
                if slot.secret or slot.source.value=='SECRET_REF':
                    raise ValueError('account credentials are injected by the Runner, not workflow fields')
                if slot.source.value=='PRIOR_STEP_JSON_PATH':
                    producer=by_id[slot.producer_step_id]
                    if not any(item.extractor_id==slot.slot_id and item.json_path==slot.source_path and not item.secret for item in producer.output_extractors):
                        raise ValueError('dynamic value must name the declared producer extraction')
        return self

    @property
    def steps(self):
        return self.workflow.steps

    @property
    def target_step_id(self):
        return self.workflow.target_step_id


class OperationFlowDraft(ProtocolModel):
    id:str=Field(pattern=r'^ofl_[0-9a-f]{32}$')
    revision:int=Field(ge=1)
    business_action_id:str=Field(pattern=ACTION_ID_PATTERN)
    action_revision:int=Field(ge=1)
    subject_test_identity_id:str=Field(pattern=TEST_IDENTITY_ID_PATTERN)
    resource_owner_test_identity_id:str=Field(pattern=TEST_IDENTITY_ID_PATTERN)
    provenance:Literal['MANUAL','OPENAPI','RECORDING']='MANUAL'
    source_recording_id:str|None=None
    source_fingerprint:str=Field(pattern=r'^[0-9a-f]{64}$')
    actual_resource_id:str
    target_step_id:str
    steps:tuple[HttpWorkflowStep,...]=Field(min_length=1,max_length=32)
    recovery:RecordedRequestTemplate|None=None
