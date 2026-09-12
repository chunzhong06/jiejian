# 验证纯计划保留完整回归、有限对照和证据缺口，并按冻结语义解释资源存在。
import pytest
from product.backend.core.check_plan import classify_http_resource_presence
from product.protocols.execution_v3 import CaseRole
from tests.fixtures.check_plan import prepared_action, plan


def test_plan_reuses_full_allow_case_and_preserves_distinct_subject_same_owner():
    result = plan()
    assert not result.gaps
    action = result.actions[0]
    assert len(action.cases) == 2 and len(action.twins) == 1
    cases = {case.case_id: case for case in action.cases}
    twin = action.twins[0]
    allow, deny = cases[twin.allow_case_id], cases[twin.deny_case_id]
    assert set(allow.roles) == {CaseRole.ALLOW_CONTROL, CaseRole.ALLOW_REGRESSION}
    assert allow.resource_owner_test_identity_id == deny.resource_owner_test_identity_id
    assert allow.subject_test_identity_id != deny.subject_test_identity_id


def test_superset_retains_full_regression_and_separate_subset_control():
    result = plan(prepared_action(superset=True))
    assert not result.gaps
    assert len(result.actions[0].cases) == 3
    regression = next(case for case in result.actions[0].cases if CaseRole.ALLOW_REGRESSION in case.roles)
    control = next(case for case in result.actions[0].cases if CaseRole.ALLOW_CONTROL in case.roles)
    assert len(regression.protected_effect_ids) == 2 and len(control.protected_effect_ids) == 1
    assert len(control.permission.protected_effect_ids) == 2


def test_plan_is_independent_of_permission_and_assignment_order():
    prepared = prepared_action(superset=True)
    reordered = prepared.model_copy(update={"permissions": tuple(reversed(prepared.permissions)),
        "identities": tuple(reversed(prepared.identities)), "evidence": tuple(reversed(prepared.evidence))})
    assert plan(prepared) == plan(reordered)


@pytest.mark.parametrize("field,reason", [("resources", "ACTION_RESOURCE_REQUIRED"),
    ("identities", "TEST_IDENTITY_REQUIRED"), ("observer_capabilities", "EFFECT_VERDICT_PROOF_REQUIRED")])
def test_missing_facts_keep_action_and_named_gap(field, reason):
    result = plan(prepared_action().model_copy(update={field: ()}))
    assert len(result.actions) == 1
    assert reason in {gap.reason for gap in result.gaps}


@pytest.mark.parametrize("status,expected", [(200, ("CONFIRMED", "CLOSED")), (299, ("CONFIRMED", "CLOSED")),
    (404, ("ABSENT", "CLOSED")), (410, ("ABSENT", "CLOSED")), (403, ("UNKNOWN", "OPEN")),
    (500, ("UNKNOWN", "OPEN")), (None, ("UNKNOWN", "OPEN"))])
def test_presence_status_is_narrow(status, expected):
    assert classify_http_resource_presence(status, same_resource=True, same_run=True) == expected
    assert classify_http_resource_presence(status, same_resource=False, same_run=True) == ("UNKNOWN", "OPEN")
    assert classify_http_resource_presence(status, same_resource=True, same_run=True, redirected=True) == ("UNKNOWN", "OPEN")


@pytest.mark.parametrize("kind,level", [("OBJECT_CREATION", "VERDICT_REQUIRED"),
    ("STATE_MUTATION", "SUPPORTING"), ("DATA_DISCLOSURE", "SUPPORTING")])
def test_recorded_get_only_proves_exact_resource_presence(kind, level):
    from product.backend.core.action_preparation import ActionEvidenceBinding, ActionEvidenceKind, RecordedRequestTemplate, seal_binding
    from product.backend.core.permission_semantics import BusinessEffectKind
    from product.backend.core.check_plan import derive_effect_proof
    prepared = prepared_action()
    old = prepared.evidence[0]
    facts = old.model_dump(exclude={"binding_fingerprint"}) | dict(kind=ActionEvidenceKind.RECORDED_OBSERVATION,
        observer_reference=None, source_recording_id="rec_"+"1"*32, source_draft_revision=1,
        source_draft_sha256="a"*64, step_id="step_000001",
        request_template=RecordedRequestTemplate(method="GET", relative_path="/items/{case_resource_id}", json_body={}))
    binding = seal_binding(ActionEvidenceBinding, **facts)
    effect = prepared.action.effect_catalog[0].model_copy(update={"effect_kind": BusinessEffectKind(kind)})
    proof = derive_effect_proof(effect, binding, "resource-1")
    assert proof.level == level
    assert proof.rule == ("HTTP_RESOURCE_PRESENCE" if kind == "OBJECT_CREATION" else "RECORDED_SUPPORT")
    partial = seal_binding(ActionEvidenceBinding, **(facts | {"request_template": RecordedRequestTemplate(
        method="GET", relative_path="/items/prefix-{case_resource_id}", json_body={})}))
    assert derive_effect_proof(effect, partial, "resource-1").level == "SUPPORTING"


