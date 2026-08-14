from __future__ import annotations

from pathlib import Path

import pytest

from jiejian.domain.lifecycle import CaseVerdict
from jiejian.errors import ErrorCode, JiejianError
from jiejian.protocols import (
    CausalityStatus,
    CorrelationV2,
    ObservationCompleteness,
    ObservationEnvelopeV2,
    ObservationPhase,
    ObservationProvenanceV2,
    ObservationWindowV2,
    ObserverOutcomeStatus,
    ProvenanceType,
    build_normalized_state,
    canonical_runner_v2_json_bytes,
    parse_runner_result_v2,
)
from jiejian.runner import execution_v2
from jiejian.verification.http import HttpResponse
from jiejian.verification.models import Identity
from jiejian.runner import execution

from tests.execution.protocol.test_runner_v2 import _evidence, _input


class _FakeHttp:
    instances: list[_FakeHttp] = []

    def __init__(self, *_args, **_kwargs) -> None:
        self.requests: list[tuple[str, str, dict[str, object] | None]] = []
        self.__class__.instances.append(self)

    def request(self, method: str, path: str, *, json_body=None, **_kwargs) -> HttpResponse:
        self.requests.append((method, path, json_body))
        return HttpResponse(status_code=200, data={"accepted": True})

    def close(self) -> None:
        return None


def _owner_envelope(spec, correlation, phase, *, changed: bool) -> ObservationEnvelopeV2:
    state = build_normalized_state({"status_code": 200, "data": {"value": "new" if changed else "old"}})
    return ObservationEnvelopeV2(
        observer_id=spec.observer_id,
        observer_type=spec.observer_type,
        phase=phase,
        target_id=spec.target.target_id,
        window=ObservationWindowV2(phase=phase, started_at_us=1, finished_at_us=2, timeout_us=spec.budget.timeout_us),
        correlation=correlation,
        causality=CausalityStatus.CORRELATED,
        completeness=ObservationCompleteness.COMPLETE,
        state=state,
        provenance=ObservationProvenanceV2(
            provenance_type=ProvenanceType.OWNER_API,
            adapter_version="fake-owner",
            target_id=spec.target.target_id,
            source_sha256=state.canonical_sha256,
        ),
    )


def test_v2_case_orders_before_request_after_and_produces_evidence(monkeypatch, tmp_path: Path) -> None:
    document = _input()
    calls: list[str] = []

    def observe(self, executor, *, resource_id, owner_token, case_id, phase, known_secrets=()):
        calls.append(phase.value)
        return _owner_envelope(self.spec, CorrelationV2(case_id=case_id, resource_id=resource_id, request_marker=case_id), phase, changed=phase is ObservationPhase.AFTER)

    monkeypatch.setattr(execution_v2, "HttpExecutor", _FakeHttp)
    monkeypatch.setattr(execution_v2.OwnerApiObserverV2Adapter, "observe", observe)
    runner = execution_v2.RunnerV2Executor(document, environ={"JIEJIAN_TEST_TOKEN": "subject-secret", "OWNER_READ_ONLY": "owner-secret"}, staging=tmp_path / "staging", clock=lambda: 10)
    evidence = runner.run_case(document.project_snapshot.plan.cases[0])
    runner.http.close()

    assert calls == ["BEFORE", "AFTER"]
    assert [item[0:2] for item in _FakeHttp.instances[-1].requests] == [("POST", "/reset"), ("PATCH", "/resources/document"), ("POST", "/reset")]
    assert evidence.verdict is CaseVerdict.SAFE
    assert evidence.request_fact.status_code == 200
    assert all("subject-secret" not in repr(item.model_dump(mode="python")) for item in evidence.observations)


