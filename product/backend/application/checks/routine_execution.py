"""方案修订、公开绑定与当前冻结输入的衔接；不执行目标或保存就绪结论。"""
import re
import time

from pydantic import BaseModel, ConfigDict, Field

from product.backend.domain.boundaries.entities import boundary_sha256
from product.backend.domain.checks.selection import resolve_selected_permissions,permission_key
from product.backend.domain.preparation.requirements import compile_action_assurance
from product.backend.domain.errors import ErrorCode, JiejianError
from product.protocols.codec import content_hash
from product.protocols.checks.check_runtime import check_runtime_fingerprint
from product.protocols.checks.routine_reference import FrozenRoutineReference
from product.protocols.checks.execution_request import PermissionReference
from product.protocols.checks.routines import (CheckRoutineDocument, RoutineBindingDocument, RoutineBoundAsset,
    RoutineLimits, RoutineScope, RoutineRequirement, RoutineActor, RoutineAction, routine_bytes)


class SaveRoutineRevision(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, hide_input_in_errors=True)
    operation_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    routine_id: str | None = Field(default=None, pattern=r'^csp_[0-9a-f]{32}$')
    expected_revision: int = Field(ge=0)
    name: str = Field(min_length=1, max_length=80)
    scope: RoutineScope
    limits: RoutineLimits = RoutineLimits()


class BindRoutine(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, hide_input_in_errors=True)
    operation_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    revision: int = Field(ge=1)
    expected_material_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    expected_environment_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')


def _require(value, message):
    if value is None:
        raise JiejianError(ErrorCode.RECORD_NOT_FOUND, message)
    return value


def bound_assets(request, bundle, document):
    """只输出公开身份和内容引用；请求正文、秘密引用正文与恢复内容不进入方案。"""
    assets, actors, resources = [], {}, {}
    identity_names = {item.identity_id:item.label for item in bundle.identities}
    active_actions={action.action_id for action in request.actions}
    def slot(kind,actor=None,action=None,effect=None):
        return next((item.slot for item in document.requirements or () if item.kind==kind
            and (actor is None or item.actor is not None and (item.actor.actor_id,item.actor.revision)==actor)
            and (action is None or item.action is not None and (item.action.action_id,item.action.revision)==action)
            and (effect is None or item.effect_id==effect)),None)
    for identity in bundle.identities:
        ordinal = actors.get(identity.actor_id, 0) + 1
        actors[identity.actor_id] = ordinal
        assets.append(RoutineBoundAsset(kind='ACCOUNT', label=identity.label, slot=identity.actor_id+':'+str(ordinal),
            reference=identity.identity_id, fingerprint=identity.identity_fingerprint,
            requirement_slot=slot('ACCOUNT',actor=(identity.actor_id,identity.actor_revision))))
    for action in bundle.actions:
        if action.action_id not in active_actions:
            continue
        action_ref=(action.action_id,action.action_revision)
        assets.append(RoutineBoundAsset(kind='FLOW', label=action.display_name, slot=action.action_id, reference=action.flow_id, fingerprint=action.flow_sha256,
            requirement_slot=slot('FLOW',action=action_ref)))
        for index, proof in enumerate(action.proofs):
            assets.append(RoutineBoundAsset(kind='PROOF', label=proof.business_label, slot=action.action_id+':'+proof.effect_id+':'+str(index),
                reference=proof.effect_id, fingerprint=proof.binding_fingerprint,requirement_slot=slot('PROOF',action=action_ref,effect=proof.effect_id)))
    for action in request.actions:
        for case in action.cases:
            key=(action.action_id,action.action_revision,case.resource_owner_test_identity_id,case.resource_id)
            resources.setdefault(key,dict(case=case,bindings=set()))['bindings'].add(case.resource_binding_fingerprint)
    for (action_id,revision,owner,resource),value in resources.items():
        case=value['case'];identity=dict(action_id=action_id,resource_id=resource,owner_id=owner)
        fingerprint=content_hash('RoutineResource',dict(**identity,binding_fingerprints=sorted(value['bindings'])))
        assets.append(RoutineBoundAsset(kind='RESOURCE',label=identity_names[owner]+' · '+resource,
            slot=action_id+':'+content_hash('RoutineResourceSlot',identity)[:24],reference=resource,owner_reference=owner,fingerprint=fingerprint,
            requirement_slot=slot('RESOURCE',action=(action_id,revision),actor=(case.resource_owner_actor_id,case.resource_owner_actor_revision))))
    return tuple(assets)


