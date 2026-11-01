import pytest

from product.backend.domain.boundaries.permissions import PermissionIntentRelation
from product.backend.domain.boundaries.semantics import PermissionExpectation
from product.backend.domain.checks.plan import PreparedIdentityAssignment
from product.backend.domain.lifecycle import CaseVerdict
from product.backend.domain.preparation.bindings import ActionEvidenceBinding, RuleCaseDataBinding, seal_binding
from product.backend.domain.preparation.requirements import compile_action_assurance
from product.backend.domain.verification.checks import CheckDecisionInput, CheckEffectFact, evaluate_check_case
from product.protocols.checks.conditions import PermissionConditions, ObservedPermissionConditions, match_permission_conditions, permission_conditions_overlap
from product.protocols.checks.execution_request import ExecutionAction, PermissionReference
from tests.support.builders.checks.assurance import permission
from tests.support.builders.checks.check_plan import prepared_action, plan


def conditioned_preparation(*, anonymous=False, state=False):
    prepared = prepared_action()
    allows = PermissionConditions(tenant='SAME', resource_states=('OPEN',))
    denies = PermissionConditions(principal='ANONYMOUS') if anonymous else PermissionConditions(
        tenant='SAME', resource_states=('ARCHIVED',) if state else ('OPEN',))
    permissions = (permission(1, conditions=allows), permission(2,
        subject='bar_'+'2'*32 if anonymous else 'bar_'+'1'*32,
        relation=PermissionIntentRelation.OTHER_ROLE if anonymous else PermissionIntentRelation.SAME_ROLE_OTHER_ACCOUNT,
        expectation=PermissionExpectation.DENY, conditions=denies))
    contract = compile_action_assurance(prepared.action, permissions)
    identities = tuple(PreparedIdentityAssignment(slot_id=slot.slot_id, identity_id=f'tid_{index:032x}',
        actor_id=slot.actor_id, actor_revision=slot.actor_revision, identity_fingerprint=f'{index:064x}')
        for index, slot in enumerate(contract.identity_requirements.slots, 1))
    reference = prepared.evidence[0].observer_reference.model_copy(update={'descriptor_id':'psr_'+'1'*32})
    evidence = seal_binding(ActionEvidenceBinding, **(prepared.evidence[0].model_dump(exclude={'binding_fingerprint'})
        | {'observer_reference':reference}))
    capability = prepared.observer_capabilities[0].model_copy(update={'descriptor_id':reference.descriptor_id})
    return prepared.model_copy(update={'permissions':permissions,'assurance':contract,'identities':identities,
        'evidence':(evidence,), 'observer_capabilities':(capability,)})


@pytest.mark.parametrize('tenant,state,expected', [
    (None,'OPEN','UNKNOWN'), ('A',None,'UNKNOWN'), ('B','OPEN','MISMATCH'),
    ('A','ARCHIVED','MISMATCH'), ('A','OPEN','MATCH')])
def test_conditions_use_actual_values_and_keep_missing_values_unknown(tenant, state, expected):
    observed = ObservedPermissionConditions(proof_fingerprint='a'*64, source_id='psr_'+'1'*32,
        source_fingerprint='b'*64, principal='AUTHENTICATED', subject_tenant=tenant,
        owner_tenant='A', resource_tenant='A', resource_state=state)
    assert match_permission_conditions(PermissionConditions(tenant='SAME',resource_states=('OPEN',)),observed) == expected


@pytest.mark.parametrize('left,right,expected', [
    (None, PermissionConditions(resource_states=('OPEN',)), True),
    (None, PermissionConditions(principal='ANONYMOUS'), False),
    (PermissionConditions(resource_states=('OPEN',)), PermissionConditions(resource_states=('ARCHIVED',)), False),
    (PermissionConditions(tenant='SAME'), PermissionConditions(tenant='DIFFERENT'), False),
    (PermissionConditions(resource_states=('OPEN','ARCHIVED')), PermissionConditions(resource_states=('ARCHIVED',)), True)])
def test_only_disjoint_conditions_separate_opposite_expectations(left,right,expected):
    assert permission_conditions_overlap(left,right) is expected


