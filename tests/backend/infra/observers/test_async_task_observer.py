from __future__ import annotations

import json
import subprocess
from pathlib import Path

import httpx
import pytest

import product.backend.infra.observers.async_task as async_module
from product.protocols import (
    AsyncTaskApiLocator,
    AsyncTaskObserverInvocation,
    AsyncTaskPollBudget,
    AsyncTaskStatus,
    Correlation,
    ObservationCompleteness,
    ObservationPhase,
    ObserverBudget,
    ObserverOutcomeStatus,
    ObserverSpec,
    ObserverTarget,
    ObserverType,
)
from tests.fixtures.runtime_environment import runtime_identity_environment


def _spec(*, base_url: str = "https://127.0.0.1:8443", allow_loopback_http: bool = False, max_polls: int = 4, poll_interval_us: int = 0, timeout_us: int = 5_000_000, max_response_bytes: int = 8192, common_max_bytes: int | None = None) -> ObserverSpec:
    locator = AsyncTaskApiLocator(
        base_url=base_url,
        relative_path_template="/observer/tasks/by-case/{request_marker}",
        read_only_credential_ref="env:TASK_TOKEN",
        allow_private_network=True,
        allow_loopback_http=allow_loopback_http,
        poll_budget=AsyncTaskPollBudget(max_polls=max_polls, poll_interval_us=poll_interval_us, per_request_timeout_us=100_000, max_response_bytes=max_response_bytes),
    )
    return ObserverSpec(
        observer_id="async_observer",
        observer_type=ObserverType.ASYNC_TASK_STATUS,
        target=ObserverTarget(target_id="task-state", locator=locator, normalization_id="task-state", normalization_version="1.0"),
        phases=(ObservationPhase.EVENTUAL,),
        required=True,
        budget=ObserverBudget(timeout_us=timeout_us, max_rows=1, max_bytes=common_max_bytes or max_response_bytes),
    )


def _response(state: str, *, task_id: str | None = "task-1", final_result: dict[str, object] | None = None, case_tag: str = "case-1", resource_id: str = "resource-a") -> bytes:
    return json.dumps({"schema_version": "1", "case_tag": case_tag, "resource_id": resource_id, "task_id": task_id, "state": state, "final_result": final_result}, separators=(",", ":")).encode()


def _invocation(spec: ObserverSpec | None = None) -> AsyncTaskObserverInvocation:
    return AsyncTaskObserverInvocation(spec=spec or _spec(), correlation=Correlation(case_id="case-1", resource_id="resource-a", request_marker="case-1"), phase=ObservationPhase.EVENTUAL)


def _run_fake(monkeypatch: pytest.MonkeyPatch, responses: list[bytes], *, status_codes: list[int] | None = None, spec: ObserverSpec | None = None):
    invocation = _invocation(spec)
    monkeypatch.setenv("TASK_TOKEN", "opaque-task-secret")
    queue = list(responses)
    codes = list(status_codes or [200] * len(queue))

    class Response:
        def __init__(self, content: bytes, status_code: int) -> None:
            self.content = content
            self.status_code = status_code

        def iter_bytes(self):
            yield self.content

    class Stream:
        def __init__(self, response: Response) -> None:
            self.response = response

        def __enter__(self) -> Response:
            return self.response

        def __exit__(self, *args: object) -> None:
            return None

    class Client:
        last: Response | None = None

        def stream(self, method: str, url: str, *, headers: dict[str, str]) -> Stream:
            assert headers == {"Authorization": "Bearer opaque-task-secret"}
            if not queue:
                assert self.last is not None
                return Stream(self.last)
            self.last = Response(queue.pop(0), codes.pop(0))
            return Stream(self.last)

        def close(self) -> None:
            pass

    monkeypatch.setattr(async_module.httpx, "Client", lambda **kwargs: Client())
    envelope = async_module._run_child(invocation, utc_now_us=lambda: 100)
    return envelope, async_module.evaluate_observer_outcome(envelope, required=True)


