from __future__ import annotations

from pathlib import Path

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
    ObserverOutcomeStatus,
    ProvenanceType,
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

    def cleanup(self, path: str, *, case_id: str) -> None:
        return None

    def close(self) -> None:
        return None


def _owner_envelope(spec, correlation, phase, *, changed: bool) -> ObservationEnvelope:
    state = build_normalized_state({"value": "new" if changed else "old"})
    return ObservationEnvelope(observer_id=spec.observer_id, observer_type=spec.observer_type, phase=phase, target_id=spec.target.target_id, window=ObservationWindow(phase=phase, started_at_us=1, finished_at_us=2, timeout_us=spec.budget.timeout_us), correlation=correlation, causality=CausalityStatus.CORRELATED, completeness=ObservationCompleteness.COMPLETE, state=state, provenance=ObservationProvenance(provenance_type=ProvenanceType.OWNER_API, adapter_version="fake-owner", target_id=spec.target.target_id, source_sha256=state.canonical_sha256))


def _run(monkeypatch, tmp_path: Path, outcome: ExecutionOutcome):
    _FakeHttp.outcome = outcome
    def observe(self, executor, *, resource_id, owner_token, case_id, phase, known_secrets=()):
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
    evidence = _run(monkeypatch, tmp_path, ExecutionOutcome.FAILED)
    assert evidence.execution_fact.outcome is ExecutionOutcome.FAILED
    assert evidence.verdict is CaseVerdict.INCONCLUSIVE
