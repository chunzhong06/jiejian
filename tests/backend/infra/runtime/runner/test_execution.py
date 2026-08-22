from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from product.backend.core.lifecycle import CaseVerdict
from product.backend.core.verification.facts import ExecutionFact, ExecutionOutcome, TargetType
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import (
    CausalityStatus,
    Correlation,
    ObservationCompleteness,
    ObservationEnvelope,
    ObservationPhase,
    ObservationProvenance,
    ObservationWindow,
    ObserverType,
    ObserverOutcomeStatus,
    ProvenanceType,
    HttpOutcomeClassifier,
    HttpPredicate,
    HttpPredicateKind,
    build_normalized_state,
)
from product.backend.infra.execution.http import HttpResponse
from product.backend.infra.runtime.runner import execution
from tests.fixtures.runner import runner_input


class _FakeHttp:
    instances: list[_FakeHttp] = []
    outcome = ExecutionOutcome.ACCEPTED
    target_type = TargetType.WEB

    def __init__(self, *_args, **_kwargs) -> None:
        self.requests: list[tuple[str, str]] = []
        self.__class__.instances.append(self)

    def request(self, method: str, path: str, *, json_body=None, **_kwargs) -> HttpResponse:
        self.requests.append((method, path))
        return HttpResponse(status_code=200, data={"ok": True})

    def execute(self, binding, *, case_id: str, action_id: str, **_kwargs) -> ExecutionFact:
        return ExecutionFact(case_id=case_id, action_id=action_id, target_type=TargetType.WEB, outcome=self.outcome, execution_marker=case_id, input_hash="a" * 64, output_hash="b" * 64, reason_codes=() if self.outcome in {ExecutionOutcome.ACCEPTED, ExecutionOutcome.DENIED} else ("TRANSPORT_FAILURE",))

    def execute_detailed(self, binding, *, case_id: str, action_id: str, **_kwargs):
        return self.execute(binding, case_id=case_id, action_id=action_id), HttpResponse(status_code=200, data={"ok": True}, body=b'{"ok":true}')

    def cleanup(self, path: str, *, case_id: str) -> None:
        return None

    def close(self) -> None:
        return None


def _owner_envelope(spec, correlation, phase, *, changed: bool) -> ObservationEnvelope:
    state = build_normalized_state({"value": "new" if changed else "old"})
    return ObservationEnvelope(observer_id=spec.observer_id, observer_type=spec.observer_type, phase=phase, target_id=spec.target.target_id, window=ObservationWindow(phase=phase, started_at_us=1, finished_at_us=2, timeout_us=spec.budget.timeout_us), correlation=correlation, causality=CausalityStatus.CORRELATED, completeness=ObservationCompleteness.COMPLETE, state=state, provenance=ObservationProvenance(provenance_type=ProvenanceType.OWNER_API, adapter_version="fake-owner", target_id=spec.target.target_id, source_sha256=state.canonical_sha256))


def _run(monkeypatch, tmp_path: Path, outcome: ExecutionOutcome):
    _FakeHttp.outcome = outcome
    def observe(self, executor, *, resource_id, owner_token, case_id, phase, known_secrets=(), identity_runtime=None):
        return _owner_envelope(self.spec, Correlation(case_id=case_id, resource_id=resource_id, request_marker=case_id), phase, changed=phase is ObservationPhase.AFTER)
    monkeypatch.setattr(execution, "HttpExecutionAdapter", _FakeHttp)
    monkeypatch.setattr(execution.OwnerApiObserverAdapter, "observe", observe)
    runner = execution.RunnerExecutor(runner_input(), environ={"JIEJIAN_TEST_TOKEN": "subject-secret", "OWNER_READ_ONLY": "owner-secret"}, staging=tmp_path / "staging", clock=lambda: 10)
    try:
        return runner.run_case(runner_input().project_snapshot.plan.cases[0])
    finally:
        runner.http.close()


def test_runner_maps_accepted_execution_and_observed_effect(monkeypatch, tmp_path: Path) -> None:
    evidence = _run(monkeypatch, tmp_path, ExecutionOutcome.ACCEPTED)
    assert evidence.execution_fact.outcome is ExecutionOutcome.ACCEPTED
    assert evidence.verdict is CaseVerdict.SAFE


def test_runner_maps_denied_execution_without_core_http_knowledge(monkeypatch, tmp_path: Path) -> None:
    evidence = _run(monkeypatch, tmp_path, ExecutionOutcome.DENIED)
    assert evidence.execution_fact.outcome is ExecutionOutcome.DENIED
    assert evidence.verdict is CaseVerdict.INCONCLUSIVE


def test_runner_maps_transport_failure_to_inconclusive(monkeypatch, tmp_path: Path) -> None:
    import pytest
    with pytest.raises(JiejianError, match=ErrorCode.TARGET_EXECUTION_FAILED.value):
        _run(monkeypatch, tmp_path, ExecutionOutcome.FAILED)


