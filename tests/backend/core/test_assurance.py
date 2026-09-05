# 验证权限到身份、资源与证明需求的确定性编译及非法历史关系关闭语义。

import ast
from pathlib import Path

import pytest

from product.backend.core.assurance import (
    AllocationMode, AssuranceStatus, IdentityRequirementPlanner,
    _color_components, compile_action_assurance,
)
from product.backend.core.permission_intent import PermissionIntentRelation as Relation
from product.backend.core.permission_semantics import BusinessEffectKind, PermissionExpectation
from product.backend.core.verification.permissions import (
    PermissionExpectation as LegacyExpectation, SecurityEffectKind,
)
from tests.fixtures.assurance import ACTOR, OTHER_ACTOR, EFFECT, SECOND_EFFECT, action, permission


def test_canonical_enums_keep_one_object_and_persistent_values():
    assert LegacyExpectation is PermissionExpectation
    assert SecurityEffectKind is BusinessEffectKind
    assert [item.value for item in PermissionExpectation] == ["ALLOW", "DENY"]
    assert {item.value for item in BusinessEffectKind} == {
        "STATE_MUTATION", "DATA_DISCLOSURE", "OBJECT_CREATION", "EXTERNAL_DISPATCH",
        "RESTRICTED_FUNCTION_INVOCATION", "CREDENTIAL_ACCESS",
    }


@pytest.mark.parametrize(("relation", "owner", "count"), [
    (Relation.OWNS, ACTOR, 1), (Relation.SAME_ROLE_OTHER_ACCOUNT, ACTOR, 2),
    (Relation.OTHER_ROLE, OTHER_ACTOR, 2),
])
def test_relation_produces_required_real_identity_count(relation, owner, count):
    result = compile_action_assurance(action(), (permission(relation=relation, owner=owner),))
    assert result.status is AssuranceStatus.READY
    assert len(result.identity_requirements.slots) == count
    positions = result.identity_requirements.permissions[0]
    assert (positions.subject_slot_id == positions.resource_owner_slot_id) == (relation is Relation.OWNS)
    assert len(result.resources) == 1
    assert result.resources[0].owner_slot_id == positions.resource_owner_slot_id


def test_many_permissions_reuse_three_accounts_and_are_order_independent():
    permissions = (
        permission(1, subject=OTHER_ACTOR, owner=OTHER_ACTOR),
        permission(2, subject=ACTOR, owner=OTHER_ACTOR, relation=Relation.OTHER_ROLE,
                   expectation=PermissionExpectation.DENY),
        permission(3, relation=Relation.SAME_ROLE_OTHER_ACCOUNT, expectation=PermissionExpectation.DENY),
        permission(4),
    )
    first = compile_action_assurance(action(), permissions)
    second = compile_action_assurance(action(), tuple(reversed(permissions)))
    assert first == second
    slots = first.identity_requirements.slots
    assert len(slots) == 3
    assert sum(item.actor_id == ACTOR for item in slots) == 2
    assert sum(item.actor_id == OTHER_ACTOR for item in slots) == 1
    assert any(len(item.required_by_intent_ids) > 1 for item in slots)
    for item in first.identity_requirements.permissions:
        source = next(source for source in permissions if source.intent_id == item.permission.intent_id)
        if source.relation is not Relation.OWNS:
            slot = next(slot for slot in slots if slot.slot_id == item.subject_slot_id)
            assert item.resource_owner_slot_id in slot.distinct_slot_ids


def test_more_than_twelve_components_use_conservative_distinct_allocation():
    permissions = tuple(permission(i, relation=Relation.SAME_ROLE_OTHER_ACCOUNT) for i in range(1, 8))
    plan = IdentityRequirementPlanner().plan(permissions)
    assert plan.allocation_mode is AllocationMode.CONSERVATIVE
    assert len(plan.slots) >= 2
    assert all(item.subject_slot_id != item.resource_owner_slot_id for item in plan.permissions)
    assert plan == IdentityRequirementPlanner().plan(tuple(reversed(permissions)))


def test_small_graph_exact_coloring_and_large_graph_never_merge_neighbors():
    # 五环需要三色；完全图的每个位置都必须不同。
    cycle = tuple(frozenset(((i - 1) % 5, (i + 1) % 5)) for i in range(5))
    assert len(set(_color_components(cycle))) == 3
    for size in (12, 13):
        graph = tuple(frozenset(set(range(size)) - {i}) for i in range(size))
        assert len(set(_color_components(graph))) == size


@pytest.mark.parametrize(("relation", "owner", "owner_revision"), [
    (Relation.OWNS, OTHER_ACTOR, 1), (Relation.SAME_ROLE_OTHER_ACCOUNT, OTHER_ACTOR, 1),
    (Relation.OTHER_ROLE, ACTOR, 1), (Relation.OWNS, ACTOR, 2), (Relation.OTHER_ROLE, ACTOR, 2),
])
def test_invalid_history_is_readable_but_fails_closed(relation, owner, owner_revision):
    historical = permission(relation=relation, owner=owner, resource_owner_actor_revision=owner_revision)
    before = historical.model_dump_json()
    contract = compile_action_assurance(action(), (historical,))
    assert contract.status is AssuranceStatus.BLOCKED
    assert "PERMISSION_RELATION_REVIEW_REQUIRED" in contract.reason_codes
    assert contract.identity_requirements.slots == ()
    assert historical.model_dump_json() == before


def test_deny_requires_allow_for_every_effect_and_never_invents_control():
    deny = permission(2, expectation=PermissionExpectation.DENY, effects=(EFFECT, SECOND_EFFECT))
    for inputs in ((deny,), (permission(1), deny)):
        contract = compile_action_assurance(action(), inputs)
        assert contract.status is AssuranceStatus.BLOCKED
        assert "ALLOW_CONTROL_REQUIRED" in contract.reason_codes
        assert any(item.allow_permission is None for item in contract.allow_controls)
    complete = compile_action_assurance(action(), (permission(1), deny, permission(3, effects=(SECOND_EFFECT,))))
    assert complete.status is AssuranceStatus.READY
    assert {item.effect_id for item in complete.effect_evidence} == {EFFECT, SECOND_EFFECT}


def test_contract_fingerprint_freezes_business_revisions_and_recovery():
    original = compile_action_assurance(action(), (permission(),))
    changed = compile_action_assurance(action(), (permission(revision=2),))
    assert changed.fingerprint != original.fingerprint
    assert not compile_action_assurance(action(state_changing=False), (permission(),)).recovery_required
    assert compile_action_assurance(action(revision=2), (permission(action_revision=2),)).fingerprint != original.fingerprint


def test_new_business_models_and_planner_do_not_import_old_verification_or_io():
    root = Path(__file__).resolve().parents[3]
    for name in ("business_boundary", "boundary_proposal", "permission_intent", "assurance", "permission_semantics"):
        nodes = ast.walk(ast.parse((root / f"product/backend/core/{name}.py").read_text(encoding="utf-8")))
        imports = [node.module or "" for node in nodes if isinstance(node, ast.ImportFrom)]
        assert not any("core.verification.permissions" in value for value in imports)
        assert not any(any(term in value for term in ("infra", "workflows", "llm", "httpx", "playwright")) for value in imports)
