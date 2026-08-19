from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

import product.backend.infra.observers.azure_queue as queue_module
from product.protocols import (
    AzureQueuePeekLocator,
    Correlation,
    ObservationCompleteness,
    ObservationPhase,
    ObserverBudget,
    ObserverOutcomeStatus,
    ObserverSpec,
    ObserverTarget,
    ObserverType,
    QueuePeekBudget,
)
from product.protocols.observer import OBSERVER_JSON_MAX_BYTES


SAS = "sv=2023-11-03&se=2099-01-01T00%3A00%3A00Z&sp=r&sr=q&sig=opaque-signature"
CORRELATION = Correlation(case_id="case-1", resource_id="resource-a", request_marker="case-1")


def _spec(*, max_messages: int = 8, max_message_bytes: int = 4096, max_total_bytes: int = 8192, max_attempts: int = 1, timeout_us: int = 5_000_000) -> ObserverSpec:
    locator = AzureQueuePeekLocator(
        allow_loopback_http=True,
        service_url="http://127.0.0.1:10000/devstoreaccount1",
        queue_name="queue-test",
        read_only_sas_ref="env:QUEUE_SAS",
        exclusive_test_queue=True,
        allowed_fields=("event_id", "case_tag", "resource_id", "sequence", "event_type", "result"),
        peek_budget=QueuePeekBudget(
            max_messages=max_messages,
            max_message_bytes=max_message_bytes,
            max_total_bytes=max_total_bytes,
            max_attempts=max_attempts,
            per_request_timeout_us=100_000,
            retry_interval_us=0,
        ),
    )
    return ObserverSpec(
        observer_id="queue-observer",
        observer_type=ObserverType.AZURE_QUEUE_PEEK,
        target=ObserverTarget(target_id="queue-target", locator=locator, normalization_id="queue", normalization_version="1.0"),
        phases=(ObservationPhase.EVENTUAL,),
        required=True,
        budget=ObserverBudget(timeout_us=timeout_us, max_rows=max_messages, max_bytes=max_total_bytes),
    )


def _xml(records: list[dict[str, object]]) -> bytes:
    body = []
    for index, record in enumerate(records):
        encoded = base64.b64encode(json.dumps(record, separators=(",", ":")).encode()).decode()
        body.append(
            f"<QueueMessage><MessageId>message-{index}</MessageId>"
            f"<MessageText>{encoded}</MessageText></QueueMessage>"
        )
    return ("<EnumerationResults><QueueMessagesList>" + "".join(body) + "</QueueMessagesList></EnumerationResults>").encode()


def _xml_message_text(text: bytes) -> bytes:
    encoded = base64.b64encode(text).decode()
    return f"<EnumerationResults><QueueMessagesList><QueueMessage><MessageText>{encoded}</MessageText></QueueMessage></QueueMessagesList></EnumerationResults>".encode()


def _record(event_id: str, sequence: int, *, case_tag: str = "case-1", resource_id: str = "resource-a", event_type: str = "TASK_STATE") -> dict[str, object]:
    return {"event_id": event_id, "case_tag": case_tag, "resource_id": resource_id, "sequence": sequence, "event_type": event_type}


