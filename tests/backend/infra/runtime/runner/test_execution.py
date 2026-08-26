# 验证隔离 Runner 运行时中的Runner 执行。

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from product.backend.core.lifecycle import CaseVerdict
from product.backend.core.verification.facts import ExecutionFact, ExecutionOutcome, TargetType
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import (
    CleanupIssue,
    CleanupIssueCode,
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
    RunnerFailurePhase,
    HttpOutcomeClassifier,
    HttpPredicate,
    HttpPredicateKind,
    build_normalized_state,
)
from product.backend.infra.execution.web import runtime as web_runtime
from product.backend.infra.execution.web.adapter import HttpResponse
from product.backend.infra.runtime.runner import composition
from product.backend.infra.runtime.runner.case_orchestrator import CaseExecutionFailure
from product.backend.infra.runtime.runner.executor import RunnerExecutor
from product.backend.infra.runtime.runner.progress import RunnerProgressEvent, RunnerProgressWriter
from product.backend.infra.runtime.runner.result_builder import evidence_from_case
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


def _run(monkeypatch, tmp_path: Path, outcome: ExecutionOutcome, progress=None):
    _FakeHttp.outcome = outcome

    def observe(self, executor, *, resource_id, owner_token, case_id, phase, known_secrets=(), identity_runtime=None):
        return _owner_envelope(self.spec, Correlation(case_id=case_id, resource_id=resource_id, request_marker=case_id), phase, changed=phase is ObservationPhase.AFTER)

    monkeypatch.setattr(web_runtime, "HttpExecutionAdapter", _FakeHttp)
    monkeypatch.setattr(web_runtime.OwnerApiObserverAdapter, "observe", observe)
    document = runner_input()
    runner = RunnerExecutor(
        document,
        runtime_factory=web_runtime.WebTargetRuntimeFactory(),
        environ={"JIEJIAN_TEST_TOKEN": "subject-secret", "OWNER_READ_ONLY": "owner-secret"},
        staging=tmp_path / "staging",
        clock=lambda: 10,
        progress=progress,
    )
    try:
        result = runner.run_case(document.project_snapshot.plan.cases[0])
        return evidence_from_case(document, result)
    finally:
        runner.close()


def test_runner_maps_accepted_execution_and_observed_effect(monkeypatch, tmp_path: Path) -> None:
    evidence = _run(monkeypatch, tmp_path, ExecutionOutcome.ACCEPTED)
    assert evidence.execution_fact.outcome is ExecutionOutcome.ACCEPTED
    assert evidence.verdict is CaseVerdict.SAFE


def test_runner_maps_denied_execution_without_core_http_knowledge(monkeypatch, tmp_path: Path) -> None:
    evidence = _run(monkeypatch, tmp_path, ExecutionOutcome.DENIED)
    assert evidence.execution_fact.outcome is ExecutionOutcome.DENIED
    assert evidence.verdict is CaseVerdict.INCONCLUSIVE


def test_runner_preserves_target_execution_failure_without_verdict(monkeypatch, tmp_path: Path) -> None:
    import pytest

    with pytest.raises(CaseExecutionFailure) as captured:
        _run(monkeypatch, tmp_path, ExecutionOutcome.FAILED)
    assert isinstance(captured.value.primary, JiejianError)
    assert captured.value.primary.code == ErrorCode.TARGET_EXECUTION_FAILED.value
    assert captured.value.phase is RunnerFailurePhase.TARGET