def test_anonymous_principal_does_not_allocate_a_fake_account():
    prepared = conditioned_preparation(anonymous=True)
    result = plan(prepared)
    assert not result.gaps
    case = next(item for item in result.actions[0].cases if item.permission.expectation == 'DENY')
    assert case.subject_test_identity_id is None and case.subject_identity_fingerprint is None
    assert all(slot.actor_id != case.subject_actor_id for slot in prepared.assurance.identity_requirements.slots)
    ExecutionAction.model_validate_json(result.actions[0].model_dump_json(exclude={'gaps'}))
    from product.backend.domain.verification.trace import ExecutionTrace
    trace=ExecutionTrace(case_id=case.case_id,action_id=result.actions[0].action_id,
        planned_subject_id=None,events=(),complete=False,reason_codes=('TRACE_EVENTS_UNAVAILABLE',))
    assert ExecutionTrace.model_validate_json(trace.model_dump_json()).planned_subject_id is None


def test_same_and_cross_tenant_scenarios_keep_distinct_subjects_for_the_same_owner():
    prepared = prepared_action()
    permissions = (permission(1, conditions=PermissionConditions(tenant='SAME')),
        permission(2, relation=PermissionIntentRelation.SAME_ROLE_OTHER_ACCOUNT,
            expectation=PermissionExpectation.DENY, conditions=PermissionConditions(tenant='SAME')),
        permission(3, relation=PermissionIntentRelation.SAME_ROLE_OTHER_ACCOUNT,
            expectation=PermissionExpectation.DENY, conditions=PermissionConditions(tenant='DIFFERENT')))
    contract = compile_action_assurance(prepared.action, permissions)
    positions = {item.permission.intent_id:item for item in contract.identity_requirements.permissions}
    same, different = (positions[rule.intent_id] for rule in permissions[1:])
    assert same.resource_owner_slot_id == different.resource_owner_slot_id
    assert same.subject_slot_id != different.subject_slot_id
    assert different.subject_slot_id != different.resource_owner_slot_id


def test_state_control_uses_explicit_rule_data_without_changing_the_normal_control():
    prepared = conditioned_preparation(state=True)
    denied = prepared.permissions[1]
    original = prepared.resources[0]
    selected = RuleCaseDataBinding(project_id=denied.project_id,
        permission=PermissionReference.model_validate(denied.model_dump(include=set(PermissionReference.model_fields))),
        resource_id='archived-ticket', owner_identity_id=original.resource_owner_test_identity_id,
        base_binding_fingerprint=original.binding_fingerprint, confirmed_at_us=20)
    result = plan(prepared.model_copy(update={'case_data':(selected,)}))
    assert not result.gaps
    action = result.actions[0]
    assert next(case for case in action.cases if case.permission.expectation == 'DENY').resource_id == 'archived-ticket'
    assert next(case for case in action.cases if case.permission.expectation == 'ALLOW').resource_id == original.actual_resource_id
    assert action.twins[0].condition_difference == 'RESOURCE_STATE'
    ExecutionAction.model_validate_json(action.model_dump_json(exclude={'gaps'}))
    stale = selected.model_copy(update={'base_binding_fingerprint':'f'*64})
    assert 'RULE_CASE_DATA_STALE' in {gap.reason for gap in plan(prepared.model_copy(update={'case_data':(stale,)})).gaps}


@pytest.mark.parametrize('actual_state,expected', [(None,CaseVerdict.INCONCLUSIVE),('ARCHIVED',CaseVerdict.INCONCLUSIVE),('OPEN',CaseVerdict.VULNERABLE)])
def test_a_confirmed_effect_is_only_attributed_to_a_rule_whose_conditions_match(actual_state, expected):
    case = next(item for item in plan(conditioned_preparation()).actions[0].cases if item.permission.expectation=='DENY')
    proof = case.proof_requirements[0]
    observed = ObservedPermissionConditions(proof_fingerprint=proof.proof_fingerprint,
        source_id=proof.reference.descriptor_id, source_fingerprint=proof.reference.descriptor_fingerprint,
        principal='AUTHENTICATED',subject_tenant='A',owner_tenant='A',resource_tenant='A',resource_state=actual_state)
    facts = CheckDecisionInput(case=case, execution='DENIED', actual_identity='MATCH',run_correlated=True,
        resource_correlated=True,baseline_trusted=True,recovery_verified=True,allow_control_verdict=CaseVerdict.SAFE,
        effects=(CheckEffectFact(effect_id=proof.effect_id,proof_fingerprint=proof.proof_fingerprint,state='CONFIRMED',
            complete=True,reliable=True,correlated=True,authoritative=True,closure='CLOSED'),),condition_observations=(observed,))
    assert evaluate_check_case(facts).verdict is expected
