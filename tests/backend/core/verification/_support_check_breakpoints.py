# 所属业务域的共享测试构造器；不导入测试用例。
from product.backend.core.lifecycle import CaseVerdict
from product.backend.core.verification.checks import CheckDecisionInput, CheckEffectFact
from product.backend.core.verification.trace import (
    ExecutionTrace, TraceEvent, TraceEventKind, TraceCorrelationKind,
    TraceAuthorityScope, TraceAuthorizationDecision,
)
from tests.fixtures.checks.check_execution import execution_pair

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