def test_runner_stops_before_target_when_baseline_observer_is_unavailable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def observe(
        self,
        executor,
        *,
        resource_id,
        owner_token,
        case_id,
        phase,
        known_secrets=(),
        identity_runtime=None,
    ):
        del executor, owner_token, known_secrets, identity_runtime
        return ObservationEnvelope(
            observer_id=self.spec.observer_id,
            observer_type=self.spec.observer_type,
            phase=phase,
            target_id=self.spec.target.target_id,
            window=ObservationWindow(
                phase=phase,
                started_at_us=1,
                finished_at_us=2,
                timeout_us=self.spec.budget.timeout_us,
            ),
            correlation=Correlation(
                case_id=case_id,
                resource_id=resource_id,
                request_marker=case_id,
            ),
            causality=CausalityStatus.UNVERIFIED,
            completeness=ObservationCompleteness.MISSING,
            reason_codes=("REQUIRED_OBSERVER_INCOMPLETE",),
        )

    monkeypatch.setattr(web_runtime, "HttpExecutionAdapter", _FakeHttp)
    monkeypatch.setattr(web_runtime.OwnerApiObserverAdapter, "observe", observe)
    document = runner_input()
    progress_path = tmp_path / "baseline-stop.jsonl"
    progress = RunnerProgressWriter(progress_path)
    runner = RunnerExecutor(
        document,
        runtime_factory=web_runtime.WebTargetRuntimeFactory(),
        environ={
            "JIEJIAN_TEST_TOKEN": "subject-secret",
            "OWNER_READ_ONLY": "owner-secret",
        },
        staging=tmp_path / "staging",
        clock=lambda: 10,
        progress=progress,
    )
    try:
        result = runner.run_case(document.project_snapshot.plan.cases[0])
    finally:
        runner.close()
        progress.close()

    assert result.verdict is CaseVerdict.INCONCLUSIVE
    assert result.reason_codes == ("BASELINE_OBSERVATION_INCOMPLETE",)
    assert all(method != "PATCH" for method, _path in _FakeHttp.instances[-1].requests)
    events = [RunnerProgressEvent.model_validate_json(line, strict=True) for line in progress_path.read_text(encoding="utf-8").splitlines()]
    assert [(item.phase.value, item.state.value) for item in events] == [
        ("PREPARE", "STARTED"), ("PREPARE", "COMPLETED"),
        ("BASELINE", "STARTED"),
        ("RECOVERY", "STARTED"), ("RECOVERY", "COMPLETED"),
    ]


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

    without_terminal = web_runtime._apply_terminal_completion(
        pending,
        response,
        classifier,
        completion_bindings=bindings,
        observations=(),
        case_id="case-202",
    )
    completed = web_runtime._apply_terminal_completion(
        pending,
        response,
        classifier,
        completion_bindings=bindings,
        observations=(terminal,),
        case_id="case-202",
    )

    assert without_terminal.outcome is ExecutionOutcome.UNKNOWN
    assert completed.outcome is ExecutionOutcome.ACCEPTED
    assert completed.reason_codes == ()


def test_runner_cleanup_failure_is_a_single_fatal_reason() -> None:
    result = composition._result_error(
        runner_input(),
        ErrorCode.CLEANUP_FAILED.value,
        phase=RunnerFailurePhase.POST_CASE_RECOVERY,
        finished_at_us=20,
        cleanup_issues=(
            CleanupIssue(code=CleanupIssueCode.POST_CASE_RECOVERY_FAILED),
        ),
    )
    assert result.result_type.value == "FATAL_ERROR"
    assert result.error is not None and result.error.code == ErrorCode.CLEANUP_FAILED.value
    assert result.reason_codes == (ErrorCode.CLEANUP_FAILED.value,)
    assert result.cleanup.status.value == "FAILED"
    assert result.cleanup.finished_at_us == 20

    completed_cleanup = composition._result_error(
        runner_input(),
        "RUNNER_FATAL",
        phase=RunnerFailurePhase.TARGET_VALIDATION,
        finished_at_us=21,
    )
    assert completed_cleanup.cleanup.status.value == "SUCCEEDED"
    assert completed_cleanup.cleanup.finished_at_us == 21


def test_runner_safety_stop_with_cleanup_failure_is_fatal() -> None:
    result = composition._result_error(
        runner_input(),
        ErrorCode.SCOPE_URL.value,
        phase=RunnerFailurePhase.TARGET_VALIDATION,
        finished_at_us=20,
        safety_stopped=True,
        cleanup_issues=(
            CleanupIssue(code=CleanupIssueCode.POST_CASE_RECOVERY_FAILED),
        ),
    )
    assert result.result_type.value == "FATAL_ERROR"
    assert result.run_lifecycle.value == "FAILED"
    assert result.job_state.value == "FAILED"
    assert result.error is not None and result.error.code == ErrorCode.SCOPE_URL.value
    assert result.reason_codes == (ErrorCode.SCOPE_URL.value,)
    assert result.cleanup.status.value == "FAILED"
    assert result.cleanup.issues[0].code is CleanupIssueCode.POST_CASE_RECOVERY_FAILED


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

    _FakeHttp.outcome = ExecutionOutcome.ACCEPTED
    monkeypatch.setattr(web_runtime, "HttpExecutionAdapter", _FakeHttp)
    monkeypatch.setattr(web_runtime, "HttpIdentityRuntime", _FailingRuntime)
    document = runner_input()
    runner = RunnerExecutor(
        document,
        runtime_factory=web_runtime.WebTargetRuntimeFactory(),
        environ={"JIEJIAN_TEST_TOKEN": "subject-secret", "OWNER_READ_ONLY": "owner-secret"},
        staging=tmp_path / "staging",
        clock=lambda: 20,
    )
    import pytest
    with pytest.raises(CaseExecutionFailure) as captured:
        runner.run_case(document.project_snapshot.plan.cases[0])
    assert isinstance(captured.value.primary, JiejianError)
    assert captured.value.primary.code == ErrorCode.CLEANUP_FAILED.value
    assert captured.value.phase is RunnerFailurePhase.POST_CASE_RECOVERY
    assert captured.value.cleanup_issues[0].code is CleanupIssueCode.IDENTITY_CLOSE_FAILED
    runner.close()


