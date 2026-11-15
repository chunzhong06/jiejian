"""新增约束改变着色时保留原主体；矛盾材料必须显式处理。"""
from types import SimpleNamespace

from product.backend.application.preparation.identity_reuse import retained_identity_assignments
from product.backend.application.preparation.service import PreparationService
from product.backend.application.test_identities.service import TestIdentityStatus as IdentityStatus
from product.backend.domain.boundaries.permissions import PermissionIntentRelation
from product.backend.domain.boundaries.semantics import PermissionExpectation
from product.backend.domain.preparation.requirements import compile_action_assurance
from tests.support.builders.checks.assurance import ACTOR, PROJECT, action, permission


def _facts():
    owner = SimpleNamespace(identity_id='tid_' + '1' * 32, actor_id=ACTOR, actor_revision=1, created_at_us=1, status=IdentityStatus.PREPARED)
    peer = SimpleNamespace(identity_id='tid_' + '2' * 32, actor_id=ACTOR, actor_revision=1, created_at_us=2, status=IdentityStatus.PREPARED)
    allowed = permission(20)
    denied = permission(1, relation=PermissionIntentRelation.SAME_ROLE_OTHER_ACCOUNT, expectation=PermissionExpectation.DENY)
    contract = compile_action_assurance(action(), (allowed, denied))
    binding = SimpleNamespace(subject_test_identity_id=owner.identity_id, resource_owner_test_identity_id=owner.identity_id)
    repository = SimpleNamespace(case_data=lambda _: (), execution=lambda *_: binding, resources=lambda *_: (binding,))
    return owner, peer, allowed, denied, contract, repository


def test_new_rule_recolors_slots_without_exchanging_existing_owner():
    owner, peer, allowed, denied, contract, repository = _facts()
    old = compile_action_assurance(action(), (allowed,))
    assert old.identity_requirements.permissions[0].resource_owner_slot_id != next(
        item.resource_owner_slot_id for item in contract.identity_requirements.permissions if item.permission.intent_id == allowed.intent_id)
    preferred, conflicts = retained_identity_assignments(repository, PROJECT, contract, (allowed, denied), (owner, peer))
    result = PreparationService._identities(contract, (owner, peer), {(ACTOR, 1): '借用人'}, preferred=preferred, conflicts=conflicts)
    ids = {item.requirement.slot_id: item.test_identity_id for item in result.slots}
    position = next(item for item in contract.identity_requirements.permissions if item.permission.intent_id == denied.intent_id)
    assert ids[position.resource_owner_slot_id] == owner.identity_id
    assert ids[position.subject_slot_id] == peer.identity_id
    retained = next(item for item in result.slots if item.test_identity_id == owner.identity_id)
    assert retained.selection_basis == 'CURRENT_MATERIAL'


def test_expired_retained_owner_is_not_exchanged_for_prepared_peer():
    owner, peer, allowed, denied, contract, repository = _facts()
    owner.status = IdentityStatus.NEEDS_REVIEW
    preferred, conflicts = retained_identity_assignments(repository, PROJECT, contract, (allowed, denied), (owner, peer))
    result = PreparationService._identities(contract, (owner, peer), {(ACTOR, 1): '借用人'}, preferred=preferred, conflicts=conflicts)
    slot = next(item for item in result.slots if item.test_identity_id == owner.identity_id)
    assert slot.status.value == 'STALE'
    assert slot.reason_codes == ('TEST_IDENTITY_REVIEW_REQUIRED',)


def test_conflicting_exact_case_owners_do_not_silently_choose_a_subject():
    owner, peer, allowed, denied, contract, repository = _facts()
    identities = contract.identity_requirements.permissions
    repository.case_data = lambda _: tuple(SimpleNamespace(permission=item.permission,
        owner_identity_id=owner.identity_id if item.permission.intent_id == allowed.intent_id else peer.identity_id) for item in identities)
    preferred, conflicts = retained_identity_assignments(repository, PROJECT, contract, (allowed, denied), (owner, peer))
    assert conflicts
    result = PreparationService._identities(contract, (owner, peer), {(ACTOR, 1): '借用人'}, preferred=preferred, conflicts=conflicts)
    assert result.status.value == 'BLOCKED'
    blocked = [item for item in result.slots if item.requirement.slot_id in conflicts]
    assert all(item.test_identity_id is None and item.reason_codes == ('IDENTITY_MATERIAL_ASSIGNMENT_CONFLICT',) for item in blocked)


def test_wrong_actor_revision_cannot_be_retained_by_old_material():
    owner, peer, allowed, denied, contract, repository = _facts()
    owner.actor_revision = 2
    preferred, conflicts = retained_identity_assignments(repository, PROJECT, contract, (allowed, denied), (owner, peer))
    assert owner.identity_id not in preferred.values()