def test_runner_resolves_202_only_after_bound_async_success() -> None:
    classifier = HttpOutcomeClassifier(
        accepted=(HttpPredicate(kind=HttpPredicateKind.STATUS_IN, statuses=(202,)),),
        completion_binding="task_completion",
    )
    pending = ExecutionFact(
        case_id="case-202",
        action_id="submit",
        target_type=TargetType.WEB,
        outcome=ExecutionOutcome.UNKNOWN,
        execution_marker="marker-202",
        input_hash="a" * 64,
        output_hash="b" * 64,
        reason_codes=("UNINTERPRETED_RESPONSE",),
    )
    correlation = Correlation(case_id="case-202", resource_id="resource-202", request_marker="marker-202")
    state = build_normalized_state({"task_state": "SUCCESS"})
    terminal = ObservationEnvelope(
        observer_id="async-observer",
        observer_type=ObserverType.ASYNC_TASK_STATUS,
        phase=ObservationPhase.EVENTUAL,
        target_id="async-target",
        window=ObservationWindow(
            phase=ObservationPhase.EVENTUAL,
            started_at_us=1,
            finished_at_us=2,
            timeout_us=10,
        ),
        correlation=correlation,
        causality=CausalityStatus.CORRELATED,
        completeness=ObservationCompleteness.COMPLETE,
        state=state,
        provenance=ObservationProvenance(
            provenance_type=ProvenanceType.ASYNC_TASK_API,
            adapter_version="test-async",
            target_id="async-target",
            source_sha256=state.canonical_sha256,
        ),
    )
    response = HttpResponse(status_code=202, data={}, body=b"{}")
    bindings = {"task_completion": SimpleNamespace(observer_id="async-observer")}

    without_terminal = execution._apply_terminal_completion(
        pending,
        response,
        classifier,
        completion_bindings=bindings,
        envelopes=(),
        case_id="case-202",
    )
    completed = execution._apply_terminal_completion(
        pending,
        response,
        classifier,
        completion_bindings=bindings,
        envelopes=(terminal,),
        case_id="case-202",
    )

    assert without_terminal.outcome is ExecutionOutcome.UNKNOWN
    assert completed.outcome is ExecutionOutcome.ACCEPTED
    assert completed.reason_codes == ()


def test_runner_cleanup_failure_is_a_single_fatal_reason() -> None:
    result = execution._result_error(
        runner_input(),
        ErrorCode.CLEANUP_FAILED.value,
        finished_at_us=20,
        cleanup_failed=True,
    )
    assert result.result_type.value == "FATAL_ERROR"
    assert result.error is not None and result.error.code == ErrorCode.CLEANUP_FAILED.value
    assert result.reason_codes == (ErrorCode.CLEANUP_FAILED.value,)
    assert result.cleanup.status.value == "FAILED"
    assert result.cleanup.finished_at_us == 20

    completed_cleanup = execution._result_error(
        runner_input(),
        "RUNNER_FATAL",
        finished_at_us=21,
        cleanup_succeeded=True,
    )
    assert completed_cleanup.cleanup.status.value == "SUCCEEDED"
    assert completed_cleanup.cleanup.finished_at_us == 21


def test_runner_safety_stop_with_cleanup_failure_is_fatal() -> None:
    result = execution._result_error(
        runner_input(),
        ErrorCode.SCOPE_URL.value,
        finished_at_us=20,
        safety_stopped=True,
        cleanup_failed=True,
    )
    assert result.result_type.value == "FATAL_ERROR"
    assert result.run_lifecycle.value == "FAILED"
    assert result.job_state.value == "FAILED"
    assert result.error is not None and result.error.code == ErrorCode.CLEANUP_FAILED.value
    assert result.reason_codes == (ErrorCode.CLEANUP_FAILED.value,)
    assert result.cleanup.status.value == "FAILED"
    assert result.cleanup.reason_codes == (ErrorCode.CLEANUP_FAILED.value,)


def test_runner_runtime_close_failure_is_cleanup_failure(monkeypatch, tmp_path: Path) -> None:
    class _FailingRuntime:
        instances = 0

        def __init__(self, *_args, **_kwargs) -> None:
            self.instance_id = self.__class__.instances
            self.__class__.instances += 1

        def bootstrap(self, _sender, *, requests=()) -> None:
            return None

        def set_csrf(self, *_args, **_kwargs) -> None:
            return None

        def close(self) -> None:
            if self.instance_id == 0:
                raise RuntimeError("runtime close failure")

    monkeypatch.setattr(execution, "HttpIdentityRuntime", _FailingRuntime)
    runner = execution.RunnerExecutor(
        runner_input(),
        environ={"JIEJIAN_TEST_TOKEN": "subject-secret", "OWNER_READ_ONLY": "owner-secret"},
        staging=tmp_path / "staging",
        clock=lambda: 20,
    )
    import pytest
    with pytest.raises(JiejianError) as captured:
        runner.run_case(runner_input().project_snapshot.plan.cases[0])
    assert captured.value.code == ErrorCode.CLEANUP_FAILED.value
