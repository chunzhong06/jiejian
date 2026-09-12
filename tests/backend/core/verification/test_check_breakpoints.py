# 当前冻结孪生直接复用六类因果定位，验证身份映射和已发布 Case 引用隔离。
import pytest

from product.backend.core.lifecycle import CaseVerdict
from product.backend.core.verification.breakpoints import BreakpointLocator, BreakpointType, BreakpointPrecision
from product.backend.core.verification.checks import CheckDecisionInput, CheckEffectFact
from product.backend.core.verification.trace import (
    ExecutionTrace, TraceEvent, TraceEventKind, TraceCorrelationKind,
    TraceAuthorityScope, TraceAuthorizationDecision,
)
from tests.fixtures.check_execution import execution_pair


def inputs(kind="AUTHORIZATION_MISSING", *, prefix="event", actual_subject=None):
    request, bundle = execution_pair(state_changing=True)
    action = request.actions[0]
    twin = action.twins[0]
    cases = {case.case_id: case for case in action.cases}
    identities = {item.identity_id: item for item in bundle.identities}
    deny = cases[twin.deny_case_id]
    allow = cases[twin.allow_case_id]
    refs = {deny.case_id: "ev_" + "d" * 64, allow.case_id: "ev_" + "a" * 64}

    def facts(case):
        return CheckDecisionInput(case=case, execution="DENIED" if case == deny else "ACCEPTED",
            actual_identity="MATCH", run_correlated=True, resource_correlated=True,
            baseline_trusted=True, recovery_verified=True, allow_control_verdict=CaseVerdict.SAFE,
            effects=tuple(CheckEffectFact(effect_id=proof.effect_id, proof_fingerprint=proof.proof_fingerprint,
                state="CONFIRMED", complete=True, reliable=True, correlated=True, authoritative=True,
                closure="CLOSED") for proof in case.proof_requirements))

    def trace(case, variant):
        planned = identities[case.subject_test_identity_id].verification.expected_application_subject_id
        subject = actual_subject or planned
        if variant == "IDENTITY_SUBSTITUTION":
            subject = identities[allow.subject_test_identity_id].verification.expected_application_subject_id
        events = []

        def event(name, event_kind, parent=None, **changes):
            value = TraceEvent(event_id=f"{prefix}-{name}", parent_event_ids=() if parent is None else (parent.event_id,),
                case_id=case.case_id, action_id=action.action_id, resource_ids=(case.resource_id,),
                kind=event_kind, semantic_key=name, subject_id=subject, actor_id=subject,
                source_component="business", source_location="business/handler",
                correlation_kind=TraceCorrelationKind.EXPLICIT_PARENT, evidence_refs=(refs[case.case_id],),
                recorded_at_us=100-len(events), **changes)
            events.append(value)
            return value

        entry = event("entry", TraceEventKind.ENTRY)
        identity = event("identity", TraceEventKind.IDENTITY, entry)
        parent = identity
        if variant not in ("AUTHORIZATION_MISSING", "AUTHORIZATION_LATE"):
            parent = event("authorization", TraceEventKind.AUTHORIZATION, identity,
                authorization_decision=TraceAuthorizationDecision.DENY if variant == "AUTHORIZATION_BYPASS" else TraceAuthorizationDecision.ALLOW)
            if variant == "AUTHORIZATION_BYPASS":
                # 授权拒绝在旁路分支；效果沿身份节点直接发生，才具备绕过的因果证据。
                parent = identity
        if variant == "AUTHORITY_EXPANSION":
            delegated = event("delegation", TraceEventKind.DELEGATION, parent,
                authority_scope=TraceAuthorityScope(allowed_action_ids=("other-action",), allowed_resource_ids=(case.resource_id,)))
            events[-1] = delegated.model_copy(update={"actor_id": "background-worker"})
            parent = events[-1]
        effect = event("effect", TraceEventKind.PERSISTENT_EFFECT, parent, effect_id=case.protected_effect_ids[0])
        if variant == "AUTHORIZATION_LATE":
            event("authorization", TraceEventKind.AUTHORIZATION, effect, authorization_decision=TraceAuthorizationDecision.DENY)
        if variant == "COMPENSATION_MASKING":
            event("recovery", TraceEventKind.RECOVERY, effect)
        return ExecutionTrace(case_id=case.case_id, action_id=action.action_id, planned_subject_id=planned,
            events=tuple(reversed(events)), complete=True)

    return dict(action=action, twin=twin, allow_facts=facts(allow), deny_facts=facts(deny),
        allow_trace=trace(allow, "normal"), deny_trace=trace(deny, kind), identities=bundle.identities,
        trace_namespace=identities[deny.subject_test_identity_id].verification.namespace,
        allow_evidence_refs=(refs[allow.case_id],), deny_evidence_refs=(refs[deny.case_id],))


