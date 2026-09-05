# 把当前正式业务边界转换为稳定维护草稿，并由 desired state 生成不可变 Proposal。

from __future__ import annotations

from product.backend.core.application_understanding import (
    ApplicationUnderstanding,
    CandidateDecision,
)
from product.backend.core.boundary_proposal import (
    BoundaryProposalBundle,
    ProposalCandidateKind,
    ProposalWriteMode,
    ProposedActionItem,
    ProposedActorItem,
    ProposedEffectItem,
    ProposedPermissionItem,
)
from product.backend.core.business_boundary import (
    ActionImplementationBinding,
    ActorImplementationBinding,
    BusinessAction,
    BusinessActionRevision,
    BusinessActor,
    BusinessActorRevision,
    BusinessEffectDefinition,
    BusinessRevisionState,
    ImplementationCandidateSnapshot,
    boundary_sha256,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.permission_intent import (
    PermissionIntentEffectiveState,
    PermissionIntentRevision,
    PermissionIntentSemantic,
)
from product.backend.workflows.business_boundaries.inspection import (
    ActionImplementationInspection,
    ActorImplementationInspection,
)
from product.backend.workflows.business_boundaries.models import (
    BoundaryMaintenanceActionItem,
    BoundaryMaintenanceActorItem,
    BoundaryMaintenanceCandidateOption,
    BoundaryMaintenanceCommand,
    BoundaryMaintenanceDraftView,
    BoundaryMaintenancePermissionItem,
    BoundaryProposalChangeSummary,
    BoundaryProposalCommand,
)


def boundary_state_fingerprint(
    project_id: str,
    actors: tuple[BusinessActor, ...],
    actions: tuple[BusinessAction, ...],
    permissions: tuple[PermissionIntentRevision, ...],
    policy_epoch: int,
) -> str:
    """只覆盖正式 current identity/revision 与权限 epoch，不绑定 discovery。"""

    return boundary_sha256(
        {
            "project_id": project_id,
            "actors": sorted(
                (item.actor_id, item.current_revision) for item in actors
            ),
            "actions": sorted(
                (item.action_id, item.current_revision) for item in actions
            ),
            "permissions": sorted(
                (item.intent_id, item.revision) for item in permissions
            ),
            "policy_epoch": policy_epoch,
        }
    )


def build_maintenance_draft(
    project_id: str,
    actor_roots: tuple[BusinessActor, ...],
    action_roots: tuple[BusinessAction, ...],
    actors: tuple[BusinessActorRevision, ...],
    actions: tuple[BusinessActionRevision, ...],
    permissions: tuple[PermissionIntentRevision, ...],
    actor_inspections: tuple[ActorImplementationInspection, ...],
    action_inspections: tuple[ActionImplementationInspection, ...],
    understanding: ApplicationUnderstanding,
    policy_epoch: int,
) -> BoundaryMaintenanceDraftView:
    """用正式 identity 生成可刷新且 local item ID 稳定的完整 desired state。"""

    actor_inspection_by_id = {item.actor_id: item for item in actor_inspections}
    action_inspection_by_id = {item.action_id: item for item in action_inspections}
    actor_items = tuple(
        BoundaryMaintenanceActorItem(
            item_id=_local_id("pactr", {"actor_id": item.actor_id}),
            actor_id=item.actor_id,
            expected_current_revision=item.revision,
            display_name=item.display_name,
            description=item.description,
            effective_state=item.effective_state,
            source_candidate_ids=(
                actor_inspection_by_id[item.actor_id].source_candidate_ids
                if item.actor_id in actor_inspection_by_id
                else ()
            ),
        )
        for item in sorted(actors, key=lambda value: value.actor_id)
    )
    action_items = tuple(
        BoundaryMaintenanceActionItem(
            item_id=_local_id("pactn", {"action_id": item.action_id}),
            action_id=item.action_id,
            expected_current_revision=item.revision,
            display_name=item.display_name,
            description=item.description,
            primary_resource_concept=item.primary_resource_concept,
            operation_kind=item.operation_kind,
            state_changing=item.state_changing,
            effects=tuple(
                ProposedEffectItem(
                    item_id=_local_id(
                        "peff",
                        {"action_id": item.action_id, "effect_id": effect.effect_id},
                    ),
                    **effect.model_dump(),
                )
                for effect in item.effect_catalog
            ),
            effective_state=item.effective_state,
            source_candidate_ids=(
                action_inspection_by_id[item.action_id].source_candidate_ids
                if item.action_id in action_inspection_by_id
                else ()
            ),
        )
        for item in sorted(actions, key=lambda value: value.action_id)
    )
    actor_item_by_id = {item.actor_id: item.item_id for item in actor_items}
    action_item_by_id = {item.action_id: item.item_id for item in action_items}
    effect_item_by_id = {
        (action.action_id, effect.effect_id): effect.item_id
        for action in action_items
        for effect in action.effects
        if action.action_id is not None and effect.effect_id is not None
    }
    permission_items: list[BoundaryMaintenancePermissionItem] = []
    for item in sorted(permissions, key=lambda value: value.intent_id):
        if (
            item.subject_actor_id not in actor_item_by_id
            or item.resource_owner_actor_id not in actor_item_by_id
            or item.business_action_id not in action_item_by_id
        ):
            raise JiejianError(
                ErrorCode.BOUNDARY_MAINTENANCE_INCOMPLETE,
                "当前权限无法映射到正式业务边界",
                details={"intent_id": item.intent_id},
            )
        protected_items = tuple(
            effect_item_by_id.get(
                (item.business_action_id, effect_id),
                _local_id(
                    "peff",
                    {
                        "action_id": item.business_action_id,
                        "missing_effect_id": effect_id,
                    },
                ),
            )
            for effect_id in item.protected_effect_ids
        )
        permission_items.append(
            BoundaryMaintenancePermissionItem(
                item_id=_local_id("pperm", {"intent_id": item.intent_id}),
                intent_id=item.intent_id,
                expected_current_revision=item.revision,
                effective_state=item.effective_state,
                subject_actor_item_id=actor_item_by_id[item.subject_actor_id],
                business_action_item_id=action_item_by_id[item.business_action_id],
                resource_owner_actor_item_id=actor_item_by_id[
                    item.resource_owner_actor_id
                ],
                relation=item.relation,
                expectation=item.expectation,
                protected_effect_item_ids=protected_items,
            )
        )
    options = tuple(
        sorted(
            (
                *(
                    BoundaryMaintenanceCandidateOption(
                        candidate_kind=ProposalCandidateKind.ROLE,
                        candidate_id=item.candidate_id,
                        display_name=item.display_name,
                        confidence=item.confidence.value,
                        evidence_available=bool(item.evidence),
                    )
                    for item in understanding.role_candidates
                    if not item.stale
                    and item.decision is not CandidateDecision.REJECTED
                ),
                *(
                    BoundaryMaintenanceCandidateOption(
                        candidate_kind=ProposalCandidateKind.ACTION,
                        candidate_id=item.candidate_id,
                        display_name=item.display_name,
                        confidence=item.confidence.value,
                        evidence_available=bool(item.evidence),
                    )
                    for item in understanding.action_candidates
                    if not item.stale
                    and item.decision is not CandidateDecision.REJECTED
                ),
            ),
            key=lambda item: (item.candidate_kind.value, item.candidate_id),
        )
    )
    inspections = tuple(
        sorted(
            (*actor_inspections, *action_inspections),
            key=lambda item: (
                "ACTOR" if isinstance(item, ActorImplementationInspection) else "ACTION",
                item.actor_id
                if isinstance(item, ActorImplementationInspection)
                else item.action_id,
            ),
        )
    )
    return BoundaryMaintenanceDraftView(
        project_id=project_id,
        boundary_state_fingerprint=boundary_state_fingerprint(
            project_id,
            actor_roots,
            action_roots,
            permissions,
            policy_epoch,
        ),
        actors=actor_items,
        actions=action_items,
        permissions=tuple(permission_items),
        candidate_options=options,
        implementation_inspections=inspections,
    )


def maintenance_to_proposal_command(
    project_id: str,
    command: BoundaryMaintenanceCommand,
    actor_roots: tuple[BusinessActor, ...],
    action_roots: tuple[BusinessAction, ...],
    actors: tuple[BusinessActorRevision, ...],
    actions: tuple[BusinessActionRevision, ...],
    permissions: tuple[PermissionIntentRevision, ...],
    policy_epoch: int,
) -> BoundaryProposalCommand:
    """验证完整 desired state，并由服务端独占决定每个 Proposal write mode。"""

    actual_fingerprint = boundary_state_fingerprint(
        project_id,
        actor_roots,
        action_roots,
        permissions,
        policy_epoch,
    )
    if command.expected_boundary_state_fingerprint != actual_fingerprint:
        raise JiejianError(
            ErrorCode.BOUNDARY_REVISION_CONFLICT,
            "业务边界已变化，请刷新维护草稿",
        )
    actor_by_id = {item.actor_id: item for item in actors}
    action_by_id = {item.action_id: item for item in actions}
    permission_by_id = {item.intent_id: item for item in permissions}
    _require_unique_formal(
        "actor_id",
        tuple(item.actor_id for item in command.actors if item.actor_id is not None),
    )
    _require_unique_formal(
        "action_id",
        tuple(item.action_id for item in command.actions if item.action_id is not None),
    )
    _require_unique_formal(
        "intent_id",
        tuple(
            item.intent_id for item in command.permissions if item.intent_id is not None
        ),
    )
    _require_complete(
        "actor_id",
        set(actor_by_id),
        {item.actor_id for item in command.actors if item.actor_id is not None},
    )
    _require_complete(
        "action_id",
        set(action_by_id),
        {item.action_id for item in command.actions if item.action_id is not None},
    )
    _require_complete(
        "intent_id",
        set(permission_by_id),
        {item.intent_id for item in command.permissions if item.intent_id is not None},
    )

    proposed_actors: list[ProposedActorItem] = []
    actor_formal_by_item: dict[str, str | None] = {}
    actor_revision_by_item: dict[str, int] = {}
    actor_state_by_item: dict[str, BusinessRevisionState] = {}
    for item in command.actors:
        current = None if item.actor_id is None else actor_by_id[item.actor_id]
        if current is not None and item.expected_current_revision != current.revision:
            raise JiejianError(
                ErrorCode.BOUNDARY_REVISION_CONFLICT,
                "业务主体 current revision 已变化",
            )
        same = current is not None and (
            item.display_name == current.display_name
            and item.description == current.description
            and item.effective_state is current.effective_state
        )
        mode = (
            ProposalWriteMode.CREATE
            if current is None
            else ProposalWriteMode.REFERENCE
            if same
            else ProposalWriteMode.APPEND_REVISION
        )
        proposed_actors.append(
            ProposedActorItem(
                item_id=item.item_id,
                write_mode=mode,
                actor_id=item.actor_id,
                expected_current_revision=item.expected_current_revision,
                display_name=item.display_name,
                description=item.description,
                effective_state=item.effective_state,
                source_candidate_ids=item.source_candidate_ids,
            )
        )
        actor_formal_by_item[item.item_id] = item.actor_id
        actor_revision_by_item[item.item_id] = (
            1
            if current is None
            else current.revision + (mode is ProposalWriteMode.APPEND_REVISION)
        )
        actor_state_by_item[item.item_id] = item.effective_state

    proposed_actions: list[ProposedActionItem] = []
    action_formal_by_item: dict[str, str | None] = {}
    action_revision_by_item: dict[str, int] = {}
    action_state_by_item: dict[str, BusinessRevisionState] = {}
    effect_formal_by_action_item: dict[str, dict[str, str | None]] = {}
    for item in command.actions:
        current = None if item.action_id is None else action_by_id[item.action_id]
        if current is not None and item.expected_current_revision != current.revision:
            raise JiejianError(
                ErrorCode.BOUNDARY_REVISION_CONFLICT,
                "业务动作 current revision 已变化",
            )
        current_effects = (
            {} if current is None else {effect.effect_id: effect for effect in current.effect_catalog}
        )
        effects: list[ProposedEffectItem] = []
        effect_formal: dict[str, str | None] = {}
        for desired in item.effects:
            if current is None and desired.effect_id is not None:
                raise JiejianError(
                    ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID,
                    "新业务动作不能引用正式 Effect",
                )
            retained_id = desired.effect_id
            if desired.effect_id is not None:
                existing = current_effects.get(desired.effect_id)
                if existing is None:
                    raise JiejianError(
                        ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID,
                        "Effect 不属于当前业务动作",
                    )
                if existing != _business_effect(desired.effect_id, desired):
                    retained_id = None
            proposed = desired.model_copy(update={"effect_id": retained_id})
            effects.append(proposed)
            effect_formal[desired.item_id] = retained_id
        same = current is not None and _action_semantics_equal(item, effects, current)
        mode = (
            ProposalWriteMode.CREATE
            if current is None
            else ProposalWriteMode.REFERENCE
            if same
            else ProposalWriteMode.APPEND_REVISION
        )
        proposed_actions.append(
            ProposedActionItem(
                item_id=item.item_id,
                write_mode=mode,
                action_id=item.action_id,
                expected_current_revision=item.expected_current_revision,
                display_name=item.display_name,
                description=item.description,
                primary_resource_concept=item.primary_resource_concept,
                operation_kind=item.operation_kind,
                state_changing=item.state_changing,
                effect_catalog=tuple(effects),
                effective_state=item.effective_state,
                source_candidate_ids=item.source_candidate_ids,
            )
        )
        action_formal_by_item[item.item_id] = item.action_id
        action_revision_by_item[item.item_id] = (
            1
            if current is None
            else current.revision + (mode is ProposalWriteMode.APPEND_REVISION)
        )
        action_state_by_item[item.item_id] = item.effective_state
        effect_formal_by_action_item[item.item_id] = effect_formal

    proposed_permissions: list[ProposedPermissionItem] = []
    for item in command.permissions:
        current = None if item.intent_id is None else permission_by_id[item.intent_id]
        if current is not None and item.expected_current_revision != current.revision:
            raise JiejianError(
                ErrorCode.BOUNDARY_REVISION_CONFLICT,
                "权限 current revision 已变化",
            )
        missing_refs = tuple(
            value
            for value in (
                item.subject_actor_item_id,
                item.resource_owner_actor_item_id,
                item.business_action_item_id,
            )
            if value
            not in (
                actor_formal_by_item
                if value.startswith("pactr_")
                else action_formal_by_item
            )
        )
        if missing_refs:
            raise JiejianError(
                ErrorCode.BOUNDARY_MAINTENANCE_INCOMPLETE,
                "权限引用的业务项目不在完整维护命令中",
                details={"missing_item_ids": missing_refs},
            )
        effect_formal = effect_formal_by_action_item[item.business_action_item_id]
        missing_effects = tuple(
            value for value in item.protected_effect_item_ids if value not in effect_formal
        )
        if missing_effects:
            raise JiejianError(
                ErrorCode.BOUNDARY_EFFECT_MAPPING_REQUIRED,
                "权限保护结果已变化，请明确选择当前业务结果",
                details={
                    "intent_id": item.intent_id,
                    "action_item_id": item.business_action_item_id,
                    "missing_effect_item_ids": missing_effects,
                },
            )
        if item.effective_state is PermissionIntentEffectiveState.ACTIVE and (
            actor_state_by_item[item.subject_actor_item_id]
            is not BusinessRevisionState.ACTIVE
            or actor_state_by_item[item.resource_owner_actor_item_id]
            is not BusinessRevisionState.ACTIVE
            or action_state_by_item[item.business_action_item_id]
            is not BusinessRevisionState.ACTIVE
        ):
            raise JiejianError(
                ErrorCode.BOUNDARY_MAINTENANCE_INCOMPLETE,
                "退休业务边界仍有未闭合的 ACTIVE 权限",
                details={"intent_id": item.intent_id},
            )
        formal_effect_ids = tuple(
            effect_formal[value] for value in item.protected_effect_item_ids
        )
        all_formal = (
            actor_formal_by_item[item.subject_actor_item_id] is not None
            and actor_formal_by_item[item.resource_owner_actor_item_id] is not None
            and action_formal_by_item[item.business_action_item_id] is not None
            and all(value is not None for value in formal_effect_ids)
        )
        same = False
        if current is not None and all_formal:
            desired_semantic = PermissionIntentSemantic(
                effective_state=item.effective_state,
                subject_actor_id=actor_formal_by_item[item.subject_actor_item_id],
                subject_actor_revision=actor_revision_by_item[
                    item.subject_actor_item_id
                ],
                business_action_id=action_formal_by_item[
                    item.business_action_item_id
                ],
                action_revision=action_revision_by_item[item.business_action_item_id],
                resource_owner_actor_id=actor_formal_by_item[
                    item.resource_owner_actor_item_id
                ],
                resource_owner_actor_revision=actor_revision_by_item[
                    item.resource_owner_actor_item_id
                ],
                relation=item.relation,
                expectation=item.expectation,
                protected_effect_ids=formal_effect_ids,
            )
            current_semantic = PermissionIntentSemantic.model_validate(
                current.model_dump(include=set(PermissionIntentSemantic.model_fields))
            )
            same = desired_semantic == current_semantic
        mode = (
            ProposalWriteMode.CREATE
            if current is None
            else ProposalWriteMode.REFERENCE
            if same
            else ProposalWriteMode.APPEND_REVISION
        )
        proposed_permissions.append(
            ProposedPermissionItem(
                item_id=item.item_id,
                write_mode=mode,
                intent_id=item.intent_id,
                expected_current_revision=item.expected_current_revision,
                effective_state=item.effective_state,
                subject_actor_item_id=item.subject_actor_item_id,
                business_action_item_id=item.business_action_item_id,
                resource_owner_actor_item_id=item.resource_owner_actor_item_id,
                relation=item.relation,
                expectation=item.expectation,
                protected_effect_item_ids=item.protected_effect_item_ids,
            )
        )
    return BoundaryProposalCommand(
        proposed_actors=tuple(proposed_actors),
        proposed_actions=tuple(proposed_actions),
        proposed_permissions=tuple(proposed_permissions),
        unresolved_questions=(),
        provenance=command.provenance,
    )


def proposal_change_summary(
    proposal: BoundaryProposalBundle,
    permissions: tuple[PermissionIntentRevision, ...],
    actor_bindings: tuple[ActorImplementationBinding, ...],
    action_bindings: tuple[ActionImplementationBinding, ...],
) -> BoundaryProposalChangeSummary:
    """从不可变 Proposal 与批准前当前 facts 形成确定性审阅摘要。"""

    actor_by_item = {item.item_id: item for item in proposal.proposed_actors}
    action_by_item = {item.item_id: item for item in proposal.proposed_actions}
    latest_by_id = {item.intent_id: item for item in permissions}
    actor_binding_by_key = {
        (item.actor_id, item.actor_revision): item for item in actor_bindings
    }
    action_binding_by_key = {
        (item.action_id, item.action_revision): item for item in action_bindings
    }
    business_updates: list[str] = []
    retirements: list[str] = []
    rebinds: list[str] = []
    for item in proposal.proposed_actors:
        if item.write_mode is ProposalWriteMode.APPEND_REVISION:
            (retirements if item.effective_state is BusinessRevisionState.RETIRED else business_updates).append(
                item.display_name
            )
        if item.write_mode is ProposalWriteMode.REFERENCE and item.actor_id is not None:
            binding = actor_binding_by_key.get(
                (item.actor_id, item.expected_current_revision or 0)
            )
            if _binding_changed(
                binding,
                item.source_candidate_ids,
                proposal,
                ProposalCandidateKind.ROLE,
            ):
                rebinds.append(item.display_name)
    for item in proposal.proposed_actions:
        if item.write_mode is ProposalWriteMode.APPEND_REVISION:
            (retirements if item.effective_state is BusinessRevisionState.RETIRED else business_updates).append(
                item.display_name
            )
        if item.write_mode is ProposalWriteMode.REFERENCE and item.action_id is not None:
            binding = action_binding_by_key.get(
                (item.action_id, item.expected_current_revision or 0)
            )
            if _binding_changed(
                binding,
                item.source_candidate_ids,
                proposal,
                ProposalCandidateKind.ACTION,
            ):
                rebinds.append(item.display_name)
    permission_updates: list[str] = []
    carry_forwards: list[str] = []
    permission_retirements: list[str] = []
    for item in proposal.proposed_permissions:
        if item.write_mode is ProposalWriteMode.CREATE:
            permission_updates.append(
                _permission_label(item, actor_by_item, action_by_item)
            )
            continue
        if item.write_mode is not ProposalWriteMode.APPEND_REVISION:
            continue
        label = _permission_label(item, actor_by_item, action_by_item)
        if item.effective_state is PermissionIntentEffectiveState.RETIRED:
            permission_retirements.append(label)
        elif _is_carry_forward(item, latest_by_id, actor_by_item, action_by_item):
            carry_forwards.append(label)
        else:
            permission_updates.append(label)
    return BoundaryProposalChangeSummary(
        new_actor_count=sum(
            item.write_mode is ProposalWriteMode.CREATE
            for item in proposal.proposed_actors
        ),
        new_action_count=sum(
            item.write_mode is ProposalWriteMode.CREATE
            for item in proposal.proposed_actions
        ),
        business_revision_updates=tuple(sorted(business_updates)),
        retirements=tuple(sorted(retirements)),
        permission_updates=tuple(sorted(permission_updates)),
        permission_carry_forwards=tuple(sorted(carry_forwards)),
        permission_retirements=tuple(sorted(permission_retirements)),
        implementation_rebinds=tuple(sorted(rebinds)),
        unresolved_count=len(proposal.unresolved_questions),
        change_codes=tuple(
            code
            for code, present in (
                ("BUSINESS_REVISION_UPDATE", bool(business_updates)),
                ("RETIREMENT", bool(retirements or permission_retirements)),
                ("PERMISSION_UPDATE", bool(permission_updates)),
                ("CARRY_FORWARD_PERMISSION", bool(carry_forwards)),
                ("IMPLEMENTATION_REBIND", bool(rebinds)),
                ("UNRESOLVED_QUESTION", bool(proposal.unresolved_questions)),
            )
            if present
        ),
    )


def _require_complete(field: str, expected: set[str], actual: set[str]) -> None:
    if expected == actual:
        return
    raise JiejianError(
        ErrorCode.BOUNDARY_MAINTENANCE_INCOMPLETE,
        "维护命令必须显式包含全部当前业务对象",
        details={
            "field": field,
            "missing": tuple(sorted(expected - actual)),
            "unexpected": tuple(sorted(actual - expected)),
        },
    )


def _require_unique_formal(field: str, values: tuple[str, ...]) -> None:
    if len(values) == len(set(values)):
        return
    raise JiejianError(
        ErrorCode.BOUNDARY_MAINTENANCE_INCOMPLETE,
        "维护命令中的正式 identity 必须唯一",
        details={"field": field},
    )


def _local_id(prefix: str, payload: dict[str, str]) -> str:
    return f"{prefix}_{boundary_sha256(payload)[:16]}"


def _business_effect(effect_id: str, item: ProposedEffectItem) -> BusinessEffectDefinition:
    return BusinessEffectDefinition(
        effect_id=effect_id,
        business_label=item.business_label,
        effect_kind=item.effect_kind,
        resource_concept=item.resource_concept,
        expected_state=item.expected_state,
        protected_projection=item.protected_projection,
        description=item.description,
    )


def _action_semantics_equal(
    item: BoundaryMaintenanceActionItem,
    effects: list[ProposedEffectItem],
    current: BusinessActionRevision,
) -> bool:
    if not (
        item.display_name == current.display_name
        and item.description == current.description
        and item.primary_resource_concept == current.primary_resource_concept
        and item.operation_kind is current.operation_kind
        and item.state_changing is current.state_changing
        and item.effective_state is current.effective_state
        and len(effects) == len(current.effect_catalog)
    ):
        return False
    current_effects = {effect.effect_id: effect for effect in current.effect_catalog}
    return all(
        effect.effect_id is not None
        and current_effects.get(effect.effect_id)
        == _business_effect(effect.effect_id, effect)
        for effect in effects
    )


def _binding_changed(
    binding: ActorImplementationBinding | ActionImplementationBinding | None,
    candidate_ids: tuple[str, ...],
    proposal: BoundaryProposalBundle,
    kind: ProposalCandidateKind,
) -> bool:
    if binding is None or binding.basis_version != 2:
        return True
    bound_ids = (
        binding.role_candidate_ids
        if isinstance(binding, ActorImplementationBinding)
        else binding.action_candidate_ids
    )
    snapshots = tuple(
        ImplementationCandidateSnapshot(
            candidate_id=item.candidate_id,
            candidate_fingerprint=item.candidate_fingerprint,
            evidence_fingerprint=item.evidence_fingerprint,
        )
        for item in proposal.source_snapshot.candidates
        if item.candidate_kind is kind and item.candidate_id in candidate_ids
    )
    return bound_ids != candidate_ids or binding.candidate_snapshots != snapshots


def _permission_label(
    item: ProposedPermissionItem,
    actors: dict[str, ProposedActorItem],
    actions: dict[str, ProposedActionItem],
) -> str:
    return (
        f"{actors[item.subject_actor_item_id].display_name} → "
        f"{actions[item.business_action_item_id].display_name}"
    )


def _is_carry_forward(
    item: ProposedPermissionItem,
    latest: dict[str, PermissionIntentRevision],
    actors: dict[str, ProposedActorItem],
    actions: dict[str, ProposedActionItem],
) -> bool:
    if item.intent_id is None or item.intent_id not in latest:
        return False
    current = latest[item.intent_id]
    subject = actors[item.subject_actor_item_id]
    owner = actors[item.resource_owner_actor_item_id]
    action = actions[item.business_action_item_id]
    effect_ids = {
        effect.item_id: effect.effect_id for effect in action.effect_catalog
    }
    protected = tuple(effect_ids[value] for value in item.protected_effect_item_ids)
    return (
        subject.actor_id == current.subject_actor_id
        and owner.actor_id == current.resource_owner_actor_id
        and action.action_id == current.business_action_id
        and item.effective_state is current.effective_state
        and item.relation is current.relation
        and item.expectation is current.expectation
        and all(value is not None for value in protected)
        and tuple(sorted(protected)) == current.protected_effect_ids
    )


__all__ = [
    "boundary_state_fingerprint",
    "build_maintenance_draft",
    "maintenance_to_proposal_command",
    "proposal_change_summary",
]
