# 验证真实审计适配器到当前 Trace 与凭据访问事实的关联、缺口和事件预算。
import os
import sys
from types import SimpleNamespace

import pytest

from product.backend.infra.observers.audit_log import run_audit_log_observer
from product.backend.infra.observers.check_trace import build_check_trace
from product.backend.infra.observers.effect_projector import EffectProjector
from product.protocols.observer import Correlation, ObservationPhase
from tests.backend.infra.observers.test_audit_log_observer import _spec, _record, _write, TRACE_FIELDS
from tests.fixtures.check_execution import execution_pair
from tests.backend.infra.execution.test_check_observers import observer_target


def _row(case, event_id, *, parent=None, kind="ENTRY", sequence=1):
    row = _record("run-marker", "task-check", event_id, "request_received" if kind == "ENTRY" else "credential_read",
        sequence, resource=case.resource_id, kind=kind,
        semantic_key="request_received" if kind == "ENTRY" else "credential_read",
        subject_id="subject-1", actor_id="subject-1", source_component="service",
        source_location="api:/read", recorded_at_us=sequence)
    if parent is not None:
        row["parent_event_id"] = parent
    if kind == "FINAL_EFFECT":
        row.update(effect_id=case.protected_effect_ids[0], effect="APPLIED")
    return row


def _trace(case, rows, *, trusted=True):
    envelope = SimpleNamespace(state=SimpleNamespace(canonical_data={"records": rows}))
    return build_check_trace(case=case, action_id="action-1", planned_subject_id="subject-1",
        marker="run-marker", groups=(((envelope,), trusted),))


def test_real_audit_source_preserves_explicit_causality_and_credential_access(tmp_path):
    request, bundle = execution_pair()
    case = request.actions[0].cases[0]
    rows = [_row(case, "entry"), _row(case, "read", parent="entry", kind="FINAL_EFFECT", sequence=2)]
    _write(tmp_path / "audit.jsonl", rows)
    spec = _spec(fields=TRACE_FIELDS)
    observed = run_audit_log_observer(spec,
        Correlation(case_id=case.case_id, resource_id=case.resource_id, request_marker="run-marker"),
        ObservationPhase.AFTER, attempt_dir=tmp_path / "attempt",
        parent_environ={**os.environ, "AUDIT_ROOT": str(tmp_path)}, python_executable=sys.executable)
    assert observed.outcome.status.value == "AVAILABLE"
    assert observed.envelope is not None
    trace = build_check_trace(case=case, action_id="action-1", planned_subject_id="subject-1",
        marker="run-marker", groups=(((observed.envelope,), True),))
    assert trace.complete
    assert trace.events[1].parent_event_ids == ("entry",)
    assert trace.events[1].effect_id == case.protected_effect_ids[0]
    assert trace.events[1].authority_scope.allowed_action_ids == ()
    proof = bundle.actions[0].proofs[0].model_copy(update={"effect_kind": "CREDENTIAL_ACCESS"})
    fact = EffectProjector.project_check(case_id=case.case_id, resource_id=case.resource_id,
        proof=proof, spec=spec, envelopes=(observed.envelope,))
    assert fact.effect.value == "CONFIRMED"
    assert str(tmp_path) not in trace.model_dump_json()


@pytest.mark.parametrize("fault,reason", [
    ("untrusted", "TRACE_SOURCE_INCOMPLETE"), ("other-run", "TRACE_CORRELATION_INVALID"),
    ("orphan", "TRACE_PARENT_MISSING"), ("conflict", "TRACE_EVENT_CONFLICT"),
    ("cycle", "TRACE_GRAPH_INVALID"), ("budget", "TRACE_BUDGET_EXCEEDED"),
])
def test_trace_gaps_never_become_complete_or_invent_parent_nodes(fault, reason):
    request, _ = execution_pair()
    case = request.actions[0].cases[0]
    rows = [_row(case, "entry"), _row(case, "read", parent="entry", kind="FINAL_EFFECT", sequence=2)]
    if fault == "other-run":
        rows[1]["case_tag"] = "another-run"
    elif fault == "orphan":
        rows[1]["parent_event_id"] = "missing"
    elif fault == "conflict":
        rows.append({**rows[0], "actor_id": "another-actor"})
    elif fault == "cycle":
        rows[0]["parent_event_id"] = "read"
    elif fault == "budget":
        rows = [_row(case, f"event-{index}", sequence=index) for index in range(600)]
    trace = _trace(case, rows, trusted=fault != "untrusted")
    assert not trace.complete and reason in trace.reason_codes
    assert len(trace.events) <= 512
    assert all(parent in {item.event_id for item in trace.events}
        for item in trace.events for parent in item.parent_event_ids)