def missing_requirements(document,assets):
    missing=[]
    for requirement in document.requirements or ():
        rows={((item.owner_reference if item.kind=='RESOURCE' else None),item.reference) for item in assets if item.kind==requirement.kind and item.requirement_slot==requirement.slot}
        if len(rows)<requirement.minimum_count:
            missing.append(requirement.slot)
    return tuple(missing)


class RoutineExecution:
    def __init__(self, uow_factory, boundaries, checks, preparation_reader=None):
        self.uow, self.boundaries, self.checks = uow_factory, boundaries, checks
        self.preparation_reader=preparation_reader

    def _declarations(self, project, scope, work):
        """复制已批准含义的公开要求；纯编译合同及其READY状态不持久化。"""
        boundary=self.boundaries.view(project,work=work)
        selected=scope.permissions
        if scope.scenario is not None:
            scenario=_require(work.business_scenarios.get(project,scope.scenario.scenario_id,scope.scenario.revision),'业务场景修订不存在')
            unique={permission_key(item.permission):item.permission for experiment in scenario.experiments for invocation in experiment.invocations for item in invocation.items}
            selected=tuple(PermissionReference(**item.model_dump(mode='json')) for item in unique.values())
        keys=resolve_selected_permissions(boundary.permission_intents,selected)
        permissions=tuple(item for item in boundary.permission_intents if permission_key(item) in keys)
        actors={(item.actor_id,item.revision):item for item in boundary.actors}
        values={}
        for action in boundary.actions:
            direct=tuple(item for item in permissions if (item.business_action_id,item.action_revision)==(action.action_id,action.revision))
            if not direct:
                continue
            contract=compile_action_assurance(action,direct)
            action_ref=RoutineAction(action_id=action.action_id,revision=action.revision)
            action_slot=action.action_id+'@'+str(action.revision)
            slots={item.slot_id:item for item in contract.identity_requirements.slots}
            counts={}
            for slot in slots.values():
                key=(slot.actor_id,slot.actor_revision)
                counts[key]=counts.get(key,0)+1
            for key,count in counts.items():
                actor=_require(actors.get(key),'方案引用的业务角色修订不可用')
                slot=actor.actor_id+'@'+str(actor.revision)
                previous=values.get(('ACCOUNT',slot))
                values['ACCOUNT',slot]=RoutineRequirement(kind='ACCOUNT',slot=slot,label=actor.display_name,
                    actor=RoutineActor(actor_id=actor.actor_id,revision=actor.revision),minimum_count=max(count,previous.minimum_count if previous else 0))
            values['FLOW',action_slot]=RoutineRequirement(kind='FLOW',slot=action_slot,label=action.display_name,action=action_ref,
                normal_control_required=any(item.expectation.value=='DENY' for item in direct),recovery_required=action.state_changing)
            owners={}
            for resource in contract.resources:
                owner=slots[resource.owner_slot_id];key=(owner.actor_id,owner.actor_revision)
                owners[key]=owners.get(key,0)+1
            for key,count in owners.items():
                actor=_require(actors.get(key),'资源归属角色修订不可用')
                slot=action_slot+':'+actor.actor_id+'@'+str(actor.revision)
                values['RESOURCE',slot]=RoutineRequirement(kind='RESOURCE',slot=slot,label=action.primary_resource_concept+' · '+actor.display_name,
                    action=action_ref,actor=RoutineActor(actor_id=actor.actor_id,revision=actor.revision),minimum_count=count)
            effects={item.effect_id:item for item in action.effect_catalog}
            for proof in contract.effect_evidence:
                effect=effects[proof.effect_id];slot=action_slot+':'+effect.effect_id
                values['PROOF',slot]=RoutineRequirement(kind='PROOF',slot=slot,label=effect.business_label,action=action_ref,effect_id=effect.effect_id)
        order={'ACCOUNT':0,'RESOURCE':1,'FLOW':2,'PROOF':3}
        return tuple(sorted(values.values(),key=lambda item:(order[item.kind],item.slot)))

    def save(self, project, command):
        fingerprint = boundary_sha256(command.model_dump(mode='json'))
        routine_id = command.routine_id or 'csp_'+command.operation_id
        with self.uow() as work:
            work.acquire_write_lock()
            previous = work.routine_revisions.operation(project, command.operation_id)
            if previous is not None:
                if previous[1] != fingerprint:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, '原保存请求已用于其他方案内容')
                return previous[0]
            if work.projects.get(project) is None:
                raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, '应用不存在')
            current = work.routine_revisions.latest(project, routine_id)
            if command.routine_id and current is None and not any(
                item['routine_id'] == routine_id for item in work.check_routines.list(project)):
                raise JiejianError(ErrorCode.RECORD_NOT_FOUND, '原检查方案不存在')
            revision = 0 if current is None else current.revision
            if command.expected_revision != revision:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '检查方案已有新修订，请保留草稿并核对差异',
                    details=dict(reason='ROUTINE_REVISION_CONFLICT', current_revision=revision))
            if command.scope.permissions:
                boundary = self.boundaries.view(project, work=work)
                resolve_selected_permissions(boundary.permission_intents, command.scope.permissions)
            else:
                scenario = command.scope.scenario
                _require(work.business_scenarios.get(project, scenario.scenario_id, scenario.revision), '业务场景修订不存在')
                if not work.business_scenarios.is_reviewed(project, scenario.scenario_id, scenario.revision):
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, '请先审阅并保存这份业务场景')
            document = CheckRoutineDocument(routine_id=routine_id, project_id=project, revision=revision+1,
                name=command.name, scope=command.scope, limits=command.limits,
                requirements=self._declarations(project,command.scope,work),created_at_us=time.time_ns()//1000)
            if len(routine_bytes(document))>1_048_576:
                raise JiejianError(ErrorCode.INPUT_INVALID,'方案公开内容超过单份读取预算，请缩小范围分别保存')
            work.routine_revisions.save(document, command.operation_id, fingerprint)
            work.commit()
            return document

    def read(self, project, routine, revision):
        with self.uow() as work:
            return _require(work.routine_revisions.get(project, routine, revision), '检查方案修订不存在')

    def catalog(self, project, after=None, limit=50):
        if not 1 <= limit <= 50 or after is not None and re.fullmatch(r'csp_[0-9a-f]{32}', after) is None:
            raise JiejianError(ErrorCode.INPUT_INVALID, '方案分页参数无效')
        with self.uow() as work:
            if work.projects.get(project) is None:
                raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, '应用不存在')
            full = work.routine_revisions.summaries(project, after, limit+1)
            legacy = [{key:value for key,value in item.items() if key != 'request_fingerprint'}
                for item in work.check_routines.list(project) if not work.routine_revisions.exists(project, item['routine_id'])] if after is None else []
            return dict(project_id=project, routines=full[:limit], legacy_selections=legacy,
                next_cursor=full[limit-1]['routine_id'] if len(full)>limit else None)

    def history(self, project, routine, before=None):
        with self.uow() as work:
            return work.routine_revisions.history(project, routine, before)

    def bindings(self, project, routine, revision):
        with self.uow() as work:
            _require(work.routine_revisions.get(project, routine, revision), '检查方案修订不存在')
            return work.routine_revisions.bindings(project, routine, revision)

    def _prepare(self, project, document, work=None):
        return self.checks._freeze(project, work=work,
            selected_permissions=document.scope.permissions or None, scenario_reference=document.scope.scenario)

    def binding_preview(self, project, routine, revision):
        document = self.read(project, routine, revision)
        preview, request, bundle = self._prepare(project, document)
        environment = bundle.environment if bundle is not None else None
        if environment is None:
            # 缺少账号等材料不会抹掉已选择的环境；这里只呈现公开配置，不据此声称可绑定。
            with self.uow() as work:
                application=work.application_understanding.get(project)
                environment=None if application is None else application.environment
        assets=() if request is None or bundle is None else bound_assets(request,bundle,document)
        missing=missing_requirements(document,assets)
        from product.backend.application.checks.routine_progress import requirement_progress
        try:
            progress=None if self.preparation_reader is None else self.preparation_reader(project)
        except JiejianError:
            progress=None
        return dict(project_id=project, routine=document, preview=preview, environment=environment,
            environment_fingerprint=None if environment is None else environment.fingerprint,
            material_fingerprint=None if bundle is None else check_runtime_fingerprint(bundle),
            assets=assets,missing_requirement_slots=missing,requirement_progress=requirement_progress(document,assets,progress),
            can_bind=preview.can_execute and environment is not None and not missing)

    def bind(self, project, routine, command):
        binding_id = 'crb_'+command.operation_id
        fingerprint = boundary_sha256(dict(routine_id=routine, command=command.model_dump(mode='json')))
        with self.uow() as work:
            work.acquire_write_lock()
            previous = work.routine_revisions.binding(project, binding_id)
            if previous is not None:
                if previous[1] != fingerprint:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, '原绑定请求已用于其他内容')
                return previous[0]
            document = _require(work.routine_revisions.get(project, routine, command.revision), '检查方案修订不存在')
            preview, request, bundle = self._prepare(project, document, work)
            if not preview.can_execute or request is None or bundle is None or bundle.environment is None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '请先补齐当前环境的真实账号、资源、流程和证明')
            environment = bundle.environment
            material = check_runtime_fingerprint(bundle)
            if material != command.expected_material_fingerprint or environment.fingerprint != command.expected_environment_fingerprint:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '环境或材料已经变化，请重新审阅绑定')
            assets=bound_assets(request,bundle,document)
            if missing_requirements(document,assets):
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'当前材料尚未对应方案声明的逻辑要求，请核对准备与方案修订')
            binding = RoutineBindingDocument(binding_id=binding_id, project_id=project, routine_id=routine,
                routine_revision=document.revision, routine_fingerprint=document.fingerprint,
                environment_id=environment.environment_id, environment_revision=environment.revision,
                environment_fingerprint=environment.fingerprint, material_fingerprint=material,
                assets=assets, created_at_us=time.time_ns()//1000)
            work.routine_revisions.save_binding(binding, fingerprint)
            work.commit()
            return binding

    def resolve(self, project, reference, work):
        document = _require(work.routine_revisions.get(project, reference.routine_id, reference.revision), '检查方案修订不存在')
        binding = _require(work.routine_revisions.binding(project, reference.binding_id), '检查方案环境绑定不存在')[0]
        if (binding.routine_id, binding.routine_revision, binding.routine_fingerprint) != (
            document.routine_id, document.revision, document.fingerprint):
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '这份环境绑定不属于所选方案修订')
        if missing_requirements(document,binding.assets):
            raise JiejianError(ErrorCode.STORAGE_STATE,'方案绑定缺少其声明的准确逻辑对应')
        return document, binding

    def constrain(self, document, binding, bundle):
        if bundle.environment is None or bundle.environment.fingerprint != binding.environment_fingerprint or check_runtime_fingerprint(bundle) != binding.material_fingerprint:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '方案绑定的环境或材料已变化，请保留原绑定并审阅新差异',
                details=dict(reason='ROUTINE_BINDING_CHANGED'))
        budget = bundle.budget.model_copy(update=dict(
            max_duration_us=min(bundle.budget.max_duration_us, document.limits.max_duration_us),
            max_cases=min(bundle.budget.max_cases, document.limits.max_cases)))
        return bundle.model_copy(update=dict(budget=budget))

    def frozen_reference(self, document, binding):
        return FrozenRoutineReference(routine_id=document.routine_id, revision=document.revision,
            binding_id=binding.binding_id, routine_fingerprint=document.fingerprint, binding_fingerprint=binding.fingerprint)
