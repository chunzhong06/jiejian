"""可复验的有限业务实验；权限只引用已批准修订，顺序与批量不会隐式生成新规则。"""
from __future__ import annotations

from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from product.protocols.codec import content_hash

Key = Annotated[str, Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,63}$')]
PathPart = Annotated[str, Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')] | Annotated[int, Field(ge=0,le=127)]


class ScenarioModel(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True,hide_input_in_errors=True)


class ScenarioPermission(ScenarioModel):
    intent_id: str=Field(pattern=r'^pin_[0-9a-f]{32}$')
    revision: int=Field(ge=1)
    intent_hash: str=Field(pattern=r'^[0-9a-f]{64}$')


class ScenarioItem(ScenarioModel):
    id: Key
    permission: ScenarioPermission
    subject_identity_id: str|None=Field(default=None,pattern=r'^tid_[0-9a-f]{32}$')
    resource_id: str=Field(min_length=1,max_length=256)
    resource_from: Key|None=Field(default=None,exclude_if=lambda value:value is None)


class BatchInvocation(ScenarioModel):
    strategy: Literal['ATOMIC','PER_ITEM']
    array_path: tuple[PathPart,...]=Field(min_length=1,max_length=8)
    # 批量读取必须声明返回项的资源/位置关联；未配置时不能借整份响应证明单项披露。
    response_items_path: str|None=Field(default=None,pattern=r'^\$(?:\.[A-Za-z_][A-Za-z0-9_]*|\[[0-9]+\]){0,8}$')
    response_resource_field: Key|None=None


class ScenarioInvocation(ScenarioModel):
    id: Key
    label: str=Field(min_length=1,max_length=128)
    items: tuple[ScenarioItem,...]=Field(min_length=1,max_length=32)
    batch: BatchInvocation|None=None
    depends_on: tuple[Key,...]=Field(default=(),max_length=16)

    @model_validator(mode='after')
    def one_request(self):
        if self.batch is None and len(self.items)!=1:
            raise ValueError('multiple items require one explicit batch invocation')
        if self.batch is not None and any(item.resource_from is not None for item in self.items):
            raise ValueError('dynamic resources require individually correlated invocations')
        if len({item.id for item in self.items})!=len(self.items) or len(set(self.depends_on))!=len(self.depends_on):
            raise ValueError('duplicate item or dependency')
        if len({item.subject_identity_id for item in self.items})!=1:
            raise ValueError('one HTTP invocation has one actual principal')
        return self


class ScenarioExperiment(ScenarioModel):
    id: Key
    label: str=Field(min_length=1,max_length=128)
    kind: Literal['NORMAL','OMIT','REORDER','REPEAT','CHANGE_SUBJECT','REVOKE']
    control_experiment_id: Key|None=None
    invocations: tuple[ScenarioInvocation,...]=Field(min_length=1,max_length=16)

    @model_validator(mode='after')
    def finite_order(self):
        ids=[item.id for item in self.invocations]
        if len(set(ids))!=len(ids):
            raise ValueError('each occurrence needs a distinct invocation ID')
        if self.kind=='NORMAL':
            seen=set()
            for invocation in self.invocations:
                if not set(invocation.depends_on)<=seen:
                    raise ValueError('normal business sequence must satisfy its declared dependencies')
                if any(item.resource_from is not None and item.resource_from not in seen for item in invocation.items):
                    raise ValueError('normal resource consumers must follow their producer')
                seen.add(invocation.id)
        elif self.control_experiment_id is None:
            raise ValueError('a challenge requires an explicit normal experiment')
        return self


class BusinessScenarioRevision(ScenarioModel):
    document_type: Literal['jiejian.business-scenario']='jiejian.business-scenario'
    schema_version: Literal['1']='1'
    id: str=Field(pattern=r'^bsc_[0-9a-f]{32}$')
    project_id: str=Field(pattern=r'^[a-z][a-z0-9_-]{0,63}$')
    revision: int=Field(ge=1)
    label: str=Field(min_length=1,max_length=128)
    description: str=Field(default='',max_length=1024)
    experiments: tuple[ScenarioExperiment,...]=Field(min_length=1,max_length=16)

    @model_validator(mode='after')
    def normal_controls(self):
        by_id={item.id:item for item in self.experiments}
        if len(by_id)!=len(self.experiments) or not any(item.kind=='NORMAL' for item in self.experiments):
            raise ValueError('experiments need unique IDs and a normal control')
        for item in self.experiments:
            if item.control_experiment_id is not None and (item.control_experiment_id not in by_id
                    or by_id[item.control_experiment_id].kind!='NORMAL' or item.control_experiment_id==item.id):
                raise ValueError('control must reference another complete normal experiment')
        return self


class FrozenScenarioInvocation(ScenarioModel):
    experiment_id: Key
    invocation_id: Key
    case_ids: tuple[Annotated[str,Field(pattern=r'^case_[0-9a-f]{32}$')],...]=Field(min_length=1,max_length=32)


class FrozenBusinessScenario(ScenarioModel):
    document: BusinessScenarioRevision
    fingerprint: str=Field(pattern=r'^[0-9a-f]{64}$')
    invocations: tuple[FrozenScenarioInvocation,...]=Field(min_length=1,max_length=256)


class ScenarioReference(ScenarioModel):
    scenario_id: str=Field(pattern=r'^bsc_[0-9a-f]{32}$')
    revision: int=Field(ge=1)


def scenario_control_cases(scenario, case_id):
    invocation=next((item for item in scenario.invocations if case_id in item.case_ids),None)
    if invocation is None:
        return ()
    experiment=next(item for item in scenario.document.experiments if item.id==invocation.experiment_id)
    if experiment.control_experiment_id is None:
        return ()
    return tuple(key for item in scenario.invocations if item.experiment_id==experiment.control_experiment_id for key in item.case_ids)


def validate_scenario_cases(scenario, actions):
    """独立 reader 核对正式规则、资源、实际身份和按批量策略推导的义务。"""
    if scenario.fingerprint!=content_hash('BusinessScenario',scenario.document.model_dump(mode='json')):
        raise ValueError('scenario content identity')
    cases={case.case_id:case for action in actions for case in action.cases}
    frozen={(item.experiment_id,item.invocation_id):item for item in scenario.invocations}
    expected={(experiment.id,invocation.id) for experiment in scenario.document.experiments for invocation in experiment.invocations}
    if set(frozen)!=expected or len(frozen)!=len(scenario.invocations):
        raise ValueError('scenario invocation coverage')
    seen=set()
    for experiment in scenario.document.experiments:
        for invocation in experiment.invocations:
            ids=frozen[experiment.id,invocation.id].case_ids
            if len(ids)!=len(invocation.items) or seen.intersection(ids):
                raise ValueError('scenario item occurrence coverage')
            seen.update(ids)
            selected=[cases[key] for key in ids]
            mixed=any(case.permission.expectation=='DENY' for case in selected)
            if experiment.kind=='NORMAL' and mixed:
                raise ValueError('normal control contains a forbidden operation')
            for index,(item,case) in enumerate(zip(invocation.items,selected,strict=True)):
                permission=case.permission
                if (permission.intent_id,permission.revision,permission.intent_hash)!=(item.permission.intent_id,item.permission.revision,item.permission.intent_hash):
                    raise ValueError('scenario permission revision')
                occurrence='occ_'+content_hash('ScenarioOccurrence',dict(scenario=scenario.fingerprint,
                    experiment=experiment.id,invocation=invocation.id,index=index))[:32]
                if (case.occurrence_id,case.subject_test_identity_id,case.resource_id)!=(occurrence,item.subject_identity_id,item.resource_id):
                    raise ValueError('scenario item identity')
                if invocation.batch is None:
                    if case.invocation_kind is not None:
                        raise ValueError('single invocation cannot use batch obligations')
                else:
                    absent=(invocation.batch.strategy=='ATOMIC' and mixed) or permission.expectation=='DENY'
                    if (case.invocation_kind,case.batch_effect_expectation)!=('BATCH_'+invocation.batch.strategy,'ABSENT' if absent else 'PRESENT'):
                        raise ValueError('batch policy obligation')
    if seen!={case.case_id for case in cases.values() if case.occurrence_id is not None}:
        raise ValueError('orphan scenario case')
    mapped={(case.permission.intent_id,case.permission.revision,case.permission.intent_hash):(action.action_id,case.permission.conditions)
        for action in actions for case in action.cases}
    validate_experiment_variants(scenario.document,mapped)
    for experiment in scenario.document.experiments:
        for invocation in experiment.invocations:
            if experiment.kind=='NORMAL':
                continue
            selected=[cases[key] for key in frozen[experiment.id,invocation.id].case_ids]
            control=next(item for item in scenario.document.experiments if item.id==experiment.control_experiment_id)
            def signature(items):
                return [(case.execution.flow_id,case.resource_id,case.protected_effect_ids) for case in items]
            if invocation.batch is not None:
                matches=[item for item in control.invocations if item.batch==invocation.batch
                    and signature([cases[key] for key in frozen[control.id,item.id].case_ids])==signature(selected)]
                if not matches:
                    raise ValueError('batch challenge needs the same complete all-allowed batch control')
            else:
                normal_cases=[cases[key] for item in control.invocations for key in frozen[control.id,item.id].case_ids]
                if any(case.expects_absence and not any(signature([normal])==signature([case])
                    and not normal.expects_absence and 'ALLOW_REGRESSION' in normal.roles for normal in normal_cases) for case in selected):
                    raise ValueError('scenario denial needs the same full normal effect control')


def validate_experiment_variants(document,permissions):
    """实验名称必须对应实际结构变化；标签本身不能形成跳步、重复或撤销覆盖。"""
    import json
    from collections import Counter
    def signature(invocation,*,subjects=True):
        members=[(permissions[(item.permission.intent_id,item.permission.revision,item.permission.intent_hash)][0],
            item.subject_identity_id if subjects else None,item.resource_id,item.resource_from) for item in invocation.items]
        return json.dumps(dict(items=members,batch=None if invocation.batch is None else invocation.batch.model_dump(mode='json')),sort_keys=True)
    def subsequence(left,right):
        iterator=iter(right)
        return all(any(candidate==value for candidate in iterator) for value in left)
    for experiment in document.experiments:
        if experiment.kind=='NORMAL':continue
        control=next(item for item in document.experiments if item.id==experiment.control_experiment_id)
        normal=[signature(item) for item in control.invocations]
        variant=[signature(item) for item in experiment.invocations]
        valid=True
        if experiment.kind=='OMIT':valid=len(variant)<len(normal) and subsequence(variant,normal)
        elif experiment.kind=='REORDER':valid=normal!=variant and Counter(normal)==Counter(variant)
        elif experiment.kind=='REPEAT':valid=len(variant)>len(normal) and subsequence(normal,variant) and set(variant)<=set(normal)
        elif experiment.kind=='CHANGE_SUBJECT':
            valid=normal!=variant and [signature(item,subjects=False) for item in control.invocations]==[signature(item,subjects=False) for item in experiment.invocations]
        elif experiment.kind=='REVOKE':
            valid=any(condition is not None and any(relation.kind in {'SHARING','DELEGATION'} and relation.state=='REVOKED' for relation in condition.relationships)
                for node in experiment.invocations for item in node.items
                for _action,condition in (permissions[(item.permission.intent_id,item.permission.revision,item.permission.intent_hash)],))
        if not valid:raise ValueError('scenario variant does not match its claimed experiment kind')