class _Response:
    def __init__(self, payload: bytes, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def iter_bytes(self):
        yield self.payload


class _Stream:
    def __init__(self, response: _Response) -> None:
        self.response = response

    def __enter__(self) -> _Response:
        return self.response

    def __exit__(self, *args: object) -> None:
        return None


def _run_fake(monkeypatch: pytest.MonkeyPatch, payloads: list[bytes], *, statuses: list[int] | None = None, spec: ObserverSpec | None = None):
    monkeypatch.setenv("QUEUE_SAS", SAS)
    responses = list(payloads)
    codes = list(statuses or [200] * len(responses))
    calls: list[tuple[str, str, dict[str, str]]] = []

    class Client:
        def stream(self, method: str, url: str, *, headers: dict[str, str]) -> _Stream:
            calls.append((method, url, headers))
            return _Stream(_Response(responses.pop(0), codes.pop(0)))

        def close(self) -> None:
            pass

    monkeypatch.setattr(queue_module.httpx, "Client", lambda **kwargs: Client())
    invocation = queue_module.ObserverInvocation(spec=spec or _spec(), correlation=CORRELATION, phase=ObservationPhase.EVENTUAL)
    envelope = queue_module._run_child(invocation, utc_now_us=lambda: 100)
    return envelope, queue_module.evaluate_observer_outcome(envelope, required=True), calls


def test_queue_peek_success_is_stable_and_only_uses_get_peek(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _xml([_record("b", 2), _record("a", 1), _record("a", 1), _record("other", 3, case_tag="other")])
    first, first_outcome, calls = _run_fake(monkeypatch, [payload])
    second, second_outcome, _ = _run_fake(monkeypatch, [payload])
    assert first.completeness is ObservationCompleteness.COMPLETE
    assert first_outcome.status is ObserverOutcomeStatus.AVAILABLE
    assert second_outcome.status is ObserverOutcomeStatus.AVAILABLE
    assert first.state == second.state
    assert first.state is not None
    assert first.state.canonical_data["matched_count"] == 2
    assert [item["event_id"] for item in first.state.canonical_data["messages"]] == ["a", "b"]
    assert calls[0][0] == "GET"
    assert "peekonly=true" in calls[0][1]
    assert "numofmessages=8" in calls[0][1]
    assert calls[0][1].startswith("http://127.0.0.1:10000/devstoreaccount1/queue-test/messages?")
    assert calls[0][2] == {"x-ms-version": "2023-11-03", "Accept": "application/xml"}
    assert all(word not in queue_module._request_url.__code__.co_consts for word in ("receive", "delete", "clear", "send"))


def test_queue_peek_empty_is_complete_but_limit_is_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    empty, outcome, _ = _run_fake(monkeypatch, [_xml([_record("other", 1, case_tag="other")])])
    assert empty.completeness is ObservationCompleteness.COMPLETE
    assert outcome.status is ObserverOutcomeStatus.AVAILABLE
    assert empty.state is not None and empty.state.canonical_data["matched_count"] == 0
    limited, outcome, _ = _run_fake(monkeypatch, [_xml([_record(str(index), index) for index in range(4)])], spec=_spec(max_messages=4))
    assert limited.completeness is ObservationCompleteness.PARTIAL
    assert limited.reason_codes == (queue_module.AZURE_QUEUE_MESSAGE_LIMIT,)
    assert outcome.status is ObserverOutcomeStatus.INCONCLUSIVE


def test_queue_peek_rejects_conflict_and_correlation(monkeypatch: pytest.MonkeyPatch) -> None:
    conflict = _xml([_record("same", 1), _record("same", 2)])
    envelope, outcome, _ = _run_fake(monkeypatch, [conflict])
    assert envelope.completeness is ObservationCompleteness.PARTIAL
    assert queue_module.AZURE_QUEUE_MESSAGE_CONFLICT in envelope.reason_codes
    assert outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    mismatch = _xml([_record("bad", 1, case_tag="wrong")])
    envelope, outcome, _ = _run_fake(monkeypatch, [mismatch])
    assert outcome.status is ObserverOutcomeStatus.AVAILABLE
    assert envelope.state is not None and envelope.state.canonical_data["matched_count"] == 0


@pytest.mark.parametrize(
    "payload",
    [
        b"\xef\xbb\xbf<EnumerationResults />",
        b"<!DOCTYPE EnumerationResults><EnumerationResults />",
        b"<EnumerationResults><QueueMessagesList><QueueMessage><MessageText>not-base64</MessageText></QueueMessage></QueueMessagesList></EnumerationResults>",
        _xml([{"event_id": "a", "case_tag": "case-1", "resource_id": "resource-a", "sequence": 1, "extra": {"nested": True}}]),
        _xml_message_text(b"not-json"),
    ],
)
def test_queue_peek_rejects_xml_and_json_boundaries(monkeypatch: pytest.MonkeyPatch, payload: bytes) -> None:
    envelope, outcome, _ = _run_fake(monkeypatch, [payload])
    assert outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    assert envelope.completeness in {ObservationCompleteness.PARTIAL, ObservationCompleteness.ERROR}


def test_queue_peek_retries_only_retryable_statuses(monkeypatch: pytest.MonkeyPatch) -> None:
    envelope, outcome, calls = _run_fake(monkeypatch, [b"busy", _xml([_record("a", 1)])], statuses=[429, 200], spec=_spec(max_attempts=2))
    assert outcome.status is ObserverOutcomeStatus.AVAILABLE
    assert envelope.completeness is ObservationCompleteness.COMPLETE
    assert len(calls) == 2
    envelope, outcome, calls = _run_fake(monkeypatch, [b"forbidden", _xml([_record("a", 1)])], statuses=[403, 200], spec=_spec(max_attempts=2))
    assert outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    assert envelope.reason_codes == (queue_module.AZURE_QUEUE_AUTH,)
    assert len(calls) == 1


@pytest.mark.parametrize("value", [SAS, "?" + SAS, "sv=1&se=2&sp=rw&sr=q&sig=x", "sv=1&se=2&sp=r&sr=a&sig=x", "sv=1&se=2&sp=r&sr=q&sig=x&unknown=y", "sv=1&se=2&sp=r&sr=q&sig=x&sig=y", "sv=1&se=2&sp=r&sr=q&sig=x%0A", "sv=1&se=2&sp=r&sr=q&sig=x%09", "sv%0A=1&se=2&sp=r&sr=q&sig=x", "https://secret.example/?x=1"])
def test_queue_sas_boundary_is_strict(value: str) -> None:
    if value in {SAS, "?" + SAS}:
        assert queue_module._parse_sas(value).startswith("sv=")
    else:
        with pytest.raises(ValueError):
            queue_module._parse_sas(value)


def test_queue_process_entry_delegates_to_core(monkeypatch: pytest.MonkeyPatch) -> None:
    import product.backend.infra.observers.azure_queue as process_module

    monkeypatch.setattr(process_module, "child_main", lambda input_path, output_path: 7)
    monkeypatch.setattr(sys, "argv", ["azure_queue_observer_process", "--input", "input.json", "--output", "output.json"])
    assert process_module.main() == 7


def test_queue_sas_and_response_never_enter_state_or_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "sv=secret-value"
    monkeypatch.setenv("QUEUE_SAS", secret)
    invocation = queue_module.ObserverInvocation(spec=_spec(), correlation=CORRELATION, phase=ObservationPhase.EVENTUAL)
    envelope = queue_module._run_child(invocation, utc_now_us=lambda: 100)
    outcome = queue_module.evaluate_observer_outcome(envelope, required=True)
    assert outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    assert secret not in envelope.model_dump_json()


def test_queue_parent_cancel_timeout_crash_and_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = _spec(timeout_us=100_000)

    class Process:
        returncode = None
        def __init__(self) -> None:
            self.killed = False
        def wait(self, timeout: float | None = None) -> int:
            raise subprocess.TimeoutExpired("queue", timeout)
        def kill(self) -> None:
            self.killed = True

    process = Process()
    monkeypatch.setattr(queue_module.subprocess, "Popen", lambda *args, **kwargs: process)
    clock = iter((1_000_000_000, 1_001_000_000, 1_050_000_000, 1_101_000_000))
    monkeypatch.setattr(queue_module.time, "monotonic_ns", lambda: next(clock, 1_101_000_000))
    result = queue_module.run_azure_queue_observer(spec, CORRELATION, ObservationPhase.EVENTUAL, attempt_dir=tmp_path / "timeout", parent_environ={"QUEUE_SAS": SAS}, python_executable="python")
    assert result.envelope is not None and result.envelope.completeness is ObservationCompleteness.TIMED_OUT
    assert result.outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    assert process.killed
    assert not list((tmp_path / "timeout").glob("*"))

    monkeypatch.setattr(queue_module.subprocess, "Popen", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("missing interpreter")))
    crash = queue_module.run_azure_queue_observer(spec, CORRELATION, ObservationPhase.EVENTUAL, attempt_dir=tmp_path / "crash", parent_environ={"QUEUE_SAS": SAS}, python_executable="C:\\missing-python.exe")
    assert crash.envelope is None and crash.outcome.status is ObserverOutcomeStatus.EXECUTION_ERROR


def test_queue_parent_selects_only_referenced_sas_and_keeps_command_secret_free(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class Process:
        returncode = 7
        def wait(self, timeout: float | None = None) -> int:
            return 0

    def fake_popen(command: list[str], **kwargs: object) -> Process:
        captured["command"] = command
        captured["environment"] = kwargs["env"]
        return Process()

    monkeypatch.setattr(queue_module.subprocess, "Popen", fake_popen)
    secret = "opaque-queue-sas"
    result = queue_module.run_azure_queue_observer(
        _spec(), CORRELATION, ObservationPhase.EVENTUAL,
        attempt_dir=tmp_path / "minimal-env",
        parent_environ={"QUEUE_SAS": secret, "UNRELATED_SECRET": "must-not-propagate", "PATH": "C:\\Windows"},
        python_executable="python",
    )
    assert result.envelope is None
    assert result.outcome.status is ObserverOutcomeStatus.EXECUTION_ERROR
    assert captured["environment"]["QUEUE_SAS"] == secret
    assert "UNRELATED_SECRET" not in captured["environment"]
    assert secret not in " ".join(captured["command"])


def test_queue_parent_rejects_corrupt_output_before_acceptance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _assert_parent_rejects_output(tmp_path, monkeypatch, b"{}")


def test_queue_parent_rejects_oversized_output_before_acceptance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _assert_parent_rejects_output(tmp_path, monkeypatch, b"x" * (OBSERVER_JSON_MAX_BYTES + 1))


def _assert_parent_rejects_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: bytes) -> None:
    class Process:
        returncode = 0
        def __init__(self, output: Path) -> None:
            self.output = output
        def wait(self, timeout: float | None = None) -> int:
            self.output.write_bytes(payload)
            return 0

    def fake_popen(command: list[str], **kwargs: object) -> Process:
        output = Path(command[command.index("--output") + 1])
        return Process(output)

    monkeypatch.setattr(queue_module.subprocess, "Popen", fake_popen)
    attempt = tmp_path / "output"
    result = queue_module.run_azure_queue_observer(
        _spec(), CORRELATION, ObservationPhase.EVENTUAL,
        attempt_dir=attempt,
        parent_environ={"QUEUE_SAS": SAS, "PATH": "C:\\Windows"},
        python_executable="python",
    )
    assert result.envelope is None
    assert result.outcome.status is ObserverOutcomeStatus.EXECUTION_ERROR
    assert not list(attempt.glob("*"))


def test_queue_output_binding_rejects_wrong_target(monkeypatch: pytest.MonkeyPatch) -> None:
    envelope, _, _ = _run_fake(monkeypatch, [_xml([_record("a", 1)])])
    invocation = queue_module.ObserverInvocation(spec=_spec(), correlation=CORRELATION, phase=ObservationPhase.EVENTUAL)
    with pytest.raises(ValueError):
        queue_module._validate_output_binding(invocation, envelope.model_copy(update={"target_id": "wrong-target"}))


def test_queue_protocol_scope_is_not_widened() -> None:
    with pytest.raises(ValueError):
        AzureQueuePeekLocator(allow_loopback_http=False, service_url="http://127.0.0.1:10000/devstoreaccount1", queue_name="queue-test", read_only_sas_ref="env:QUEUE_SAS", exclusive_test_queue=True, allowed_fields=("event_id", "case_tag", "resource_id", "sequence"), peek_budget=QueuePeekBudget(max_messages=1, max_message_bytes=100, max_total_bytes=100, max_attempts=1, per_request_timeout_us=1, retry_interval_us=0))