@pytest.mark.parametrize("field", ["closure_supported", "resource_correlation_supported"])
def test_registered_proof_requires_both_precise_capabilities(field):
    prepared = prepared_action()
    capability = prepared.observer_capabilities[0].model_copy(update={field: False})
    result = plan(prepared.model_copy(update={"observer_capabilities": (capability,)}))
    assert "EFFECT_VERDICT_PROOF_REQUIRED" in {gap.reason for gap in result.gaps}


@pytest.mark.parametrize("state_changing", [False, True])
def test_multiple_owners_reuse_validated_parameterized_materials(state_changing):
    """录制来源归属不能把动作模板永久锁在一个 owner，实际资源仍逐 case 冻结。"""
    from product.backend.core.assurance import compile_action_assurance
    from product.backend.core.check_plan import PreparedIdentityAssignment
    from product.backend.core.action_preparation import ActionRecoveryBinding, RecordedRequestTemplate, seal_binding
    from tests.fixtures.assurance import ACTOR, OTHER_ACTOR, action, permission

    original = prepared_action()
    business = action(state_changing=state_changing)
    permissions = (permission(), permission(3, subject=OTHER_ACTOR, owner=OTHER_ACTOR))
    contract = compile_action_assurance(business, permissions)
    identities = tuple(PreparedIdentityAssignment(slot_id=slot.slot_id, identity_id=f"tid_{index:032x}",
        actor_id=slot.actor_id, actor_revision=slot.actor_revision, identity_fingerprint=f"{index:064x}")
        for index, slot in enumerate(contract.identity_requirements.slots, 1))
    original_owner = next(item for item in identities if item.actor_id == ACTOR)

    def rebind(binding, owner):
        return seal_binding(type(binding), **(binding.model_dump(exclude={"binding_fingerprint"}) | dict(
            action_semantic_fingerprint=business.semantic_fingerprint,
            subject_test_identity_id=owner.identity_id, subject_identity_fingerprint=owner.identity_fingerprint,
            resource_owner_test_identity_id=owner.identity_id, owner_identity_fingerprint=owner.identity_fingerprint)))

    execution = rebind(original.execution, original_owner)
    evidence = tuple(rebind(item, original_owner) for item in original.evidence)
    resources = tuple(seal_binding(type(original.resources[0]), **(rebind(original.resources[0], owner).model_dump(
        exclude={"binding_fingerprint"}) | {"actual_resource_id": f"resource-{index}"}))
        for index, owner in enumerate(identities, 1))
    recovery = None
    if state_changing:
        source = execution.model_dump(exclude={"binding_fingerprint", "flow_id", "flow_sha256", "resource_injection"})
        recovery = seal_binding(ActionRecoveryBinding, **source, step_id="step_000002",
            request_template=RecordedRequestTemplate(method="DELETE", relative_path="/items/{case_resource_id}", json_body={}))
    result = plan(original.model_copy(update=dict(action=business, permissions=permissions, assurance=contract,
        identities=identities, execution=execution, resources=resources, evidence=evidence, recovery=recovery)))
    assert not result.gaps
    cases = result.actions[0].cases
    assert len(cases) == 2 and {case.permission.intent_id for case in cases} == {item.intent_id for item in permissions}
    assert len({case.resource_id for case in cases}) == 2
    assert len({case.resource_owner_test_identity_id for case in cases}) == 2
    assert len({case.proof_requirements[0].binding_fingerprint for case in cases}) == 1
    assert all(case.proof_requirements[0].resource_id == case.resource_id for case in cases)
    assert all((case.recovery is not None) == state_changing for case in cases)