def test_required_before_failure_does_not_send_business_request(monkeypatch, tmp_path: Path) -> None:
    document = _input()
    calls: list[str] = []

    def observe(self, executor, *, resource_id, owner_token, case_id, phase, known_secrets=()):
        calls.append(phase.value)
        envelope = _owner_envelope(self.spec, CorrelationV2(case_id=case_id, resource_id=resource_id, request_marker=case_id), phase, changed=False)
        return envelope.model_copy(update={
            "completeness": ObservationCompleteness.MISSING,
            "state": None,
            "provenance": None,
            "causality": CausalityStatus.CORRELATED,
            "reason_codes": ("OWNER_API_MISSING",),
        })

    monkeypatch.setattr(execution_v2, "HttpExecutor", _FakeHttp)
    monkeypatch.setattr(execution_v2.OwnerApiObserverV2Adapter, "observe", observe)
    runner = execution_v2.RunnerV2Executor(document, environ={"JIEJIAN_TEST_TOKEN": "subject-secret", "OWNER_READ_ONLY": "owner-secret"}, staging=tmp_path / "staging", clock=lambda: 10)
    evidence = runner.run_case(document.project_snapshot.plan.cases[0])
    runner.http.close()

    assert calls == ["BEFORE"]
    assert [item[0] for item in _FakeHttp.instances[-1].requests] == ["POST", "POST"]
    assert evidence.verdict is CaseVerdict.INCONCLUSIVE
    assert evidence.request_fact.failure_code == "V2_REQUIRED_OBSERVER_INCOMPLETE"
    assert evidence.outcomes[0].status is ObserverOutcomeStatus.INCONCLUSIVE


def test_schema_two_is_dispatched_before_v1_parser(monkeypatch, tmp_path: Path) -> None:
    called = []
    monkeypatch.setattr(execution, "execute_runner_v2_attempt", lambda *args, **kwargs: called.append((args, kwargs)) or 0)
    input_path = tmp_path / "input.json"
    staging = tmp_path / "staging"
    input_path.write_text('{"schema_version":"2","opaque":"bounded"}', encoding="utf-8")
    assert execution.execute_runner_attempt(input_path, staging, environ={}) == 0
    assert called and called[0][0][0] == input_path


@pytest.mark.parametrize(
    "raw",
    [
        b"\xef\xbb\xbf{\"schema_version\":\"2\"}",
        b'{"schema_version":"2","schema_version":"2"}',
        b'{"schema_version":"3"}',
        b'{"schema_version":"1","unknown":true}',
    ],
)
def test_runner_entry_rejects_invalid_version_documents_with_protocol_exit(tmp_path: Path, raw: bytes) -> None:
    input_path = tmp_path / "input.json"
    input_path.write_bytes(raw)
    assert execution.execute_runner_attempt(input_path, tmp_path / "staging", environ={}) == 64


def test_v2_attempt_writes_evidence_and_result_staging_artifacts(monkeypatch, tmp_path: Path) -> None:
    document = _input()

    class _FakeRunner:
        def __init__(self, *args, **kwargs) -> None:
            self.http = _FakeHttp()

        def run_case(self, case):
            return _evidence()

    monkeypatch.setattr(execution_v2, "RunnerV2Executor", _FakeRunner)
    input_path = tmp_path / "input.json"
    input_path.write_bytes(canonical_runner_v2_json_bytes(document, known_secrets=("subject-secret", "owner-secret")))
    staging = tmp_path / "staging"
    assert execution_v2.execute_runner_v2_attempt(
        input_path,
        staging,
        environ={"JIEJIAN_TEST_TOKEN": "subject-secret", "OWNER_READ_ONLY": "owner-secret"},
        finished_at_us=lambda: 10,
    ) == 0
    result = parse_runner_result_v2((staging / "result.json").read_bytes())
    assert result.verdict.value == "INCONCLUSIVE"
    assert result.coverage_gap_count > 0
    assert len(result.evidence) == 1
    evidence_path = staging / "artifacts" / "evidence" / f"{result.evidence[0].evidence_id}.json"
    assert evidence_path.exists()
    assert evidence_path.read_bytes() == canonical_runner_v2_json_bytes(result.evidence[0], known_secrets=("subject-secret", "owner-secret"))
    assert result.finished_at_us == 10


@pytest.mark.parametrize("failure", ["open", "fsync", "replace"])
def test_v2_artifact_write_failures_return_write_exit_and_leave_no_partial(monkeypatch, tmp_path: Path, failure: str) -> None:
    document = _input()

    class _FakeRunner:
        def __init__(self, *args, **kwargs) -> None:
            self.http = _FakeHttp()

        def run_case(self, case):
            return _evidence()

    monkeypatch.setattr(execution_v2, "RunnerV2Executor", _FakeRunner)
    input_path = tmp_path / "input.json"
    input_path.write_bytes(canonical_runner_v2_json_bytes(document, known_secrets=("subject-secret", "owner-secret")))
    if failure == "open":
        def fail_open(*args, **kwargs):
            raise OSError("open failure")

        monkeypatch.setattr(execution_v2, "open", fail_open, raising=False)
    elif failure == "fsync":
        def fail_fsync(*args, **kwargs):
            raise OSError("fsync failure")

        monkeypatch.setattr(execution_v2.os, "fsync", fail_fsync)
    else:
        def fail_replace(*args, **kwargs):
            raise OSError("replace failure")

        monkeypatch.setattr(execution_v2.os, "replace", fail_replace)
    staging = tmp_path / f"staging-{failure}"
    assert execution_v2.execute_runner_v2_attempt(
        input_path,
        staging,
        environ={"JIEJIAN_TEST_TOKEN": "subject-secret", "OWNER_READ_ONLY": "owner-secret"},
        finished_at_us=lambda: 10,
    ) == execution_v2.RUNNER_EXIT_WRITE
    assert not list(staging.rglob("*.partial"))