def test_trace_uses_explicit_effect_and_does_not_infer_it_from_case():
    request, _ = execution_pair()
    case = request.actions[0].cases[0]
    row = _row(case, "read", kind="FINAL_EFFECT")
    del row["effect_id"]
    assert _trace(case, [row]).events[0].effect_id is None


def test_dispatch_projection_is_explicit_and_rejects_other_case_effects():
    request,_=execution_pair()
    case=request.actions[0].cases[0]
    row=_row(case,"dispatch",kind="MESSAGE")
    row["dispatch_effect_ids"]=[case.protected_effect_ids[0]]
    assert _trace(case,[row]).events[0].dispatch_effect_ids==case.protected_effect_ids
    row["dispatch_effect_ids"]=["unrelated-effect"]
    trace=_trace(case,[row])
    assert not trace.complete and not trace.events


def test_auxiliary_runtime_keeps_source_level_and_failed_later_window_is_partial(observer_target, tmp_path):
    from product.backend.infra.execution.check_executor import CheckExecutor
    from product.backend.infra.execution.web.check_runtime import CheckWebRuntime
    from product.backend.infra.observers.check_runtime import CheckObserverRuntime

    port, state, _ = observer_target
    spec = _spec(fields=TRACE_FIELDS)
    def configure(payload):
        proof = payload["actions"][0]["proofs"][0]
        proof["auxiliary_sources"] = [dict(observer_id=spec.observer_id, descriptor_fingerprint="a" * 64,
            observation_identity_id=proof["observation_identity_id"], level="DIAGNOSIS_REQUIRED",
            source_label="受控审计", source_location="audit/events", trace_namespace="application")]
        payload["observers"].append(spec.model_dump(mode="json"))
    request, bundle = execution_pair(port=port, configure=configure)
    case, action = request.actions[0].cases[0], bundle.actions[0]
    environment = {**os.environ, "CHECK_TEST_BEARER": "loopback-fixture-value", "AUDIT_ROOT": str(tmp_path)}
    web = CheckWebRuntime(bundle, environ=environment, cancellation_requested=lambda: False)
    runtime = CheckObserverRuntime(bundle, web, attempt_dir=tmp_path / "observer",
        environ=environment, cancellation_requested=lambda: False)
    # 直接使用生产辅助来源编排入口，主证明对象保持原值。
    executor = object.__new__(CheckExecutor)
    executor.observers = runtime
    try:
        baseline = executor._observe_auxiliary(action, case, "BASELINE")
        assert baseline[0].observation.state == "UNKNOWN"
        rows = [_row(case, "entry"), _row(case, "read", parent="entry", kind="FINAL_EFFECT", sequence=2)]
        for row in rows:
            row["case_tag"] = web.request_marker(case.case_id)
        _write(tmp_path / "audit.jsonl", rows)
        observed = executor._observe_auxiliary(action, case, "AFTER")
        assert observed[0].observation.level == "DIAGNOSIS_REQUIRED"
        assert observed[0].observation.observer_id == spec.observer_id
        assert case.proof_requirements[0].level == "VERDICT_REQUIRED"
        assert runtime.trace(action, case).complete
        # 前一次完整结果不能掩盖本次缺失身份信息的观察失败。
        state["subject_id"] = "unmapped-account"
        executor._observe_auxiliary(action, case, "AFTER")
        assert not runtime.trace(action, case).complete
    finally:
        web.close()
