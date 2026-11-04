from __future__ import annotations
from product.protocols.web.environment import FrozenEnvironment
from product.protocols.preparation.http_entity import HttpEntityEvidence
from product.protocols.preparation.api_source import ApiSourceReference

import re
from typing import Literal
from pydantic import Field,model_validator
from product.protocols.web.base import ProtocolModel
from product.protocols.web.workflow import HttpWorkflowBinding,HttpWorkflowStep
from product.protocols.web.target import WebTargetScope
from product.backend.domain.identifiers import PROJECT_ID_PATTERN,TEST_IDENTITY_ID_PATTERN
from product.backend.domain.boundaries.entities import ACTION_ID_PATTERN
from product.backend.domain.preparation.bindings import RecordedRequestTemplate,ResourceInjection


def operation_resource_injection(workflow):
    """从唯一受检请求定位资源，不根据参数名称猜测资源归属。"""
    from product.backend.domain.preparation.bindings import ResourceInjectionKind
    from product.backend.domain.boundaries.entities import boundary_sha256
    step=next(item for item in workflow.steps if item.id==workflow.target_step_id)
    resources=[slot for slot in step.input_slots if slot.source.value=='CASE_RESOURCE_ID']
    created=[item for item in step.output_extractors if item.extractor_id=='created_resource_id']
    if not resources and len(created)==1 and created[0].kind.value=='JSON_PATH':
        consumer,location='RESPONSE_JSON',created[0].json_path
    elif len(resources)==1:
        slot=resources[0]
        consumer=slot.consumer.value
        if consumer=='PATH':
            parts=step.request_template.path.strip('/').split('/')
            marker='{'+slot.slot_id+'}'
            if parts.count(marker)!=1:raise ValueError('resource slot must occupy a complete path segment')
            location='path['+str(parts.index(marker))+']'
        elif consumer=='QUERY':
            fields=[item.name for item in step.request_template.query if item.slot_id==slot.slot_id]
            if len(fields)!=1:raise ValueError('resource slot must occupy one query value')
            location='query.'+fields[0]
        elif consumer=='JSON_BODY' and step.request_template.body.kind.value=='JSON':
            def paths(value,prefix=()):
                if isinstance(value,dict):
                    if value=={'$slot':slot.slot_id}:yield prefix
                    else:
                        for key,child in value.items():yield from paths(child,(*prefix,key))
                elif isinstance(value,list):
                    for index,child in enumerate(value):yield from paths(child,(*prefix,index))
            found=list(paths(step.request_template.body.value))
            if len(found)!=1 or not found[0]:raise ValueError('resource slot must occupy one JSON field')
            location='$'
            for part in found[0]:
                if isinstance(part,int):location+='['+str(part)+']'
                elif re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*',part):location+='.'+part
                else:raise ValueError('resource JSON field must have an unambiguous path')
        else:raise ValueError('resource slot must use path, query, or JSON body')
    else:raise ValueError('target requires one input resource or a declared created object response')
    return ResourceInjection(consumer=ResourceInjectionKind(consumer),location=location,
        template_fingerprint=boundary_sha256(dict(method=step.request_template.method,path=step.request_template.path,
            query_names=sorted(item.name for item in step.request_template.query),consumer=consumer,location=location)))


class OperationFlow(ProtocolModel):
    """不可变流程修订；来源说明编辑起点，采用绑定另外记录当前材料事实。"""
    document_type: Literal['jiejian.operation-flow']='jiejian.operation-flow'
    schema_version: Literal['1','2']='1'
    environment: FrozenEnvironment|None=Field(default=None,exclude_if=lambda value:value is None)
    source_request: ApiSourceReference|None=Field(default=None,exclude_if=lambda value:value is None)
    entity_evidence: tuple[HttpEntityEvidence,...]=Field(default=(),max_length=16,exclude_if=lambda value:not value)
    id: str=Field(pattern=r'^ofl_[0-9a-f]{32}$')
    revision: int=Field(ge=1)
    project_id: str=Field(pattern=PROJECT_ID_PATTERN)
    business_action_id: str=Field(pattern=ACTION_ID_PATTERN)
    action_revision: int=Field(ge=1)
    subject_test_identity_id: str=Field(pattern=TEST_IDENTITY_ID_PATTERN)
    resource_owner_test_identity_id: str=Field(pattern=TEST_IDENTITY_ID_PATTERN)
    provenance: Literal['MANUAL','OPENAPI','RECORDING']
    source_recording_id: str|None=Field(default=None,pattern=r'^rec_[0-9a-f]{32}$')
    source_fingerprint: str|None=Field(pattern=r'^[0-9a-f]{64}$')
    target_scope: WebTargetScope
    workflow: HttpWorkflowBinding
    actual_resource_id: str=Field(pattern=r'^[A-Za-z0-9_-][A-Za-z0-9_.-]{0,255}$')
    resource_injection: ResourceInjection
    recovery: RecordedRequestTemplate|None=None

    @model_validator(mode='after')
    def source_and_execution(self):
        if (self.schema_version == '2') != (self.environment is not None or self.source_request is not None):
            raise ValueError('environment operation flow requires format 2')
        if self.source_fingerprint is None and self.environment is None:
            raise ValueError('source-free flow requires its environment')
        if self.entity_evidence and self.environment is None:
            raise ValueError('entity evidence requires an environment snapshot')
        if len({item.effect_id for item in self.entity_evidence}) != len(self.entity_evidence):
            raise ValueError('duplicate entity evidence effect')
        if self.environment is not None and self.target_scope != self.environment.target:
            raise ValueError('flow target differs from its environment')
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
                if slot.source.value=='SECRET_REF' or slot.secret and slot.source.value not in {'PRIOR_STEP_JSON_PATH','PRIOR_STEP_HEADER','PRIOR_STEP_COOKIE'}:
                    raise ValueError('account credentials are injected by the Runner, not workflow fields')
                if slot.source.value=='PRIOR_STEP_JSON_PATH':
                    producer=by_id[slot.producer_step_id]
                    if not any(item.extractor_id==slot.slot_id and item.json_path==slot.source_path and item.secret==slot.secret for item in producer.output_extractors):
                        raise ValueError('dynamic value must name the declared producer extraction')
        return self

    @property
    def steps(self):
        return self.workflow.steps

    @property
    def target_step_id(self):
        return self.workflow.target_step_id


class OperationFlowDraft(ProtocolModel):
    source_request: ApiSourceReference|None=Field(default=None,exclude_if=lambda value:value is None)
    entity_evidence: tuple[HttpEntityEvidence,...]=Field(default=(),max_length=16,exclude_if=lambda value:not value)
    id:str=Field(pattern=r'^ofl_[0-9a-f]{32}$')
    revision:int=Field(ge=1)
    business_action_id:str=Field(pattern=ACTION_ID_PATTERN)
    action_revision:int=Field(ge=1)
    subject_test_identity_id:str=Field(pattern=TEST_IDENTITY_ID_PATTERN)
    resource_owner_test_identity_id:str=Field(pattern=TEST_IDENTITY_ID_PATTERN)
    provenance:Literal['MANUAL','OPENAPI','RECORDING']='MANUAL'
    source_recording_id:str|None=None
    source_fingerprint:str|None=Field(pattern=r'^[0-9a-f]{64}$')
    actual_resource_id:str
    target_step_id:str
    steps:tuple[HttpWorkflowStep,...]=Field(min_length=1,max_length=32)
    recovery:RecordedRequestTemplate|None=None
