# 成功派发与真实后果分开；旧字节兼容、分叉因果和缺口不能制造后果或精确定位。
from pathlib import Path
import json

import pytest

from product.backend.core.verification.breakpoints import BreakpointLocator, BreakpointType, BreakpointPrecision
from product.backend.core.verification.trace import ExecutionTrace, TraceEvent, TraceEventKind, TraceAuthorizationDecision
from product.protocols.check_result import CheckEvidence, canonical_check_document, parse_check_document
from tests.backend.core.verification.test_check_breakpoints import inputs


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


def test_prior_trace_and_evidence_remain_identical_canonical_bytes():
    directory=Path(__file__).resolve().parents[4]/"var/coordination/v113-c1-dispatch-causality"
    raw=(directory/"prior-trace.json").read_bytes()
    trace=ExecutionTrace.model_validate_json(raw)
    assert json.dumps(trace.model_dump(mode="json"),ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()==raw
    raw=(directory/"prior-evidence.json").read_bytes()
    assert canonical_check_document(parse_check_document(raw,CheckEvidence))==raw
