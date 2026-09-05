# 验证准备服务每次重读事实、稳定分配账号，并对缺失材料和来源不匹配保持关闭。

from types import SimpleNamespace

from product.backend.core.permission_intent import PermissionIntentRelation
from product.backend.core.test_identity import TestIdentityAuthMethod as AuthMethod
from product.backend.workflows.business_boundaries.models import BusinessBoundaryView
from product.backend.workflows.preparation.models import PreparationStatus
from product.backend.workflows.preparation.service import PreparationService
from product.backend.workflows.test_identities.service import (
    TestIdentityStatus as IdentityStatus, TestIdentityView as IdentityView,
)
from tests.fixtures.assurance import ACTOR, OTHER_ACTOR, PROJECT, action, actor, permission


def _identity(number, *, status=IdentityStatus.PREPARED, created=10, actor_id=ACTOR, actor_revision=1):
    return IdentityView(
        identity_id=f"tid_{number:032x}", project_id=PROJECT, actor_id=actor_id,
        actor_revision=actor_revision, actor_display_name="普通成员", label="协作账号",
        auth_method=AuthMethod.BEARER if status is not IdentityStatus.NOT_PREPARED else None,
        status=status, cookie_count=0, created_at_us=created, updated_at_us=created,
    )


def _service(*, state_changing=True, identities=(), relation=PermissionIntentRelation.OWNS, bindings=None):
    state = SimpleNamespace(
        boundary=BusinessBoundaryView(
            project_id=PROJECT, policy_epoch=1, actors=(actor(), actor(OTHER_ACTOR)),
            actions=(action(state_changing=state_changing),), actor_bindings=(), action_bindings=(),
            permission_intents=(permission(relation=relation),), permission_statuses=(),
        ), identities=identities,
    )
    service = PreparationService(SimpleNamespace(view=lambda _: state.boundary),
                                 SimpleNamespace(list=lambda _: state.identities), bindings=bindings)
    return service, state


def test_missing_materials_never_become_complete_and_read_only_needs_no_recovery():
    for changes in (True, False):
        service, _ = _service(state_changing=changes)
        result = service.get(PROJECT)
        assert not result.preparation_complete
        item = result.actions[0]
        assert item.identity_requirements.status is PreparationStatus.NEEDS_USER
        assert item.execution.status is PreparationStatus.NEEDS_USER
        assert item.resources[0].status is PreparationStatus.NEEDS_USER
        assert item.effect_evidence[0].status is PreparationStatus.NEEDS_USER
        assert item.recovery.status is (PreparationStatus.NEEDS_USER if changes else PreparationStatus.NOT_REQUIRED)


def test_prepared_priority_stable_older_identity_and_live_reinspection():
    old = _identity(100, created=10)
    new = _identity(1, created=20)
    unprepared = _identity(2, status=IdentityStatus.NOT_PREPARED, created=1)
    stale = _identity(3, status=IdentityStatus.NEEDS_REVIEW, created=1)
    wrong_revision = _identity(4, actor_revision=2, created=1)
    service, state = _service(identities=(unprepared, old, stale, wrong_revision))
    first = service.get(PROJECT).actions[0]
    assert first.identity_requirements.slots[0].test_identity_id == old.identity_id
    state.identities += (new,)
    second = service.get(PROJECT).actions[0]
    assert second.identity_requirements == first.identity_requirements
    state.identities = (unprepared, stale, wrong_revision)
    third = service.get(PROJECT).actions[0]
    assert third.identity_requirements.slots[0].test_identity_id == unprepared.identity_id
    assert third.identity_requirements.status is PreparationStatus.NEEDS_USER
    assert third.assurance_contract_fingerprint == first.assurance_contract_fingerprint
    state.identities = (stale, wrong_revision)
    last = service.get(PROJECT).actions[0]
    assert last.identity_requirements.slots[0].test_identity_id is None
    assert last.identity_requirements.slots[0].status is PreparationStatus.STALE


def test_distinct_slots_cannot_reuse_one_test_identity_and_resources_follow_owner():
    identity = _identity(1)
    service, state = _service(identities=(identity,), relation=PermissionIntentRelation.SAME_ROLE_OTHER_ACCOUNT)
    first = service.get(PROJECT).actions[0]
    assert sum(item.test_identity_id is not None for item in first.identity_requirements.slots) == 1
    state.identities += (_identity(2),)
    second = service.get(PROJECT).actions[0]
    assert second.identity_requirements.status is PreparationStatus.SATISFIED
    assigned = {item.requirement.slot_id: item.test_identity_id for item in second.identity_requirements.slots}
    assert len(set(assigned.values())) == 2
    assert all(item.owner_test_identity_id == assigned[item.owner_slot_id] for item in second.resources)


def test_binding_port_cannot_hide_required_resources_or_effects():
    def inspect(action, contract, identities):
        missing = PreparationService._missing_technical(contract, identities)
        return missing.model_copy(update={
            "execution": missing.execution.model_copy(update={"status": PreparationStatus.SATISFIED, "reason_codes": ()}),
            "resources": (), "effect_evidence": (),
            "recovery": missing.recovery.model_copy(update={"status": PreparationStatus.SATISFIED, "reason_codes": ()}),
        })
    service, _ = _service(identities=(_identity(1),), bindings=SimpleNamespace(inspect=inspect))
    item = service.get(PROJECT).actions[0]
    assert not item.preparation_complete
    assert "PREPARATION_REQUIREMENT_MISMATCH" in item.reason_codes
