# 当前冻结孪生直接复用六类因果定位，验证身份映射和已发布 Case 引用隔离。
import pytest

from product.backend.core.verification.breakpoints import BreakpointLocator, BreakpointType, BreakpointPrecision
from product.backend.core.verification.trace import TraceEventKind, TraceAuthorityScope
from tests.backend.core.verification._support_check_breakpoints import (
    inputs,
)




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
