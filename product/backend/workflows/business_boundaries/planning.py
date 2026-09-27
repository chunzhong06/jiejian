# 在同一审批事务中构造完整写入计划；此模块不提交事务。
from __future__ import annotations
from product.backend.core.boundaries.permissions import permission_relation_consistent
from dataclasses import dataclass
from uuid import uuid4
from product.backend.core.boundaries.approval import HumanApproval
from product.backend.core.applications.models import ApplicationUnderstanding
from product.backend.core.boundaries.proposals import BoundaryProposalBundle, ProposalWriteMode, ProposedActionItem, ProposedActorItem, ProposedPermissionItem
from product.backend.core.boundaries.entities import ActionImplementationBinding, ActorImplementationBinding, BusinessAction, BusinessActionRevision, BusinessActor, BusinessActorRevision, BusinessEffectDefinition, BusinessRevisionState, boundary_sha256
from product.backend.core.errors import ErrorCode
from product.backend.core.boundaries.permissions import PermissionIntentEffectiveState, PermissionIntentSemantic
from product.backend.infra.storage import StorageUnitOfWork
from . import sources as boundary_sources
from . import validation as boundary_validation

@dataclass(frozen=True)
class _ActorPlan:
    item: ProposedActorItem
    root: BusinessActor
    revision: BusinessActorRevision
    binding: ActorImplementationBinding | None
    write_revision: bool
    write_binding: bool
    create_root: bool


@dataclass(frozen=True)
class _ActionPlan:
    item: ProposedActionItem
    root: BusinessAction
    revision: BusinessActionRevision
    effect_ids: dict[str, str]
    binding: ActionImplementationBinding | None
    write_revision: bool
    write_binding: bool
    create_root: bool


@dataclass(frozen=True)
class _PermissionPlan:
    item: ProposedPermissionItem
    semantic: PermissionIntentSemantic
    intent_id: str
    revision: int
    write_revision: bool


def _plan_actors(work: StorageUnitOfWork,
    proposal: BoundaryProposalBundle,
    approval: HumanApproval,
    understanding: ApplicationUnderstanding,
    now_us: int,
) -> tuple[_ActorPlan, ...]:
    plans: list[_ActorPlan] = []
    for item in proposal.proposed_actors:
        if item.write_mode is ProposalWriteMode.CREATE:
            actor_id = f"bar_{uuid4().hex}"
            revision_number = 1
            current = None
        else:
            assert item.actor_id is not None and item.expected_current_revision is not None
            actor_id = item.actor_id
            current = work.business_boundaries.actor(actor_id)
            if (
                current is None
                or current.project_id != proposal.project_id
                or current.current_revision != item.expected_current_revision
            ):
                boundary_validation._raise(ErrorCode.BOUNDARY_REVISION_CONFLICT, "业务主体当前 revision 已变化")
            revision_number = (
                current.current_revision
                if item.write_mode is ProposalWriteMode.REFERENCE
                else current.current_revision + 1
            )
        fingerprint = boundary_sha256(
            {
                "actor_id": actor_id,
                "project_id": proposal.project_id,
                "display_name": item.display_name,
                "description": item.description,
                "effective_state": item.effective_state.value,
            }
        )
        revision = BusinessActorRevision(
            actor_id=actor_id,
            project_id=proposal.project_id,
            revision=revision_number,
            display_name=item.display_name,
            description=item.description,
            semantic_fingerprint=fingerprint,
            effective_state=item.effective_state,
            approval=approval,
            created_at_us=now_us,
        )
        if item.write_mode is ProposalWriteMode.REFERENCE:
            stored = work.business_boundaries.actor_revision(actor_id, revision_number)
            if stored is None or stored.semantic_fingerprint != fingerprint:
                boundary_validation._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "业务主体引用与当前事实不一致")
            revision = stored
            assert current is not None
            root = current
            write_revision = False
            create_root = False
        else:
            if current is not None:
                previous = work.business_boundaries.actor_revision(actor_id, current.current_revision)
                if previous is not None and previous.semantic_fingerprint == fingerprint:
                    boundary_validation._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "业务主体新 revision 没有语义变化")
                root = BusinessActor(
                    actor_id=actor_id,
                    project_id=proposal.project_id,
                    current_revision=revision_number,
                    created_at_us=current.created_at_us,
                    updated_at_us=now_us,
                )
                create_root = False
            else:
                root = BusinessActor(
                    actor_id=actor_id,
                    project_id=proposal.project_id,
                    current_revision=1,
                    created_at_us=now_us,
                    updated_at_us=now_us,
                )
                create_root = True
            write_revision = True
        replacement = boundary_sources._actor_binding(
            item,
            revision,
            proposal.proposal_id,
            understanding,
            now_us,
        )
        stored_binding = work.business_boundaries.actor_binding(
            revision.actor_id,
            revision.revision,
        )
        write_binding = write_revision or boundary_sources._binding_changed(
            stored_binding,
            replacement,
        )
        plans.append(
            _ActorPlan(
                item,
                root,
                revision,
                replacement if write_binding else None,
                write_revision,
                write_binding,
                create_root,
            )
        )
    return tuple(plans)


