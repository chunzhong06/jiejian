# 成功派发与真实后果分开；旧字节兼容、分叉因果和缺口不能制造后果或精确定位。
import json

import pytest

from product.backend.core.verification.breakpoints import BreakpointLocator, BreakpointType, BreakpointPrecision
from product.backend.core.verification.trace import ExecutionTrace, TraceEvent, TraceEventKind, TraceAuthorizationDecision
from product.protocols.check_result import CheckEvidence, CheckCaseOutcome, canonical_check_document, parse_check_document, seal_check_evidence
from tests.fixtures.check_execution import execution_pair
from tests.backend.core.verification._support_check_breakpoints import inputs


def dispatch_inputs():
    values = inputs("normal")
    trace = values["deny_trace"]
    identity = next(item for item in trace.events if item.kind is TraceEventKind.IDENTITY)
    authorization = next(item for item in trace.events if item.kind is TraceEventKind.AUTHORIZATION)
    effect = next(item for item in trace.events if item.kind is TraceEventKind.PERSISTENT_EFFECT)
    dispatch = effect.model_copy(update=dict(event_id="dispatch",parent_event_ids=(identity.event_id,),kind=TraceEventKind.MESSAGE,
        semantic_key="work_accepted",effect_id=None,dispatch_effect_ids=(effect.effect_id,),recorded_at_us=10))
    worker = effect.model_copy(update=dict(event_id="worker",parent_event_ids=(dispatch.event_id,),kind=TraceEventKind.DELEGATION,
        semantic_key="work_started",effect_id=None,recorded_at_us=30))
    events = []
    for item in trace.events:
        if item.event_id==authorization.event_id:
            item=item.model_copy(update=dict(parent_event_ids=(dispatch.event_id,),authorization_decision=TraceAuthorizationDecision.DENY,recorded_at_us=20))
        elif item.event_id==effect.event_id:
            item=item.model_copy(update=dict(parent_event_ids=(worker.event_id,),recorded_at_us=40))
        events.append(item)
    values["deny_trace"] = ExecutionTrace.model_validate_json(trace.model_copy(update={"events":tuple(events)+(dispatch,worker)}).model_dump_json())
    return values,dispatch,effect,authorization


def test_dispatch_before_authorization_with_parallel_worker_keeps_real_orphan():
    values,dispatch,effect,_ = dispatch_inputs()
    result = BreakpointLocator().locate_current(**values)
    assert result.breakpoint_type is BreakpointType.AUTHORIZATION_LATE
    assert result.first_violation_event_id==dispatch.event_id
    assert result.precision is BreakpointPrecision.EXACT
    assert result.orphan_effect_ids==(effect.effect_id,)
    assert dispatch.effect_id is None


@pytest.mark.parametrize("fault",["partial","metadata","effect","authorization","before","disconnected","no_confirmed"])
def test_dispatch_gaps_never_create_new_late(fault):
    values,dispatch,effect,authorization = dispatch_inputs()
    trace=values["deny_trace"]
    events=list(trace.events)
    if fault=="partial":
        trace=trace.model_copy(update={"complete":False,"reason_codes":("TRACE_SOURCE_INCOMPLETE",)})
    elif fault=="no_confirmed":
        facts=values["deny_facts"]
        values["deny_facts"]=facts.model_copy(update={"effects":tuple(item.model_copy(update={"state":"UNKNOWN"}) for item in facts.effects)})
    else:
        replacement={}
        if fault=="metadata":
            replacement[dispatch.event_id]=dispatch.model_copy(update={"dispatch_effect_ids":()})
        elif fault=="effect":
            events=[item for item in events if item.event_id!=effect.event_id]
        elif fault=="authorization":
            events=[item for item in events if item.event_id!=authorization.event_id]
        elif fault=="before":
            replacement[authorization.event_id]=authorization.model_copy(update={"parent_event_ids":dispatch.parent_event_ids})
            replacement[dispatch.event_id]=dispatch.model_copy(update={"parent_event_ids":(authorization.event_id,)})
        else:
            replacement[effect.event_id]=effect.model_copy(update={"parent_event_ids":dispatch.parent_event_ids})
        events=[replacement.get(item.event_id,item) for item in events]
    values["deny_trace"]=trace.model_copy(update={"events":tuple(events)})
    result=BreakpointLocator().locate_current(**values)
    assert result is None or result.breakpoint_type is not BreakpointType.AUTHORIZATION_LATE