def test_runner_progress_records_bounded_business_phases_without_verdict_data(monkeypatch, tmp_path: Path) -> None:
    _FakeHttp.outcome = ExecutionOutcome.ACCEPTED
    monkeypatch.setattr(web_runtime, "HttpExecutionAdapter", _FakeHttp)
    monkeypatch.setattr(
        web_runtime.OwnerApiObserverAdapter,
        "observe",
        lambda self, executor, *, resource_id, owner_token, case_id, phase, known_secrets=(), identity_runtime=None: _owner_envelope(
            self.spec,
            Correlation(case_id=case_id, resource_id=resource_id, request_marker=case_id),
            phase,
            changed=phase is ObservationPhase.AFTER,
        ),
    )
    document = runner_input()
    progress_path = tmp_path / "progress.jsonl"
    writer = RunnerProgressWriter(progress_path)
    runner = RunnerExecutor(
        document,
        runtime_factory=web_runtime.WebTargetRuntimeFactory(),
        environ={"JIEJIAN_TEST_TOKEN": "subject-secret", "OWNER_READ_ONLY": "owner-secret"},
        staging=tmp_path / "staging",
        clock=lambda: 10,
        progress=writer,
        progress_clock=lambda: 77,
    )
    try:
        runner.run_case(document.project_snapshot.plan.cases[0])
    finally:
        runner.close()
        writer.close()

    lines = progress_path.read_text(encoding="utf-8").splitlines()
    events = [RunnerProgressEvent.model_validate_json(line, strict=True) for line in lines]
    allowed_fields = {
        "schema_version", "sequence", "case_id", "action_id",
        "twin_role", "phase", "state", "recorded_at_us",
    }
    assert all(set(json.loads(line)) == allowed_fields for line in lines)
    assert [(item.phase.value, item.state.value) for item in events] == [
        ("PREPARE", "STARTED"), ("PREPARE", "COMPLETED"),
        ("BASELINE", "STARTED"), ("BASELINE", "COMPLETED"),
        ("TARGET", "STARTED"), ("TARGET", "COMPLETED"),
        ("OBSERVE", "STARTED"), ("OBSERVE", "COMPLETED"),
        ("VERIFY", "STARTED"), ("VERIFY", "COMPLETED"),
        ("RECOVERY", "STARTED"), ("RECOVERY", "COMPLETED"),
    ]
    assert all(item.twin_role is None and item.case_id.startswith("case-") for item in events)
    assert all(item.recorded_at_us == 77 for item in events)
    assert all("subject-secret" not in line and "owner-secret" not in line for line in lines)
    with pytest.raises(ValueError):
        RunnerProgressEvent.model_validate(
            {**events[0].model_dump(mode="json"), "verdict": "PASS"},
            strict=True,
        )


def test_progress_writer_rejects_sensitive_ids_and_stops_at_budget(tmp_path: Path) -> None:
    rejected_path = tmp_path / "rejected.jsonl"
    writer = RunnerProgressWriter(rejected_path)
    assert writer.record(case_id="case-" + "a" * 32, action_id="secret-token", twin_role=None, phase="TARGET", state="STARTED", recorded_at_us=1) is False
    assert writer.enabled is False
    writer.close()
    path = tmp_path / "progress.jsonl"
    writer = RunnerProgressWriter(path)
    for index in range(256):
        assert writer.record(case_id="case-" + "a" * 32, action_id="modify", twin_role=None, phase="TARGET", state="STARTED", recorded_at_us=index + 1) is True
    assert writer.record(case_id="case-" + "a" * 32, action_id="modify", twin_role=None, phase="TARGET", state="STARTED", recorded_at_us=257) is False
    writer.close()
    assert len(path.read_text(encoding="utf-8").splitlines()) == 256


def test_progress_twin_roles_and_writer_failure_do_not_change_execution(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "roles.jsonl"
    writer = RunnerProgressWriter(path)
    assert writer.record(case_id="case-" + "a" * 32, action_id="modify", twin_role="ALLOW_CONTROL", phase="TARGET", state="STARTED", recorded_at_us=1)
    assert writer.record(case_id="case-" + "b" * 32, action_id="modify", twin_role="DENY_VARIANT", phase="TARGET", state="STARTED", recorded_at_us=2)
    writer.close()
    payloads = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [item["twin_role"] for item in payloads] == ["ALLOW_CONTROL", "DENY_VARIANT"]

    class BrokenProgress:
        def record(self, **_kwargs):
            raise OSError("sidecar unavailable")

    evidence = _run(monkeypatch, tmp_path / "broken", ExecutionOutcome.ACCEPTED, BrokenProgress())
    assert evidence.verdict is CaseVerdict.SAFE

    blocked_path = tmp_path / "directory-instead-of-file"
    blocked_path.mkdir()
    disabled_writer = RunnerProgressWriter(blocked_path)
    assert disabled_writer.enabled is False
    evidence = _run(monkeypatch, tmp_path / "open-failure", ExecutionOutcome.ACCEPTED, disabled_writer)
    assert evidence.verdict is CaseVerdict.SAFE
