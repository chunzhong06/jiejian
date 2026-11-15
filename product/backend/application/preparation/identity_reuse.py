"""从已有准确材料保留主体对应；槽位重新着色不应交换原资源所有者。"""
from collections import defaultdict


def retained_identity_assignments(repository, project_id, contract, permissions, identities):
    slots = {item.slot_id: item for item in contract.identity_requirements.slots}
    positions = {item.permission.intent_id: item for item in contract.identity_requirements.permissions}
    known = {item.identity_id: item for item in identities}
    hints = defaultdict(list)

    def suggest(slot_id, identity_id, priority):
        slot, identity = slots.get(slot_id), known.get(identity_id)
        if slot is not None and identity is not None and (identity.actor_id, identity.actor_revision) == (slot.actor_id, slot.actor_revision):
            hints[slot_id].append((priority, identity_id))

    for data in repository.case_data(project_id):
        position = positions.get(data.permission.intent_id)
        if position is not None and position.permission.model_dump() == data.permission.model_dump():
            suggest(position.resource_owner_slot_id, data.owner_identity_id, 3)
    execution = repository.execution(contract.action_id, contract.action_revision)
    resources = repository.resources(contract.action_id, contract.action_revision)
    for permission in permissions:
        position = positions.get(permission.intent_id)
        if position is None or permission.expectation != 'ALLOW':
            continue
        for binding in resources:
            if position.subject_slot_id == position.resource_owner_slot_id and binding.subject_test_identity_id != binding.resource_owner_test_identity_id:
                continue
            owner = known.get(binding.resource_owner_test_identity_id)
            subject = known.get(binding.subject_test_identity_id)
            if owner is None or (owner.actor_id, owner.actor_revision) != (permission.resource_owner_actor_id, permission.resource_owner_actor_revision):
                continue
            if position.subject_slot_id is not None and (subject is None or (subject.actor_id, subject.actor_revision) != (permission.subject_actor_id, permission.subject_actor_revision)):
                continue
            priority = 2 if execution is not None and (binding.subject_test_identity_id, binding.resource_owner_test_identity_id) == (execution.subject_test_identity_id, execution.resource_owner_test_identity_id) else 1
            suggest(position.resource_owner_slot_id, binding.resource_owner_test_identity_id, priority)
            suggest(position.subject_slot_id, binding.subject_test_identity_id, priority)
    preferred, conflicts = {}, set()
    for slot_id, values in hints.items():
        priority = max(value[0] for value in values)
        candidates = {identity_id for rank, identity_id in values if rank == priority}
        if len(candidates) != 1:
            conflicts.add(slot_id)
        else:
            preferred[slot_id] = next(iter(candidates))
    by_identity = defaultdict(list)
    for slot_id, identity_id in preferred.items():
        by_identity[identity_id].append(slot_id)
    for group in by_identity.values():
        if len(group) > 1:
            conflicts.update(group)
    return preferred, frozenset(conflicts)