def _plan_actions(work: StorageUnitOfWork,
    proposal: BoundaryProposalBundle,
    approval: HumanApproval,
    understanding: ApplicationUnderstanding,
    now_us: int,
) -> tuple[_ActionPlan, ...]:
    plans: list[_ActionPlan] = []
    for item in proposal.proposed_actions:
        current_revision: BusinessActionRevision | None = None
        if item.write_mode is ProposalWriteMode.CREATE:
            action_id = f"bac_{uuid4().hex}"
            revision_number = 1
            current = None
        else:
            assert item.action_id is not None and item.expected_current_revision is not None
            action_id = item.action_id
            current = work.business_boundaries.action(action_id)
            if (
                current is None
                or current.project_id != proposal.project_id
                or current.current_revision != item.expected_current_revision
            ):
                boundary_validation._raise(ErrorCode.BOUNDARY_REVISION_CONFLICT, "业务动作当前 revision 已变化")
            current_revision = work.business_boundaries.action_revision(action_id, current.current_revision)
            if current_revision is None:
                boundary_validation._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "业务动作 revision 不存在")
            revision_number = (
                current.current_revision
                if item.write_mode is ProposalWriteMode.REFERENCE
                else current.current_revision + 1
            )
        effects, effect_ids = _resolve_effects(item, current_revision)
        semantic_payload = {
            "action_id": action_id,
            "project_id": proposal.project_id,
            "display_name": item.display_name,
            "description": item.description,
            "primary_resource_concept": item.primary_resource_concept,
            "operation_kind": item.operation_kind.value,
            "state_changing": item.state_changing,
            "effect_catalog": [effect.model_dump(mode="json") for effect in effects],
            "effective_state": item.effective_state.value,
        }
        fingerprint = boundary_sha256(semantic_payload)
        revision = BusinessActionRevision(
            action_id=action_id,
            project_id=proposal.project_id,
            revision=revision_number,
            display_name=item.display_name,
            description=item.description,
            primary_resource_concept=item.primary_resource_concept,
            operation_kind=item.operation_kind,
            state_changing=item.state_changing,
            effect_catalog=effects,
            semantic_fingerprint=fingerprint,
            effective_state=item.effective_state,
            approval=approval,
            created_at_us=now_us,
        )
        if item.write_mode is ProposalWriteMode.REFERENCE:
            assert current_revision is not None and current is not None
            if current_revision.semantic_fingerprint != fingerprint:
                boundary_validation._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "业务动作引用与当前事实不一致")
            revision = current_revision
            root = current
            write_revision = False
            create_root = False
        else:
            if current is not None:
                assert current_revision is not None
                if current_revision.semantic_fingerprint == fingerprint:
                    boundary_validation._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "业务动作新 revision 没有语义变化")
                root = BusinessAction(
                    action_id=action_id,
                    project_id=proposal.project_id,
                    current_revision=revision_number,
                    created_at_us=current.created_at_us,
                    updated_at_us=now_us,
                )
                create_root = False
            else:
                root = BusinessAction(
                    action_id=action_id,
                    project_id=proposal.project_id,
                    current_revision=1,
                    created_at_us=now_us,
                    updated_at_us=now_us,
                )
                create_root = True
            write_revision = True
        replacement = boundary_sources._action_binding(
            item,
            revision,
            proposal.proposal_id,
            understanding,
            now_us,
        )
        stored_binding = work.business_boundaries.action_binding(
            revision.action_id,
            revision.revision,
        )
        write_binding = write_revision or boundary_sources._binding_changed(
            stored_binding,
            replacement,
        )
        plans.append(
            _ActionPlan(
                item,
                root,
                revision,
                effect_ids,
                replacement if write_binding else None,
                write_revision,
                write_binding,
                create_root,
            )
        )
    return tuple(plans)