@pytest.mark.parametrize(
    ("responses", "expected"),
    [
        ([_response("NOT_CREATED", task_id=None)], "NOT_CREATED"),
        ([_response("QUEUED"), _response("RUNNING"), _response("SUCCESS", final_result={"ok": True})], "SUCCESS"),
        ([_response("FAILED", final_result={"ok": False})], "FAILED"),
        ([_response("TIMED_OUT", final_result=None)], "TIMED_OUT"),
    ],
)
def test_async_task_states_are_strict_and_deterministic(monkeypatch: pytest.MonkeyPatch, responses: list[bytes], expected: str) -> None:
    envelope, outcome = _run_fake(monkeypatch, responses)
    assert envelope.completeness is ObservationCompleteness.COMPLETE
    assert outcome.status is ObserverOutcomeStatus.AVAILABLE
    assert envelope.state is not None
    assert envelope.state.canonical_data["task_state"] == expected


def test_async_task_can_start_at_running_and_all_not_created_are_negative_observation(monkeypatch: pytest.MonkeyPatch) -> None:
    envelope, outcome = _run_fake(monkeypatch, [_response("RUNNING"), _response("SUCCESS", final_result={"value": "done"})], spec=_spec(max_polls=2))
    assert outcome.status is ObserverOutcomeStatus.AVAILABLE
    assert envelope.state is not None and envelope.state.canonical_data["states_seen"] == ["RUNNING", "SUCCESS"]
    envelope, outcome = _run_fake(monkeypatch, [_response("NOT_CREATED", task_id=None), _response("NOT_CREATED", task_id=None)], spec=_spec(max_polls=2))
    assert outcome.status is ObserverOutcomeStatus.AVAILABLE
    assert envelope.state is not None and envelope.state.canonical_data["task_state"] == "NOT_CREATED"


def test_async_task_stops_after_first_terminal_response(monkeypatch: pytest.MonkeyPatch) -> None:
    invocation = _invocation(_spec(max_polls=3))
    monkeypatch.setenv("TASK_TOKEN", "opaque-task-secret")
    calls = 0

    class Client:
        def stream(self, method: str, url: str, *, headers: dict[str, str]) -> object:
            nonlocal calls
            calls += 1
            if calls > 1:
                raise AssertionError("terminal state must stop further polling")
            response = type("Response", (), {"status_code": 200, "iter_bytes": lambda self: iter((_response("SUCCESS"),))})()
            return type("Stream", (), {"__enter__": lambda self: response, "__exit__": lambda self, *args: None})()

        def close(self) -> None:
            pass

    monkeypatch.setattr(async_module.httpx, "Client", lambda **kwargs: Client())
    envelope = async_module._run_child(invocation, utc_now_us=lambda: 100)
    assert calls == 1
    assert envelope.completeness is ObservationCompleteness.COMPLETE


def test_async_task_allows_repeated_nonterminal_states(monkeypatch: pytest.MonkeyPatch) -> None:
    envelope, outcome = _run_fake(
        monkeypatch,
        [_response("QUEUED"), _response("QUEUED"), _response("RUNNING"), _response("RUNNING"), _response("SUCCESS")],
        spec=_spec(max_polls=5),
    )
    assert outcome.status is ObserverOutcomeStatus.AVAILABLE
    assert envelope.state is not None
    assert envelope.state.canonical_data["states_seen"] == ["QUEUED", "QUEUED", "RUNNING", "RUNNING", "SUCCESS"]