def test_v2_existing_staging_is_a_write_failure(monkeypatch, tmp_path: Path) -> None:
    document = _input()
    input_path = tmp_path / "input.json"
    input_path.write_bytes(canonical_runner_v2_json_bytes(document, known_secrets=("subject-secret", "owner-secret")))
    staging = tmp_path / "staging"
    staging.mkdir()
    assert execution_v2.execute_runner_v2_attempt(
        input_path,
        staging,
        environ={"JIEJIAN_TEST_TOKEN": "subject-secret", "OWNER_READ_ONLY": "owner-secret"},
        finished_at_us=lambda: 10,
    ) == execution_v2.RUNNER_EXIT_WRITE


@pytest.mark.parametrize(
    "options",
    [{}, {"cancelled": True}, {"safety_stopped": True}, {"cleanup_failed": True}],
)
def test_v2_error_results_use_injected_finished_time(options) -> None:
    document = _input()
    result = execution_v2._result_error(document, "V2_TEST_ERROR", finished_at_us=123, **options)
    assert result.finished_at_us == 123


def test_unused_snapshot_identity_secret_is_not_required(monkeypatch, tmp_path: Path) -> None:
    document = _input()
    extra = Identity(schema_version="1", id="identity-unused", role="member", secret_ref="env:UNUSED_IDENTITY")
    snapshot = document.project_snapshot.model_copy(update={
        "identities": (*document.project_snapshot.identities, extra),
    })
    document = document.model_copy(update={"project_snapshot": snapshot})

    def observe(self, executor, *, resource_id, owner_token, case_id, phase, known_secrets=()):
        return _owner_envelope(self.spec, CorrelationV2(case_id=case_id, resource_id=resource_id, request_marker=case_id), phase, changed=phase is ObservationPhase.AFTER)

    monkeypatch.setattr(execution_v2, "HttpExecutor", _FakeHttp)
    monkeypatch.setattr(execution_v2.OwnerApiObserverV2Adapter, "observe", observe)
    runner = execution_v2.RunnerV2Executor(
        document,
        environ={"JIEJIAN_TEST_TOKEN": "subject-secret", "OWNER_READ_ONLY": "owner-secret"},
        staging=tmp_path / "staging",
        clock=lambda: 10,
    )
    assert runner.run_case(document.project_snapshot.plan.cases[0]).verdict is CaseVerdict.SAFE
    runner.http.close()


def test_bound_subject_secret_is_still_required(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(execution_v2, "HttpExecutor", _FakeHttp)
    with pytest.raises(JiejianError) as error:
        execution_v2.RunnerV2Executor(
            _input(),
            environ={"OWNER_READ_ONLY": "owner-secret"},
            staging=tmp_path / "staging",
            clock=lambda: 10,
        )
    assert error.value.code == ErrorCode.SECRET_MISSING.value


def test_owner_request_timeout_is_observer_inconclusive(monkeypatch, tmp_path: Path) -> None:
    def observe(*args, **kwargs):
        raise JiejianError(ErrorCode.EXEC_TIMEOUT, "timeout")

    monkeypatch.setattr(execution_v2, "HttpExecutor", _FakeHttp)
    monkeypatch.setattr(execution_v2.OwnerApiObserverV2Adapter, "observe", observe)
    runner = execution_v2.RunnerV2Executor(
        _input(),
        environ={"JIEJIAN_TEST_TOKEN": "subject-secret", "OWNER_READ_ONLY": "owner-secret"},
        staging=tmp_path / "staging",
        clock=lambda: 10,
    )
    evidence = runner.run_case(_input().project_snapshot.plan.cases[0])
    runner.http.close()
    assert evidence.verdict is CaseVerdict.INCONCLUSIVE
    assert evidence.outcomes[0].status is ObserverOutcomeStatus.INCONCLUSIVE