def _resolve_effects(item: ProposedActionItem,
    current: BusinessActionRevision | None,
) -> tuple[tuple[BusinessEffectDefinition, ...], dict[str, str]]:
    existing = {} if current is None else {effect.effect_id: effect for effect in current.effect_catalog}
    effects: list[BusinessEffectDefinition] = []
    local_to_formal: dict[str, str] = {}
    for proposed in item.effect_catalog:
        if item.write_mode is ProposalWriteMode.CREATE and proposed.effect_id is not None:
            boundary_validation._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "新业务动作不能指定正式 Effect ID")
        effect_id = proposed.effect_id or f"bef_{uuid4().hex}"
        effect = boundary_sources._effect(effect_id, proposed)
        if proposed.effect_id is not None:
            if proposed.effect_id not in existing or existing[proposed.effect_id] != effect:
                boundary_validation._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "复用 Effect 与冻结定义不一致")
        effects.append(effect)
        local_to_formal[proposed.item_id] = effect_id
    # 正式指纹与领域对象使用相同的 effect_id 规范顺序，本地提案标识顺序不构成业务语义。
    return tuple(sorted(effects, key=lambda effect: effect.effect_id)), local_to_formal


def _plan_permissions(work: StorageUnitOfWork,
    proposal: BoundaryProposalBundle,
    actors: tuple[_ActorPlan, ...],
    actions: tuple[_ActionPlan, ...],
) -> tuple[_PermissionPlan, ...]:
    actor_by_item = {plan.item.item_id: plan.revision for plan in actors}
    action_by_item = {plan.item.item_id: plan for plan in actions}
    plans: list[_PermissionPlan] = []
    for item in proposal.proposed_permissions:
        subject = actor_by_item[item.subject_actor_item_id]
        owner = actor_by_item[item.resource_owner_actor_item_id]
        if not permission_relation_consistent(
            item.relation, (subject.actor_id, subject.revision), (owner.actor_id, owner.revision)
        ):
            boundary_validation._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "权限资源关系与业务主体不一致")
        action_plan = action_by_item[item.business_action_item_id]
        action = action_plan.revision
        protected_ids = tuple(action_plan.effect_ids[value] for value in item.protected_effect_item_ids)
        if item.effective_state is PermissionIntentEffectiveState.ACTIVE and (
            subject.effective_state is not BusinessRevisionState.ACTIVE
            or owner.effective_state is not BusinessRevisionState.ACTIVE
            or action.effective_state is not BusinessRevisionState.ACTIVE
        ):
            boundary_validation._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "ACTIVE 权限必须引用 ACTIVE 业务 revision")
        semantic = PermissionIntentSemantic(
            effective_state=item.effective_state,
            subject_actor_id=subject.actor_id,
            subject_actor_revision=subject.revision,
            business_action_id=action.action_id,
            action_revision=action.revision,
            resource_owner_actor_id=owner.actor_id,
            resource_owner_actor_revision=owner.revision,
            relation=item.relation,
            expectation=item.expectation,
            protected_effect_ids=protected_ids,
        )
        if item.write_mode is ProposalWriteMode.CREATE:
            intent_id = f"pin_{uuid4().hex}"
            revision_number = 1
            write_revision = True
        else:
            assert item.intent_id is not None and item.expected_current_revision is not None
            latest = work.permission_intents.latest(item.intent_id)
            if (
                latest is None
                or latest.project_id != proposal.project_id
                or latest.revision != item.expected_current_revision
            ):
                boundary_validation._raise(ErrorCode.BOUNDARY_REVISION_CONFLICT, "权限当前 revision 已变化")
            current_semantic = PermissionIntentSemantic.model_validate(
                latest.model_dump(include=set(PermissionIntentSemantic.model_fields))
            )
            if item.write_mode is ProposalWriteMode.REFERENCE:
                if current_semantic != semantic:
                    boundary_validation._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "权限引用与当前事实不一致")
                revision_number = latest.revision
                write_revision = False
            else:
                if current_semantic == semantic:
                    boundary_validation._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "权限新 revision 没有语义变化")
                revision_number = latest.revision + 1
                write_revision = True
            intent_id = item.intent_id
        plans.append(_PermissionPlan(item, semantic, intent_id, revision_number, write_revision))
    return tuple(plans)
