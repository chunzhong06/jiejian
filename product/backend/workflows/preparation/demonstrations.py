# 从已批准完整 ALLOW 和当前身份槽生成有限录制组合，不能拼接半截权限。
from product.backend.core.business_boundary import BoundaryModel
from product.backend.core.assurance import PermissionIdentity
from product.backend.core.permission_semantics import PermissionExpectation
from product.backend.workflows.preparation.models import PreparationStatus


class LegalActionDemonstration(BoundaryModel):
    permission: PermissionIdentity
    subject_slot_id: str
    resource_owner_slot_id: str
    subject_test_identity_id: str | None
    resource_owner_test_identity_id: str | None
    can_execute: bool


def legal_demonstrations(contract, permissions, identities):
    slots = {item.requirement.slot_id: item for item in identities.slots}
    by_id = {item.intent_id: item for item in permissions}
    result = []
    for resource in contract.resources:
        needed = {effect for intent_id in resource.required_by_intent_ids
                  for effect in by_id[intent_id].protected_effect_ids}
        for position in contract.identity_requirements.permissions:
            permission = by_id[position.permission.intent_id]
            if (permission.expectation is not PermissionExpectation.ALLOW
                    or position.resource_owner_slot_id != resource.owner_slot_id
                    or not set(permission.protected_effect_ids) >= needed):
                continue
            subject = slots[position.subject_slot_id]
            owner = slots[position.resource_owner_slot_id]
            result.append(LegalActionDemonstration(
                permission=position.permission, subject_slot_id=position.subject_slot_id,
                resource_owner_slot_id=position.resource_owner_slot_id,
                subject_test_identity_id=subject.test_identity_id,
                resource_owner_test_identity_id=owner.test_identity_id,
                can_execute=subject.status is PreparationStatus.SATISFIED and owner.status is PreparationStatus.SATISFIED,
            ))
    return tuple(result)