def test_parallel_dispatches_do_not_claim_unique_exact_location():
    values,dispatch,effect,authorization=dispatch_inputs()
    other=dispatch.model_copy(update={"event_id":"other-dispatch"})
    second_auth=authorization.model_copy(update={"event_id":"other-auth","parent_event_ids":(other.event_id,)})
    trace=values["deny_trace"]
    events=tuple(item.model_copy(update={"parent_event_ids":(dispatch.event_id,other.event_id)})
        if item.event_id==effect.event_id else item for item in trace.events)+(other,second_auth)
    values["deny_trace"]=trace.model_copy(update={"events":events})
    result=BreakpointLocator().locate_current(**values)
    assert result.precision is not BreakpointPrecision.EXACT


@pytest.mark.parametrize("bad",[None,"effect",[True],[[]],["same","same"],["x"*161],["token=hidden"],["a"+str(i) for i in range(17)]])
def test_trace_dispatch_arrays_are_strict(bad):
    _,dispatch,_,_=dispatch_inputs()
    value=dispatch.model_dump(mode="json")|{"dispatch_effect_ids":bad}
    with pytest.raises(ValueError):
        TraceEvent.model_validate(value,strict=False)


@pytest.mark.parametrize("change",[{"kind":"ENTRY"},{"effect_id":"real-effect"}])
def test_dispatch_cannot_be_a_realized_effect(change):
    _,dispatch,_,_=dispatch_inputs()
    with pytest.raises(ValueError):
        TraceEvent.model_validate(dispatch.model_dump(mode="json")|change,strict=False)


def test_empty_dispatch_preserves_explicit_trace_bytes_and_nested_evidence():
    # 旧可选字段的字节合同由明确输入固定，不依赖已删除的临时验收目录。
    request, _ = execution_pair(state_changing=True)
    action = request.actions[0]
    case = action.cases[0]
    payload = {
        "schema_version": "1", "case_id": case.case_id, "action_id": action.action_id,
        "planned_subject_id": "test-account", "complete": True, "reason_codes": [],
        "events": [{"event_id": "entry", "parent_event_ids": [], "case_id": case.case_id,
            "action_id": action.action_id, "resource_ids": [case.resource_id], "kind": "ENTRY",
            "semantic_key": "entry", "subject_id": "test-account", "actor_id": "test-account",
            "credential_source": None, "authority_scope": {"allowed_action_ids": [],
                "allowed_resource_ids": [], "origin_authorization_event_id": None,
                "delegated_from_event_id": None}, "authorization_decision": None, "effect_id": None,
            "source_component": "business", "source_location": "business/handler",
            "correlation_kind": "EXPLICIT_PARENT", "evidence_refs": [], "recorded_at_us": 1}],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    trace = ExecutionTrace.model_validate_json(raw)
    assert trace.events[0].dispatch_effect_ids == ()
    assert json.dumps(trace.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() == raw
    evidence = seal_check_evidence(run_id="run_"+"1"*32, job_id="job_"+"2"*32, attempt=1,
        action_id=action.action_id, action_revision=action.action_revision, request_hash="a"*64,
        config_hash="b"*64, case=case, outcome=CheckCaseOutcome(execution_outcome="UNKNOWN",
            actual_identity_status="UNKNOWN", baseline_trusted=False, recovery_verified=False,
            run_correlated=False, resource_correlated=False), observations=(), trace=trace)
    encoded = canonical_check_document(evidence)
    assert b'"dispatch_effect_ids"' not in encoded
    assert canonical_check_document(parse_check_document(encoded, CheckEvidence)) == encoded
