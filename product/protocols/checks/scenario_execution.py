"""独立持久化的场景请求进展；只记副作用与恢复事实，不承载权限结论。"""
from typing import Literal
import re
from pydantic import Field,model_validator
from product.protocols.checks.execution_request import WireModel,Hash


class ScenarioNodeProgress(WireModel):
    experiment_id:str=Field(min_length=1,max_length=64)
    invocation_id:str=Field(min_length=1,max_length=64)
    experiment_label:str=Field(min_length=1,max_length=128)
    invocation_label:str=Field(min_length=1,max_length=128)
    case_ids:tuple[str,...]=Field(min_length=1,max_length=32)
    request:Literal['NOT_STARTED','INTENT_SAVED','RECEIVED','UNCONFIRMED']='NOT_STARTED'
    recovery_intents:tuple[str,...]=()
    recovered_cases:tuple[str,...]=()
    observed_at_us:int=Field(ge=0)

    @model_validator(mode='after')
    def association(self):
        for values in (self.case_ids,self.recovery_intents,self.recovered_cases):
            if len(set(values))!=len(values) or any(not re.fullmatch(r'case_[0-9a-f]{32}',key) for key in values):
                raise ValueError('invalid scenario progress case')
        if not set(self.recovered_cases)<=set(self.recovery_intents)<=set(self.case_ids):
            raise ValueError('recovery progress is outside this invocation')
        if self.request=='NOT_STARTED' and self.recovery_intents:
            raise ValueError('unstarted invocation cannot have recovery progress')
        return self


class ScenarioExecutionJournal(WireModel):
    document_type:Literal['jiejian.scenario-execution']='jiejian.scenario-execution'
    schema_version:Literal['1']='1'
    run_id:str=Field(pattern=r'^run_[0-9a-f]{32}$')
    job_id:str=Field(pattern=r'^job_[0-9a-f]{32}$')
    attempt:int=Field(ge=1)
    fencing_token:int=Field(ge=1)
    request_hash:Hash
    scenario_fingerprint:Hash
    nodes:tuple[ScenarioNodeProgress,...]=Field(min_length=1,max_length=256)

    @model_validator(mode='after')
    def unique_nodes(self):
        if len({(item.experiment_id,item.invocation_id) for item in self.nodes})!=len(self.nodes):
            raise ValueError('duplicate scenario progress node')
        return self

    def validate_request(self,request):
        scenario=request.scenario
        if scenario is None or self.scenario_fingerprint!=scenario.fingerprint:
            raise ValueError('scenario progress identity')
        expected=[(item.experiment_id,item.invocation_id,item.case_ids) for item in scenario.invocations]
        if [(item.experiment_id,item.invocation_id,item.case_ids) for item in self.nodes]!=expected:
            raise ValueError('scenario progress coverage')
        labels={(experiment.id,invocation.id):(experiment.label,invocation.label)
            for experiment in scenario.document.experiments for invocation in experiment.invocations}
        if any(labels[item.experiment_id,item.invocation_id]!=(item.experiment_label,item.invocation_label) for item in self.nodes):
            raise ValueError('scenario progress labels')