@pytest.mark.parametrize("kind", list(BreakpointType))
def test_current_entry_locates_all_six_types_without_legacy_contract(kind):
    result = BreakpointLocator().locate_current(**inputs(kind.value))
    assert result.breakpoint_type is kind
    assert result.precision is BreakpointPrecision.EXACT


@pytest.mark.parametrize("prefix", ["random-z", "random-a"])
def test_current_location_does_not_depend_on_event_names_or_timestamp_order(prefix):
    result = BreakpointLocator().locate_current(**inputs(prefix=prefix))
    assert result.breakpoint_type is BreakpointType.AUTHORIZATION_MISSING
    assert result.first_violation_event_id == prefix + "-effect"


def test_service_worker_name_is_not_an_identity_mapping():
    result = BreakpointLocator().locate_current(**inputs("COMPENSATION_MASKING", actual_subject="service-worker"))
    assert result.breakpoint_type is BreakpointType.COMPENSATION_MASKING
    assert BreakpointType.IDENTITY_SUBSTITUTION not in result.amplifier_types


def test_missing_trace_keeps_violation_without_inventing_location():
    values = inputs()
    values["deny_trace"] = None
    result = BreakpointLocator().locate_current(**values)
    assert result.precision is BreakpointPrecision.VIOLATION_ONLY
    assert result.breakpoint_type is None


def test_no_attributed_orphan_does_not_diagnose():
    values = inputs()
    values["deny_facts"] = values["deny_facts"].model_copy(update={"actual_identity": "UNKNOWN"})
    assert BreakpointLocator().locate_current(**values) is None


def test_current_entry_rejects_cross_case_evidence():
    values = inputs()
    trace = values["deny_trace"]
    events = tuple(event.model_copy(update={"evidence_refs": values["allow_evidence_refs"]}) for event in trace.events)
    values["deny_trace"] = trace.model_copy(update={"events": events})
    with pytest.raises(ValueError, match="published case"):
        BreakpointLocator().locate_current(**values)


def test_current_legal_delegation_does_not_become_identity_substitution():
    values = inputs("IDENTITY_SUBSTITUTION")
    trace = values["deny_trace"]
    action_id, resource = values["action"].action_id, values["deny_facts"].case.resource_id
    events = []
    authorization = next(event for event in trace.events if event.kind is TraceEventKind.AUTHORIZATION)
    for event in trace.events:
        if event.kind is not TraceEventKind.PERSISTENT_EFFECT:
            changes = dict(subject_id=trace.planned_subject_id, actor_id=trace.planned_subject_id)
            if event.kind is TraceEventKind.AUTHORIZATION:
                changes["authority_scope"] = TraceAuthorityScope(allowed_action_ids=(action_id,), allowed_resource_ids=(resource,))
            events.append(event.model_copy(update=changes))
        else:
            events.append(event.model_copy(update={"authority_scope": TraceAuthorityScope(
                allowed_action_ids=(action_id,), allowed_resource_ids=(resource,),
                delegated_from_event_id=authorization.event_id)}))
    values["deny_trace"] = trace.model_copy(update={"events": tuple(events)})
    result = BreakpointLocator().locate_current(**values)
    assert result.breakpoint_type is not BreakpointType.IDENTITY_SUBSTITUTION
    assert BreakpointType.IDENTITY_SUBSTITUTION not in result.amplifier_types


def test_unmapped_namespace_does_not_infer_identity_substitution():
    values = inputs("IDENTITY_SUBSTITUTION")
    values["trace_namespace"] = "unregistered-namespace"
    for name in ("allow", "deny"):
        values[name + "_trace"] = values[name + "_trace"].model_copy(update={
            "planned_subject_id": values[name + "_facts"].case.subject_test_identity_id})
    result = BreakpointLocator().locate_current(**values)
    assert result.breakpoint_type is not BreakpointType.IDENTITY_SUBSTITUTION
    assert BreakpointType.IDENTITY_SUBSTITUTION not in result.amplifier_types
