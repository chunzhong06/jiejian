"""按检查的准确规则依赖裁剪准备投影；保留原身份槽位和材料来源。"""
from product.backend.application.preparation.models import PreparationStatus
from product.backend.domain.checks.selection import resolve_selected_permissions, select_assurance
from product.backend.domain.preparation.requirements import AssuranceStatus
from product.backend.application.preparation.demonstrations import legal_demonstrations


def check_preparation(boundary, preparation, selected_permissions):
    if selected_permissions is None:
        return preparation
    selected = resolve_selected_permissions(boundary.permission_intents, selected_permissions)
    roots = {item.action_id: item for item in boundary.actions}
    actions = []
    for action in preparation.actions:
        projected = select_assurance(roots[action.action_id], action.permissions, action.assurance_contract, selected)
        if projected is None:
            continue
        permissions, contract = projected
        requirements = {item.slot_id: item for item in contract.identity_requirements.slots}
        slots = tuple(item.model_copy(update={'requirement': requirements[item.requirement.slot_id]})
                      for item in action.identity_requirements.slots if item.requirement.slot_id in requirements)
        identity = action.identity_requirements.model_copy(update={
            'slots': slots,
            'status': PreparationStatus.BLOCKED if contract.status is AssuranceStatus.BLOCKED else
                PreparationStatus.SATISFIED if all(item.status is PreparationStatus.SATISFIED for item in slots) else PreparationStatus.NEEDS_USER,
            'reason_codes': tuple(dict.fromkeys(code for item in slots for code in item.reason_codes)),
        })
        owners = {item.owner_slot_id for item in contract.resources}
        effects = {item.effect_id for item in contract.effect_evidence}
        resources = tuple(item for item in action.resources if item.owner_slot_id in owners)
        evidence = tuple(item for item in action.effect_evidence if item.effect_id in effects)
        members = (identity, action.execution, *resources, *evidence)
        complete_sources = ({item.owner_slot_id for item in resources} == owners and
                            {item.effect_id for item in evidence} == effects and
                            {item.requirement.slot_id for item in slots} == set(requirements))
        legal_owners = {item.resource_owner_slot_id for item in legal_demonstrations(contract, permissions, identity)}
        reasons = tuple(dict.fromkeys((*contract.reason_codes,
            *(code for item in (*members, action.recovery) for code in item.reason_codes),
            *(('PREPARATION_REQUIREMENT_MISMATCH',) if not complete_sources else ()),
            *(('ALLOW_RESOURCE_SETUP_REQUIRED',) if owners - legal_owners else ()))))
        complete = (contract.status is AssuranceStatus.READY and complete_sources and not owners - legal_owners
            and all(item.status is PreparationStatus.SATISFIED for item in members)
            and action.recovery.status is (PreparationStatus.SATISFIED if contract.recovery_required else PreparationStatus.NOT_REQUIRED))
        actions.append(action.model_copy(update={'permissions': permissions, 'assurance_contract': contract,
            'assurance_contract_fingerprint': contract.fingerprint, 'identity_requirements': identity,
            'resources': resources, 'effect_evidence': evidence, 'reason_codes': reasons,
            'preparation_complete': complete}))
    keys = {permission.intent_id for action in actions for permission in action.permissions}
    impacts = tuple(item.model_copy(update={'permission_ids': tuple(key for key in item.permission_ids if key in keys)})
        for item in preparation.impacts if set(item.permission_ids) & keys)
    return preparation.model_copy(update={'actions': tuple(actions), 'impacts': impacts,
        'preparation_complete': bool(actions) and all(item.preparation_complete for item in actions)})
