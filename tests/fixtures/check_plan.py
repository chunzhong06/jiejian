# 构造纯计划的正式权限、双身份和精确受控证明能力，不访问外部服务。
from product.backend.core.check_plan import PreparedActionInput, PreparedIdentityAssignment, RegisteredEffectProofCapability, compile_project_check_plan
from product.backend.core.action_preparation import ActionExecutionBinding, ActionResourceBinding, ActionEvidenceBinding, ActionEvidenceKind, ActionRecoveryBinding, RecordedRequestTemplate, RegisteredObserverReference, ResourceInjection, ResourceInjectionKind, seal_binding
from product.backend.core.assurance import compile_action_assurance
from product.backend.core.permission_intent import PermissionIntentRelation
from product.backend.core.permission_semantics import PermissionExpectation
from tests.fixtures.assurance import action, permission, EFFECT, SECOND_EFFECT, PROJECT


def prepared_action(*, superset=False, state_changing=False, action_number=1):
    business_action = action(state_changing=state_changing)
    if action_number != 1:
        from product.backend.core.business_boundary import boundary_sha256
        values = business_action.model_dump()
        values["action_id"] = f"bac_{action_number:032x}"
        provisional = business_action.model_copy(update={"action_id": values["action_id"]})
        values["semantic_fingerprint"] = boundary_sha256(provisional.semantic_payload())
        business_action = type(business_action).model_validate(values)
    permissions = (permission(1 + (action_number - 1) * 2, effects=(EFFECT, SECOND_EFFECT) if superset else (EFFECT,),
        business_action_id=business_action.action_id),
        permission(2 + (action_number - 1) * 2, relation=PermissionIntentRelation.SAME_ROLE_OTHER_ACCOUNT,
            expectation=PermissionExpectation.DENY, business_action_id=business_action.action_id))
    contract = compile_action_assurance(business_action, permissions)
    identities = tuple(PreparedIdentityAssignment(slot_id=slot.slot_id, identity_id=f"tid_{index:032x}",
        actor_id=slot.actor_id, actor_revision=slot.actor_revision, identity_fingerprint=f"{index:064x}")
        for index, slot in enumerate(contract.identity_requirements.slots, 1))
    position = next(item for item in contract.identity_requirements.permissions if item.permission.intent_id == permissions[0].intent_id)
    owner = next(item for item in identities if item.slot_id == position.resource_owner_slot_id)
    common = dict(project_id=PROJECT, business_action_id=business_action.action_id, action_revision=1,
        action_semantic_fingerprint=business_action.semantic_fingerprint, implementation_fingerprint="a"*64,
        source_fingerprint="b"*64, endpoint_fingerprint="c"*64, subject_test_identity_id=owner.identity_id,
        subject_identity_fingerprint=owner.identity_fingerprint, resource_owner_test_identity_id=owner.identity_id,
        owner_identity_fingerprint=owner.identity_fingerprint, confirmed_at_us=1)
    recorded = dict(source_recording_id="rec_"+"1"*32, source_draft_revision=1, source_draft_sha256="d"*64)
    execution_facts = dict(flow_id="flow-test", flow_sha256="e"*64,
        resource_injection=ResourceInjection(consumer=ResourceInjectionKind.PATH, location="path[1]", template_fingerprint="f"*64))
    execution = seal_binding(ActionExecutionBinding, **common, **recorded, **execution_facts)
    resource = seal_binding(ActionResourceBinding, **common, **recorded, **execution_facts, actual_resource_id="resource-1")
    evidence, capabilities = [], []
    for effect in permissions[0].protected_effect_ids:
        reference = RegisteredObserverReference(descriptor_id="exp_"+"1"*32, descriptor_fingerprint="a"*64, observer_id="registered-proof")
        evidence.append(seal_binding(ActionEvidenceBinding, **common, kind=ActionEvidenceKind.REGISTERED_OBSERVER,
            effect_id=effect, observer_reference=reference))
        capabilities.append(RegisteredEffectProofCapability(**reference.model_dump(), effect_id=effect,
            closure_supported=True, resource_correlation_supported=True))
    recovery = seal_binding(ActionRecoveryBinding, **common, **recorded, step_id="restore",
        request_template=RecordedRequestTemplate(method="POST", relative_path="/restore/{case_resource_id}")) if state_changing else None
    return PreparedActionInput(action=business_action, permissions=permissions, assurance=contract, identities=identities,
        execution=execution, resources=(resource,), evidence=tuple(evidence), recovery=recovery, observer_capabilities=tuple(capabilities))


def plan(prepared=None):
    return compile_project_check_plan(PROJECT, source_fingerprint="b"*64, policy_epoch=1,
        engine_version="test-1", config_fingerprint="c"*64, actions=(prepared or prepared_action(),))
