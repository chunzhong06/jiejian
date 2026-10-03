# 从不可变提案引用的历史修订形成业务对照；缺失历史只标记未知，不用当前值补齐。
from __future__ import annotations

from product.backend.core.boundaries.proposals import BoundaryProposalBundle, ProposalWriteMode
from product.backend.infra.storage import StorageUnitOfWork
from product.backend.workflows.business_boundaries.models import (
    BoundaryProposalReview, BoundaryReviewEffect, BoundaryReviewItem, BoundaryReviewValue,
)


def _business_value(item, *, action: bool = False) -> BoundaryReviewValue:
    fields = dict(display_name=item.display_name, description=item.description,
                  effective_state=item.effective_state.value)
    if action:
        fields.update(resource_concept=item.primary_resource_concept,
                      operation_kind=item.operation_kind.value, state_changing=item.state_changing,
                      effects=tuple(BoundaryReviewEffect(
                          business_label=e.business_label, effect_kind=e.effect_kind.value,
                          resource_concept=e.resource_concept, description=e.description,
                          expected_state=e.expected_state, protected_projection=e.protected_projection,
                      ) for e in item.effect_catalog))
    return BoundaryReviewValue(**fields)


def _permission_value(item, subject, owner, action, effects) -> BoundaryReviewValue:
    return BoundaryReviewValue(
        display_name=f"{subject.display_name} · {action.display_name}",
        effective_state=item.effective_state.value, subject=subject.display_name,
        resource_owner=owner.display_name, action=action.display_name,
        relation=item.relation.value, expectation=item.expectation.value,
        protected_effects=tuple(e.business_label for e in effects),
    )


def proposal_review(work: StorageUnitOfWork, proposal: BoundaryProposalBundle) -> BoundaryProposalReview:
    """使用调用者的同一读取事务；不写修订，不从当前边界反推原始基线。"""
    items: list[BoundaryReviewItem] = []
    changed = False
    actors = {item.item_id: item for item in proposal.proposed_actors}
    actions = {item.item_id: item for item in proposal.proposed_actions}

    def owned(value):
        return value if value is not None and value.project_id == proposal.project_id else None

    for kind, proposed in (("ACTOR", proposal.proposed_actors), ("ACTION", proposal.proposed_actions),
                           ("PERMISSION", proposal.proposed_permissions)):
        for item in proposed:
            reference = getattr(item, {"ACTOR": "actor_id", "ACTION": "action_id", "PERMISSION": "intent_id"}[kind])
            before = None
            available = item.write_mode is ProposalWriteMode.CREATE
            current = None
            historical = None
            if reference is not None:
                if kind == "ACTOR":
                    historical = owned(work.business_boundaries.actor_revision(reference, item.expected_current_revision))
                    root = owned(work.business_boundaries.actor(reference))
                    current = None if root is None else root.current_revision
                elif kind == "ACTION":
                    historical = owned(work.business_boundaries.action_revision(reference, item.expected_current_revision))
                    root = owned(work.business_boundaries.action(reference))
                    current = None if root is None else root.current_revision
                else:
                    historical = owned(work.permission_intents.get_revision(reference, item.expected_current_revision))
                    latest = owned(work.permission_intents.latest(reference))
                    current = None if latest is None else latest.revision
                changed |= current != item.expected_current_revision
                available = historical is not None

            if kind != "PERMISSION":
                after = _business_value(item, action=kind == "ACTION")
                if historical is not None:
                    before = _business_value(historical, action=kind == "ACTION")
            else:
                action = actions[item.business_action_item_id]
                after = _permission_value(item, actors[item.subject_actor_item_id],
                    actors[item.resource_owner_actor_item_id], action,
                    tuple(e for e in action.effect_catalog if e.item_id in item.protected_effect_item_ids))
                if historical is not None:
                    subject = owned(work.business_boundaries.actor_revision(historical.subject_actor_id, historical.subject_actor_revision))
                    owner = owned(work.business_boundaries.actor_revision(historical.resource_owner_actor_id, historical.resource_owner_actor_revision))
                    old_action = owned(work.business_boundaries.action_revision(historical.business_action_id, historical.action_revision))
                    effects = () if old_action is None else tuple(e for e in old_action.effect_catalog if e.effect_id in historical.protected_effect_ids)
                    # 权限的旧名字与效果也必须来自它引用的修订，不能借用新提案的名称。
                    available = all(value is not None for value in (subject, owner, old_action)) and len(effects) == len(historical.protected_effect_ids)
                    if available:
                        before = _permission_value(historical, subject, owner, old_action, effects)
            mode = "CREATE" if item.write_mode is ProposalWriteMode.CREATE else "REFERENCE" if item.write_mode is ProposalWriteMode.REFERENCE else "RETIRE" if item.effective_state.value == "RETIRED" else "UPDATE"
            items.append(BoundaryReviewItem(entity_kind=kind, item_id=item.item_id, entity_id=reference,
                basis_revision=item.expected_current_revision, change_kind=mode, basis_available=available,
                before=before, after=after))
    return BoundaryProposalReview(basis_state="COMPLETE" if all(i.basis_available for i in items) else "UNAVAILABLE",
                                  current_state_changed=changed, items=tuple(items))
