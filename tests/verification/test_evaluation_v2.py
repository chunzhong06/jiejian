from __future__ import annotations

import importlib

import pytest
from pydantic import ValidationError

from jiejian.domain.lifecycle import CaseVerdict
from jiejian.verification.evaluation_v2 import (
    CaseDecisionInput,
    DecisionPhaseV2,
    EvaluationReasonCodeV2,
    ObserverKindV2,
    ObservationDecisionFact,
    RequestDecisionFact,
    evaluate_permission_case_v2,
)
from jiejian.verification.permission_coverage import PermissionMutationCaseV2, RetentionReason
from jiejian.verification.permissions import ActionDefinition, BatchAuthorizationMode, PermissionContext, PermissionExpectation


def _case(*, expectations=(PermissionExpectation.DENY,), side_effect=True, batch_mode=None, atomic=False, resources=("document",)):
    return PermissionMutationCaseV2(
        case_id="case-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        fingerprint="a" * 64,
        finding_pre_identity="b" * 64,
        source_rule_ids=("rule",),
        dimensions=(),
        retention_reason=RetentionReason.EXPLICIT_DENY_RISK,
        subject_id="member",
        action_id="modify",
        resource_ids=resources,
        expectations=expectations,
        relation_paths=tuple(("owns",) for _ in resources),
        context=PermissionContext(resource_ids=resources),
        required_observers=("http", "owner_api"),
        batch_mode=batch_mode,
        atomic=atomic,
    )


def _action(*, side_effect=True):
    return ActionDefinition(action_id="modify", flow_step_ids=("step",), side_effect=side_effect)


def _request(status=403, failure_code=None):
    return RequestDecisionFact(status_code=status, failure_code=failure_code)


def _fact(kind=ObserverKindV2.OWNER_API, *, resource="document", phase=DecisionPhaseV2.BEFORE, complete=True, digest="a" * 64, data=None):
    return ObservationDecisionFact(
        requirement_id="owner_api",
        observer_kind=kind,
        resource_id=resource,
        phase=phase,
        available=complete,
        complete=complete,
        correlated=complete,
        canonical_sha256=digest if complete else None,
        canonical_data=data if complete else None,
    )


def _owner_facts(resources=("document",), *, changed=False, complete=True):
    return tuple(
        _fact(resource=resource, phase=phase, complete=complete, digest=("b" if changed and phase is DecisionPhaseV2.AFTER else "a") * 64, data={"state": phase.value})
        for resource in resources
        for phase in (DecisionPhaseV2.BEFORE, DecisionPhaseV2.AFTER)
    )


def _input(case, action, request, facts):
    return CaseDecisionInput(case=case, action=action, expected_statuses=(200,), request=request, required_observations=facts)


def test_single_deny_and_allow_matrix() -> None:
    deny = _case()
    assert evaluate_permission_case_v2(_input(deny, _action(), _request(), _owner_facts())) == (CaseVerdict.SAFE, ())
    assert evaluate_permission_case_v2(_input(deny, _action(), _request(), _owner_facts(changed=True)))[0] is CaseVerdict.VULNERABLE
    assert evaluate_permission_case_v2(_input(deny, _action(), _request(200), _owner_facts()))[0] is CaseVerdict.VULNERABLE
    allow = _case(expectations=(PermissionExpectation.ALLOW,), side_effect=False)
    assert evaluate_permission_case_v2(_input(allow, _action(side_effect=False), _request(200), _owner_facts())) == (CaseVerdict.SAFE, ())
    assert evaluate_permission_case_v2(_input(allow, _action(side_effect=False), _request(), _owner_facts()))[0] is CaseVerdict.INCONCLUSIVE
    assert evaluate_permission_case_v2(_input(allow, _action(side_effect=False), _request(500), _owner_facts()))[0] is CaseVerdict.INCONCLUSIVE


def test_http_only_side_effect_free_allow_is_safe() -> None:
    case = _case(expectations=(PermissionExpectation.ALLOW,), side_effect=False).model_copy(update={"required_observers": ("http",)})
    assert evaluate_permission_case_v2(_input(case, _action(side_effect=False), _request(200), ())) == (CaseVerdict.SAFE, ())


def test_missing_non_http_requirement_remains_inconclusive() -> None:
    case = _case(expectations=(PermissionExpectation.ALLOW,), side_effect=False)
    assert evaluate_permission_case_v2(_input(case, _action(side_effect=False), _request(200), ()))[0] is CaseVerdict.INCONCLUSIVE


def test_http_only_side_effect_free_allow_is_safe() -> None:
    case = _case(expectations=(PermissionExpectation.ALLOW,), side_effect=False).model_copy(update={"required_observers": ("http",)})
    assert evaluate_permission_case_v2(_input(case, _action(side_effect=False), _request(200), ())) == (CaseVerdict.SAFE, ())


def test_missing_non_http_requirement_remains_inconclusive() -> None:
    case = _case(expectations=(PermissionExpectation.ALLOW,), side_effect=False)
    assert evaluate_permission_case_v2(_input(case, _action(side_effect=False), _request(200), ()))[0] is CaseVerdict.INCONCLUSIVE


def test_required_incomplete_and_request_failure_are_inconclusive() -> None:
    case = _case()
    result = evaluate_permission_case_v2(_input(case, _action(), _request(), _owner_facts(complete=False)))
    assert result == (CaseVerdict.INCONCLUSIVE, (EvaluationReasonCodeV2.REQUIRED_OBSERVER_INCOMPLETE.value,))
    result = evaluate_permission_case_v2(_input(case, _action(), _request(None, "REQUEST_TIMEOUT"), _owner_facts()))
    assert result == (CaseVerdict.INCONCLUSIVE, (EvaluationReasonCodeV2.REQUEST_FAILED.value,))