def test_async_task_common_response_budget_is_cumulative(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = _spec(max_polls=2, max_response_bytes=150, common_max_bytes=200)
    envelope, outcome = _run_fake(monkeypatch, [_response("QUEUED"), _response("QUEUED")], spec=spec)
    assert outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    assert envelope.completeness is ObservationCompleteness.PARTIAL
    assert "ASYNC_TASK_RESPONSE_LIMIT" in envelope.reason_codes


@pytest.mark.parametrize("responses", [[_response("RUNNING"), _response("QUEUED")], [_response("QUEUED", task_id="task-1"), _response("RUNNING", task_id="task-2")]])
def test_async_task_rejects_state_and_task_conflicts(monkeypatch: pytest.MonkeyPatch, responses: list[bytes]) -> None:
    envelope, outcome = _run_fake(monkeypatch, responses)
    assert outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    assert envelope.completeness is ObservationCompleteness.PARTIAL
    assert "ASYNC_TASK_STATE_CONFLICT" in envelope.reason_codes


def test_async_task_rejects_correlation_and_malformed_payloads(monkeypatch: pytest.MonkeyPatch) -> None:
    envelope, outcome = _run_fake(monkeypatch, [_response("SUCCESS", case_tag="other-case")])
    assert outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    assert "ASYNC_TASK_CORRELATION_CONFLICT" in envelope.reason_codes
    duplicate = b'{"schema_version":"1","case_tag":"case-1","case_tag":"case-1","resource_id":"resource-a","task_id":"task-1","state":"SUCCESS","final_result":null}'
    envelope, outcome = _run_fake(monkeypatch, [duplicate])
    assert outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    assert "ASYNC_TASK_RESPONSE_INVALID" in envelope.reason_codes


def test_async_task_http_failures_redirect_and_response_limit_are_inconclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    for code in (401, 403, 429, 500, 302):
        envelope, outcome = _run_fake(monkeypatch, [b"{}"], status_codes=[code])
        assert outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
        assert envelope.completeness is ObservationCompleteness.PARTIAL
    envelope, outcome = _run_fake(monkeypatch, [_response("SUCCESS", final_result={"x": "y" * 500})], spec=_spec(max_response_bytes=64))
    assert outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    assert "ASYNC_TASK_RESPONSE_LIMIT" in envelope.reason_codes


def test_async_task_scope_rejects_unsafe_origins_and_requires_loopback_http() -> None:
    with pytest.raises(ValueError):
        _spec(base_url="http://127.0.0.1:8080")
    with pytest.raises(ValueError):
        _spec(base_url="https://example.test:443")
    with pytest.raises(ValueError):
        AsyncTaskApiLocator(base_url="https://127.0.0.1:8443", relative_path_template="/observer/../{request_marker}", read_only_credential_ref="env:TASK_TOKEN", allow_private_network=True, allow_loopback_http=False, poll_budget=AsyncTaskPollBudget(max_polls=1, poll_interval_us=0, per_request_timeout_us=1, max_response_bytes=100))
    with pytest.raises(ValueError):
        AsyncTaskApiLocator(base_url="https://user:pass@127.0.0.1:8443", relative_path_template="/observer/tasks/{request_marker}", read_only_credential_ref="env:TASK_TOKEN", allow_private_network=True, allow_loopback_http=False, poll_budget=AsyncTaskPollBudget(max_polls=1, poll_interval_us=0, per_request_timeout_us=1, max_response_bytes=100))
    with pytest.raises(ValueError):
        AsyncTaskApiLocator(base_url="https://169.254.169.254:443", relative_path_template="/observer/tasks/{request_marker}", read_only_credential_ref="env:TASK_TOKEN", allow_private_network=True, allow_loopback_http=False, poll_budget=AsyncTaskPollBudget(max_polls=1, poll_interval_us=0, per_request_timeout_us=1, max_response_bytes=100))
    assert _spec(base_url="http://127.0.0.1:8080", allow_loopback_http=True).target.locator.base_url == "http://127.0.0.1:8080"


def test_async_task_parent_timeout_cancel_and_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Process:
        returncode = None
        def __init__(self) -> None:
            self.terminated = False
            self.killed = False
            self.waits: list[float | None] = []
        def wait(self, timeout: float | None = None) -> int:
            self.waits.append(timeout)
            if self.killed:
                return -9
            raise subprocess.TimeoutExpired("async", timeout)

        def poll(self) -> int | None:
            return -9 if self.killed else None
        def terminate(self) -> None:
            self.terminated = True
        def kill(self) -> None:
            self.killed = True

    process = Process()
    monkeypatch.setattr(async_module.subprocess, "Popen", lambda *args, **kwargs: process)
    clock_values = iter((0, 0, 1_000_000))
    monkeypatch.setattr(async_module.time, "monotonic_ns", lambda: next(clock_values))
    spec = _spec(timeout_us=1_000)
    result = async_module.run_async_task_observer(spec, _invocation(spec).correlation, ObservationPhase.EVENTUAL, attempt_dir=tmp_path / "attempt", parent_environ=runtime_identity_environment(tmp_path / "var", extra={"TASK_TOKEN": "opaque-task-secret"}))
    assert result.outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    assert result.envelope is not None and result.envelope.completeness is ObservationCompleteness.TIMED_OUT
    assert process.killed
    assert len(process.waits) == 3
    assert process.waits[0] <= async_module._SUPERVISION_SLICE_SECONDS
    assert all(
        timeout is not None
        and 0 <= timeout <= async_module._PROCESS_REAP_TIMEOUT_SECONDS
        for timeout in process.waits[1:]
    )
    assert not list((tmp_path / "attempt").glob("async-task-observer-*.json"))
    assert not list((tmp_path / "attempt").glob(".*async-task-observer-*.tmp"))


def test_async_task_parent_cancel_terminates_and_returns_inconclusive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Process:
        returncode = None

        def __init__(self) -> None:
            self.terminated = False
            self.waits = 0
            self.wait_timeouts: list[float | None] = []

        def wait(self, timeout: float | None = None) -> int:
            self.waits += 1
            self.wait_timeouts.append(timeout)
            if self.terminated:
                return -15
            if self.waits == 2:
                (tmp_path / "attempt" / "cancel.requested").write_text("", encoding="ascii")
            raise subprocess.TimeoutExpired("async", timeout)

        def poll(self) -> int | None:
            return -15 if self.terminated else None

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.terminated = True

    process = Process()
    monkeypatch.setattr(async_module.subprocess, "Popen", lambda *args, **kwargs: process)
    spec = _spec(timeout_us=1_000_000)
    result = async_module.run_async_task_observer(spec, _invocation(spec).correlation, ObservationPhase.EVENTUAL, attempt_dir=tmp_path / "attempt", parent_environ=runtime_identity_environment(tmp_path / "var", extra={"TASK_TOKEN": "opaque-task-secret"}))
    assert result.outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    assert result.envelope is not None and "ASYNC_TASK_CANCELLED" in result.envelope.reason_codes
    assert process.terminated
    assert (tmp_path / "attempt" / "cancel.requested").is_file()
    assert process.waits >= 2
    assert process.wait_timeouts[0] <= async_module._SUPERVISION_SLICE_SECONDS
    assert all(
        timeout is not None
        and 0 <= timeout <= async_module._PROCESS_REAP_TIMEOUT_SECONDS
        for timeout in process.wait_timeouts[2:]
    ), process.wait_timeouts


def test_async_task_request_error_is_inconclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    invocation = _invocation()
    monkeypatch.setenv("TASK_TOKEN", "opaque-task-secret")

    class Client:
        def stream(self, method: str, url: str, *, headers: dict[str, str]) -> object:
            raise httpx.ConnectError("local fake transport")

        def close(self) -> None:
            pass

    monkeypatch.setattr(async_module.httpx, "Client", lambda **kwargs: Client())
    envelope = async_module._run_child(invocation, utc_now_us=lambda: 100)
    assert envelope.completeness is ObservationCompleteness.PARTIAL
    assert async_module.evaluate_observer_outcome(envelope, required=True).status is ObserverOutcomeStatus.INCONCLUSIVE
    assert "ASYNC_TASK_UNAVAILABLE" in envelope.reason_codes


def test_async_task_child_cancel_marker_prevents_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    invocation = _invocation()
    monkeypatch.setenv("TASK_TOKEN", "opaque-task-secret")
    monkeypatch.setenv("JIEJIAN_ATTEMPT_DIR", str(tmp_path))
    (tmp_path / "cancel.requested").write_text("", encoding="ascii")

    class Client:
        def __init__(self, **kwargs: object) -> None:
            raise AssertionError("cancelled child must not construct a client")

    monkeypatch.setattr(async_module.httpx, "Client", Client)
    envelope = async_module._run_child(invocation, utc_now_us=lambda: 100)
    assert envelope.completeness is ObservationCompleteness.PARTIAL
    assert "ASYNC_TASK_CANCELLED" in envelope.reason_codes
    assert async_module.evaluate_observer_outcome(envelope, required=True).status is ObserverOutcomeStatus.INCONCLUSIVE


def test_async_task_overall_deadline_after_response_is_timed_out(monkeypatch: pytest.MonkeyPatch) -> None:
    invocation = _invocation(_spec(timeout_us=1))
    monkeypatch.setenv("TASK_TOKEN", "opaque-task-secret")

    class Client:
        def stream(self, method: str, url: str, *, headers: dict[str, str]) -> object:
            response = type("Response", (), {"status_code": 200, "iter_bytes": lambda self: iter((_response("SUCCESS"),))})()
            return type("Stream", (), {"__enter__": lambda self: response, "__exit__": lambda self, *args: None})()

        def close(self) -> None:
            pass

    calls = 0

    def clock() -> int:
        nonlocal calls
        calls += 1
        return 0 if calls == 1 else 1_000

    monkeypatch.setattr(async_module.httpx, "Client", lambda **kwargs: Client())
    monkeypatch.setattr(async_module.time, "monotonic_ns", clock)
    envelope = async_module._run_child(invocation, utc_now_us=lambda: 100)
    assert envelope.completeness is ObservationCompleteness.TIMED_OUT
    assert "ASYNC_TASK_OBSERVATION_TIMEOUT" in envelope.reason_codes
    assert async_module.evaluate_observer_outcome(envelope, required=True).status is ObserverOutcomeStatus.INCONCLUSIVE


def test_async_task_request_timeout_is_timed_out(monkeypatch: pytest.MonkeyPatch) -> None:
    invocation = _invocation()
    monkeypatch.setenv("TASK_TOKEN", "opaque-task-secret")

    class Client:
        def stream(self, method: str, url: str, *, headers: dict[str, str]) -> object:
            raise httpx.ReadTimeout("fake timeout")

        def close(self) -> None:
            pass

    monkeypatch.setattr(async_module.httpx, "Client", lambda **kwargs: Client())
    envelope = async_module._run_child(invocation, utc_now_us=lambda: 100)
    assert envelope.completeness is ObservationCompleteness.TIMED_OUT
    assert "ASYNC_TASK_REQUEST_TIMEOUT" in envelope.reason_codes
    assert async_module.evaluate_observer_outcome(envelope, required=True).status is ObserverOutcomeStatus.INCONCLUSIVE


@pytest.mark.parametrize(
    "payload",
    [
        b"\xef\xbb\xbf{}",
        b'{"schema_version":"1","case_tag":"case-1","resource_id":"resource-a","task_id":"task-1","state":"SUCCESS","final_result":null,"extra":1}',
        b'{"schema_version":"1","case_tag":"case-1","resource_id":"resource-a","task_id":"task-1","state":"SUCCESS","final_result":{"value":NaN}}',
        _response("SUCCESS", final_result={"echo": "opaque-task-secret"}),
    ],
)
def test_async_task_rejects_bom_unknown_nonfinite_and_secret_echo(monkeypatch: pytest.MonkeyPatch, payload: bytes) -> None:
    envelope, outcome = _run_fake(monkeypatch, [payload])
    assert outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    assert "ASYNC_TASK_RESPONSE_INVALID" in envelope.reason_codes or "ASYNC_TASK_RESPONSE_LIMIT" in envelope.reason_codes


def test_async_task_parent_environment_and_process_failure_are_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FailedProcess:
        returncode = 7

        def poll(self) -> int:
            return self.returncode

        def wait(self, timeout: float | None = None) -> int:
            return self.returncode

    def popen(command: list[str], *, env: dict[str, str], **kwargs: object) -> FailedProcess:
        captured["command"] = command
        captured["env"] = env
        return FailedProcess()

    monkeypatch.setattr(async_module.subprocess, "Popen", popen)
    spec = _spec()
    result = async_module.run_async_task_observer(spec, _invocation(spec).correlation, ObservationPhase.EVENTUAL, attempt_dir=tmp_path / "attempt", parent_environ=runtime_identity_environment(tmp_path / "var", extra={"TASK_TOKEN": "opaque-task-secret", "OTHER_SECRET": "not-forwarded"}))
    assert result.outcome.status is ObserverOutcomeStatus.EXECUTION_ERROR
    assert result.envelope is None
    assert captured["env"]["TASK_TOKEN"] == "opaque-task-secret"
    assert "OTHER_SECRET" not in captured["env"]
    assert "opaque-task-secret" not in " ".join(captured["command"])
    assert "https://127.0.0.1:8443" not in " ".join(captured["command"])
    assert not list((tmp_path / "attempt").glob("async-task-observer-*.json"))


def test_async_task_poll_interval_is_bounded_and_marker_is_quoted(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = _spec(max_polls=2, poll_interval_us=500_000)
    correlation = Correlation(case_id="case-1", resource_id="resource-a", request_marker="case-1:part")
    invocation = AsyncTaskObserverInvocation(spec=spec, correlation=correlation, phase=ObservationPhase.EVENTUAL)
    assert "%3A" in async_module._request_url(invocation)
    monkeypatch.setenv("TASK_TOKEN", "opaque-task-secret")
    sleeps: list[float] = []

    class Client:
        def __init__(self) -> None:
            self.responses = [_response("NOT_CREATED", task_id=None, case_tag="case-1:part"), _response("NOT_CREATED", task_id=None, case_tag="case-1:part")]

        def stream(self, method: str, url: str, *, headers: dict[str, str]) -> object:
            response = type("Response", (), {"status_code": 200, "iter_bytes": lambda self: iter((self_payload,))})()
            self_payload = self.responses.pop(0)
            response.iter_bytes = lambda: iter((self_payload,))
            return type("Stream", (), {"__enter__": lambda self: response, "__exit__": lambda self, *args: None})()

        def close(self) -> None:
            pass

    monkeypatch.setattr(async_module.httpx, "Client", lambda **kwargs: Client())
    monkeypatch.setattr(async_module.time, "sleep", lambda seconds: sleeps.append(seconds))
    envelope = async_module._run_child(invocation, utc_now_us=lambda: 100)
    assert envelope.completeness is ObservationCompleteness.COMPLETE
    assert sleeps and sleeps[0] <= 0.5


def test_async_task_corrupt_child_output_is_execution_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Process:
        returncode = 0

        def poll(self) -> int:
            return self.returncode

        def wait(self, timeout: float | None = None) -> int:
            return 0

    def popen(command: list[str], **kwargs: object) -> Process:
        output = Path(command[command.index("--output") + 1])
        output.write_bytes(b"not-json")
        return Process()

    monkeypatch.setattr(async_module.subprocess, "Popen", popen)
    spec = _spec()
    result = async_module.run_async_task_observer(spec, _invocation(spec).correlation, ObservationPhase.EVENTUAL, attempt_dir=tmp_path / "attempt", parent_environ=runtime_identity_environment(tmp_path / "var", extra={"TASK_TOKEN": "opaque-task-secret"}))
    assert result.outcome.status is ObserverOutcomeStatus.EXECUTION_ERROR
    assert result.envelope is None


def test_async_task_generic_invocation_is_rejected_and_independent_wire_is_valid() -> None:
    from product.protocols import ObserverInvocation
    spec = _spec()
    correlation = _invocation(spec).correlation
    with pytest.raises(ValueError):
        ObserverInvocation(spec=spec, correlation=correlation, phase=ObservationPhase.EVENTUAL)
    assert AsyncTaskObserverInvocation(spec=spec, correlation=correlation, phase=ObservationPhase.EVENTUAL).phase is ObservationPhase.EVENTUAL