@pytest.mark.parametrize(
    ("kind", "facts", "expected"),
    [
        (ObserverKindV2.ASYNC_TASK_STATUS, (_fact(ObserverKindV2.ASYNC_TASK_STATUS, phase=DecisionPhaseV2.EVENTUAL, data={"task_state": "NOT_CREATED"}),), CaseVerdict.SAFE),
        (ObserverKindV2.ASYNC_TASK_STATUS, (_fact(ObserverKindV2.ASYNC_TASK_STATUS, phase=DecisionPhaseV2.EVENTUAL, data={"task_state": "SUCCESS", "final_result": {"effect": "APPLIED"}}),), CaseVerdict.VULNERABLE),
        (ObserverKindV2.STRUCTURED_AUDIT_LOG, (_fact(ObserverKindV2.STRUCTURED_AUDIT_LOG, phase=DecisionPhaseV2.AFTER, data={"records": [{"event_type": "REQUEST"}]}), _fact(ObserverKindV2.STRUCTURED_AUDIT_LOG, phase=DecisionPhaseV2.EVENTUAL, data={"records": [{"event_type": "TASK_STATE"}]})), CaseVerdict.SAFE),
        (ObserverKindV2.AZURE_QUEUE_PEEK, (_fact(ObserverKindV2.AZURE_QUEUE_PEEK, phase=DecisionPhaseV2.EVENTUAL, data={"matched_count": 0, "messages": [], "window_complete": True}),), CaseVerdict.SAFE),
        (ObserverKindV2.AZURE_QUEUE_PEEK, (_fact(ObserverKindV2.AZURE_QUEUE_PEEK, phase=DecisionPhaseV2.EVENTUAL, data={"matched_count": 1, "messages": [{"event_id": "e1"}], "window_complete": True}),), CaseVerdict.VULNERABLE),
    ],
)
def test_observer_kind_effect_reduction(kind, facts, expected) -> None:
    case = _case()
    converted = tuple(fact.model_copy(update={"requirement_id": "owner_api"}) for fact in facts)
    assert evaluate_permission_case_v2(_input(case, _action(), _request(), converted))[0] is expected


def test_blob_before_after_and_audit_side_effect() -> None:
    case = _case()
    blob = _owner_facts(changed=True)
    blob = tuple(item.model_copy(update={"observer_kind": ObserverKindV2.AZURE_BLOB_OBJECT}) for item in blob)
    assert evaluate_permission_case_v2(_input(case, _action(), _request(), blob))[0] is CaseVerdict.VULNERABLE
    audit = (
        _fact(ObserverKindV2.STRUCTURED_AUDIT_LOG, phase=DecisionPhaseV2.AFTER, data={"records": [{"event_type": "SIDE_EFFECT", "effect": "APPLIED"}]}),
        _fact(ObserverKindV2.STRUCTURED_AUDIT_LOG, phase=DecisionPhaseV2.EVENTUAL, data={"records": []}),
    )
    assert evaluate_permission_case_v2(_input(case, _action(), _request(), audit))[0] is CaseVerdict.VULNERABLE
    audit_only_after = (audit[0],)
    assert evaluate_permission_case_v2(_input(case, _action(), _request(), audit_only_after))[0] is CaseVerdict.VULNERABLE


def test_batch_modes_and_resource_unknown() -> None:
    resources = ("document", "child")
    all_deny = _case(expectations=(PermissionExpectation.DENY, PermissionExpectation.DENY), batch_mode=BatchAuthorizationMode.ALL_DENY, atomic=True, resources=resources)
    assert evaluate_permission_case_v2(_input(all_deny, _action(), _request(), _owner_facts(resources)))[0] is CaseVerdict.SAFE
    all_allow = _case(expectations=(PermissionExpectation.ALLOW, PermissionExpectation.ALLOW), batch_mode=BatchAuthorizationMode.ALL_ALLOW, atomic=True, resources=resources)
    assert evaluate_permission_case_v2(_input(all_allow, _action(), _request(200), _owner_facts(resources, changed=True)))[0] is CaseVerdict.SAFE
    mixed = _case(expectations=(PermissionExpectation.ALLOW, PermissionExpectation.DENY), batch_mode=BatchAuthorizationMode.MIXED_AUTHORIZATION, atomic=True, resources=resources)
    assert evaluate_permission_case_v2(_input(mixed, _action(), _request(200), _owner_facts(resources, changed=True)))[0] is CaseVerdict.VULNERABLE
    assert evaluate_permission_case_v2(_input(mixed, _action(), _request(), _owner_facts(resources, complete=False)))[0] is CaseVerdict.INCONCLUSIVE


def test_fact_keys_and_secret_fields_are_rejected() -> None:
    case = _case()
    with pytest.raises(ValidationError):
        _input(case, ActionDefinition(action_id="other", flow_step_ids=("step",)), _request(), _owner_facts())
    with pytest.raises(ValidationError):
        _fact(data={"password": "x"})
    with pytest.raises(ValidationError):
        CaseDecisionInput(case=case, action=_action(), expected_statuses=(200,), request=_request(), required_observations=(_fact(), _fact()))


def test_decision_is_deterministic_and_module_stays_pure() -> None:
    case = _case()
    input_data = _input(case, _action(), _request(), _owner_facts())
    assert evaluate_permission_case_v2(input_data) == evaluate_permission_case_v2(input_data)
    module = importlib.import_module("jiejian.verification.evaluation_v2")
    source = module.__file__
    assert source is not None
    text = open(source, encoding="utf-8").read()
    assert all(name not in text for name in ("jiejian.protocols", "jiejian.runner", "httpx", "sqlalchemy"))
