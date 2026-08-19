# =============================================================================
# Runner 隔离域异步任务状态观察器
#
# 只通过显式 IPv4 origin 和固定 request_marker 路径读取权威任务状态；
# 观察器只解释关联、状态机、预算和完整性，不决定安全结论。
# =============================================================================

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import quote

import httpx

from product.backend.infra.runtime.process_environment import minimal_process_environment
from product.protocols.observer import AsyncTaskApiLocator, AsyncTaskObserverInvocation, AsyncTaskStatus, CausalityStatus, ObservationCompleteness, ObservationEnvelope, ObservationPhase, ObservationProvenance, ObservationWindow, OBSERVER_JSON_MAX_BYTES, ObserverOutcome, ObserverOutcomeStatus, ObserverSpec, ObserverType, ProvenanceType, build_normalized_state, canonical_json_bytes, canonical_sha256, evaluate_observer_outcome, parse_observer_json
from product.protocols.runner import WebTargetDefinition, WebTargetScope
from product.backend.infra.execution.http import WebTargetGuard


ASYNC_TASK_PROCESS_ERROR = "ASYNC_TASK_PROCESS_ERROR"
ASYNC_TASK_UNAVAILABLE = "ASYNC_TASK_UNAVAILABLE"
ASYNC_TASK_UNSUPPORTED = "ASYNC_TASK_UNSUPPORTED"
ASYNC_TASK_HTTP_STATUS = "ASYNC_TASK_HTTP_STATUS"
ASYNC_TASK_REDIRECT = "ASYNC_TASK_REDIRECT"
ASYNC_TASK_RESPONSE_INVALID = "ASYNC_TASK_RESPONSE_INVALID"
ASYNC_TASK_RESPONSE_LIMIT = "ASYNC_TASK_RESPONSE_LIMIT"
ASYNC_TASK_CORRELATION_CONFLICT = "ASYNC_TASK_CORRELATION_CONFLICT"
ASYNC_TASK_STATE_CONFLICT = "ASYNC_TASK_STATE_CONFLICT"
ASYNC_TASK_REQUEST_TIMEOUT = "ASYNC_TASK_REQUEST_TIMEOUT"
ASYNC_TASK_OBSERVATION_TIMEOUT = "ASYNC_TASK_OBSERVATION_TIMEOUT"
ASYNC_TASK_CANCELLED = "ASYNC_TASK_CANCELLED"
_PROCESS_REAP_TIMEOUT_SECONDS = 1.0
_SUPERVISION_SLICE_SECONDS = 0.05
_STATE_ORDER = {
    AsyncTaskStatus.NOT_CREATED: 0,
    AsyncTaskStatus.QUEUED: 1,
    AsyncTaskStatus.RUNNING: 2,
    AsyncTaskStatus.SUCCESS: 3,
    AsyncTaskStatus.FAILED: 3,
    AsyncTaskStatus.TIMED_OUT: 3,
}
_RESPONSE_FIELDS = frozenset({"schema_version", "case_tag", "resource_id", "task_id", "state", "final_result"})


@dataclass(frozen=True)
class AsyncTaskObserverResult:
    envelope: ObservationEnvelope | None
    outcome: ObserverOutcome


def _now_us() -> int:
    return time.time_ns() // 1_000


def _secret_name(spec: ObserverSpec) -> str:
    locator = spec.target.locator
    if not isinstance(locator, AsyncTaskApiLocator):
        raise ValueError("async task observer requires an async task locator")
    return locator.read_only_credential_ref.removeprefix("env:")


def _write_atomic(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _failure_envelope(
    invocation: AsyncTaskObserverInvocation,
    completeness: ObservationCompleteness,
    reason: str,
    started_at_us: int,
    finished_at_us: int,
) -> ObservationEnvelope:
    budget = invocation.spec.budget.timeout_us
    return ObservationEnvelope(
        observer_id=invocation.spec.observer_id,
        observer_type=ObserverType.ASYNC_TASK_STATUS,
        phase=invocation.phase,
        target_id=invocation.spec.target.target_id,
        window=ObservationWindow(
            phase=invocation.phase,
            started_at_us=started_at_us,
            finished_at_us=min(max(finished_at_us, started_at_us), started_at_us + budget),
            timeout_us=budget,
        ),
        correlation=invocation.correlation,
        causality=CausalityStatus.UNVERIFIED,
        completeness=completeness,
        reason_codes=(reason,),
    )


def _reject_nested(value: Any, *, depth: int = 0) -> None:
    if depth > 4:
        raise ValueError("async task response is too deeply nested")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 64:
                raise ValueError("async task response key is invalid")
            _reject_nested(item, depth=depth + 1)
    elif isinstance(value, list):
        if len(value) > 64:
            raise ValueError("async task response array is too large")
        for item in value:
            _reject_nested(item, depth=depth + 1)
    elif isinstance(value, str) and len(value) > 4096:
        raise ValueError("async task response string is too large")


def _parse_task_response(payload: bytes, *, known_secrets: tuple[str, ...]) -> dict[str, Any]:
    if len(payload) > OBSERVER_JSON_MAX_BYTES or payload.startswith(b"\xef\xbb\xbf"):
        raise ValueError(ASYNC_TASK_RESPONSE_LIMIT)

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(ASYNC_TASK_RESPONSE_INVALID)
            result[key] = value
        return result

    def reject_nonfinite(value: str) -> None:
        raise ValueError(ASYNC_TASK_RESPONSE_INVALID)

    parsed = json.loads(payload.decode("utf-8"), object_pairs_hook=reject_duplicates, parse_constant=reject_nonfinite)
    if not isinstance(parsed, dict) or set(parsed) != _RESPONSE_FIELDS:
        raise ValueError(ASYNC_TASK_RESPONSE_INVALID)
    if parsed["schema_version"] != "1" or not isinstance(parsed["case_tag"], str) or not isinstance(parsed["resource_id"], str):
        raise ValueError(ASYNC_TASK_RESPONSE_INVALID)
    if not isinstance(parsed["state"], str) or parsed["state"] not in {state.value for state in AsyncTaskStatus}:
        raise ValueError(ASYNC_TASK_RESPONSE_INVALID)
    task_id = parsed["task_id"]
    if task_id is not None and (not isinstance(task_id, str) or not task_id or len(task_id) > 128):
        raise ValueError(ASYNC_TASK_RESPONSE_INVALID)
    final_result = parsed["final_result"]
    if final_result is not None and not isinstance(final_result, dict):
        raise ValueError(ASYNC_TASK_RESPONSE_INVALID)
    _reject_nested(parsed, depth=0)
    if any(secret and secret in json.dumps(parsed, ensure_ascii=False, separators=(",", ":")) for secret in known_secrets):
        raise ValueError(ASYNC_TASK_RESPONSE_INVALID)
    state = AsyncTaskStatus(parsed["state"])
    if state is AsyncTaskStatus.NOT_CREATED and (task_id is not None or final_result is not None):
        raise ValueError(ASYNC_TASK_RESPONSE_INVALID)
    if state in {AsyncTaskStatus.QUEUED, AsyncTaskStatus.RUNNING} and (task_id is None or final_result is not None):
        raise ValueError(ASYNC_TASK_RESPONSE_INVALID)
    if state in {AsyncTaskStatus.SUCCESS, AsyncTaskStatus.FAILED, AsyncTaskStatus.TIMED_OUT} and task_id is None:
        raise ValueError(ASYNC_TASK_RESPONSE_INVALID)
    return parsed


def _build_scope(locator: AsyncTaskApiLocator, *, budget_bytes: int, timeout_us: int) -> WebTargetGuard:
    parsed = locator.base_url.split("://", 1)[1]
    host, raw_port = parsed.split(":", 1)
    port = int(raw_port)
    scope = WebTargetScope(
        base_url=locator.base_url,
        allowed_origins=(locator.base_url,),
        allowed_hosts=(host,),
        allowed_ports=(port,),
        allow_private_network=locator.allow_private_network or locator.allow_loopback_http,
        timeout_seconds=min(timeout_us / 1_000_000, 30),
        max_requests=locator.poll_budget.max_polls,
        max_response_bytes=min(budget_bytes, locator.poll_budget.max_response_bytes),
    )
    return WebTargetGuard(WebTargetDefinition(scope=scope, reset_path="/reset"))


def _request_url(invocation: AsyncTaskObserverInvocation) -> str:
    locator = invocation.spec.target.locator
    assert isinstance(locator, AsyncTaskApiLocator)
    path = locator.relative_path_template.replace("{request_marker}", quote(invocation.correlation.request_marker, safe=""))
    return _build_scope(locator, budget_bytes=invocation.spec.budget.max_bytes, timeout_us=locator.poll_budget.per_request_timeout_us).authorize_path(path).url


def _poll_once(
    invocation: AsyncTaskObserverInvocation,
    client: httpx.Client,
    *,
    credential: str,
) -> tuple[dict[str, Any] | None, str | None, int]:
    locator = invocation.spec.target.locator
    assert isinstance(locator, AsyncTaskApiLocator)
    url = _request_url(invocation)
    limit = locator.poll_budget.max_response_bytes
    try:
        with client.stream("GET", url, headers={"Authorization": f"Bearer {credential}"}) as response:
            if 300 <= response.status_code < 400:
                return None, ASYNC_TASK_REDIRECT, 0
            if response.status_code != 200:
                return None, ASYNC_TASK_HTTP_STATUS, 0
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > limit:
                    return None, ASYNC_TASK_RESPONSE_LIMIT, len(content)
    except httpx.TimeoutException:
        return None, ASYNC_TASK_REQUEST_TIMEOUT, 0
    except httpx.RequestError:
        return None, ASYNC_TASK_UNAVAILABLE, 0
    try:
        return _parse_task_response(bytes(content), known_secrets=(credential,)), None, len(content)
    except (UnicodeError, ValueError) as exc:
        reason = str(exc)
        return None, reason if reason.startswith("ASYNC_TASK_") else ASYNC_TASK_RESPONSE_INVALID, len(content)


def _run_child(invocation: AsyncTaskObserverInvocation, *, utc_now_us: Callable[[], int]) -> ObservationEnvelope:
    started_at_us = utc_now_us()
    locator = invocation.spec.target.locator
    if not isinstance(locator, AsyncTaskApiLocator):
        return _failure_envelope(invocation, ObservationCompleteness.UNSUPPORTED, ASYNC_TASK_UNSUPPORTED, started_at_us, utc_now_us())
    credential = os.environ.get(_secret_name(invocation.spec))
    if not credential:
        return _failure_envelope(invocation, ObservationCompleteness.MISSING, ASYNC_TASK_UNAVAILABLE, started_at_us, utc_now_us())
    deadline_ns = time.monotonic_ns() + invocation.spec.budget.timeout_us * 1_000
    attempt_dir = Path(os.environ.get("JIEJIAN_ATTEMPT_DIR", "."))
    if (attempt_dir / "cancel.requested").is_file():
        return _failure_envelope(invocation, ObservationCompleteness.PARTIAL, ASYNC_TASK_CANCELLED, started_at_us, utc_now_us())
    try:
        _request_url(invocation)
        client = httpx.Client(follow_redirects=False, trust_env=False, timeout=locator.poll_budget.per_request_timeout_us / 1_000_000)
    except Exception:
        return _failure_envelope(invocation, ObservationCompleteness.UNSUPPORTED, ASYNC_TASK_UNSUPPORTED, started_at_us, utc_now_us())
    responses: list[str] = []
    states: list[AsyncTaskStatus] = []
    task_id: str | None = None
    final_result: dict[str, Any] | None = None
    previous_order = -1
    terminal: AsyncTaskStatus | None = None
    last_response: dict[str, Any] | None = None
    reason: str | None = None
    total_response_bytes = 0
    try:
        for poll_number in range(1, locator.poll_budget.max_polls + 1):
            if (attempt_dir / "cancel.requested").is_file():
                reason = ASYNC_TASK_CANCELLED
                break
            if time.monotonic_ns() >= deadline_ns:
                reason = ASYNC_TASK_OBSERVATION_TIMEOUT
                break
            response, response_reason, response_bytes = _poll_once(invocation, client, credential=credential)
            if total_response_bytes + response_bytes > invocation.spec.budget.max_bytes:
                reason = ASYNC_TASK_RESPONSE_LIMIT
                break
            total_response_bytes += response_bytes
            if response_reason is not None:
                reason = response_reason
                break
            assert response is not None
            if time.monotonic_ns() >= deadline_ns:
                reason = ASYNC_TASK_OBSERVATION_TIMEOUT
                break
            if response["case_tag"] != invocation.correlation.request_marker or response["resource_id"] != invocation.correlation.resource_id:
                reason = ASYNC_TASK_CORRELATION_CONFLICT
                break
            current = AsyncTaskStatus(response["state"])
            current_task = response["task_id"]
            if task_id is not None and current_task != task_id:
                reason = ASYNC_TASK_STATE_CONFLICT
                break
            if current_task is not None:
                task_id = current_task
            order = _STATE_ORDER[current]
            if terminal is not None and current is not terminal:
                reason = ASYNC_TASK_STATE_CONFLICT
                break
            if terminal is None and order < previous_order:
                reason = ASYNC_TASK_STATE_CONFLICT
                break
            previous_order = order
            if terminal is None and order == 3:
                terminal = current
                final_result = response["final_result"]
            states.append(current)
            response_hash = hashlib.sha256(canonical_json_bytes(response)).hexdigest()
            responses.append(response_hash)
            last_response = response
            if terminal is not None:
                break
            if poll_number < locator.poll_budget.max_polls and locator.poll_budget.poll_interval_us:
                remaining = max(0, deadline_ns - time.monotonic_ns()) / 1_000_000_000
                time.sleep(min(locator.poll_budget.poll_interval_us / 1_000_000, remaining))
        if reason is None and terminal is None:
            if states and all(state is AsyncTaskStatus.NOT_CREATED for state in states):
                terminal = AsyncTaskStatus.NOT_CREATED
            elif states:
                reason = ASYNC_TASK_OBSERVATION_TIMEOUT
            else:
                reason = ASYNC_TASK_OBSERVATION_TIMEOUT
    finally:
        client.close()
    if reason is not None:
        completeness = ObservationCompleteness.TIMED_OUT if reason in {ASYNC_TASK_OBSERVATION_TIMEOUT, ASYNC_TASK_REQUEST_TIMEOUT} else ObservationCompleteness.PARTIAL
        return _failure_envelope(invocation, completeness, reason, started_at_us, utc_now_us())
    if terminal is None or last_response is None:
        return _failure_envelope(invocation, ObservationCompleteness.MISSING, ASYNC_TASK_UNAVAILABLE, started_at_us, utc_now_us())
    payload = {
        "task_id": task_id,
        "task_state": terminal.value,
        "final_result": final_result,
        "polls_used": len(states),
        "total_response_bytes": total_response_bytes,
        "states_seen": [state.value for state in states],
    }
    try:
        state = build_normalized_state(payload, known_secrets=(credential,))
    except ValueError:
        return _failure_envelope(invocation, ObservationCompleteness.PARTIAL, ASYNC_TASK_RESPONSE_INVALID, started_at_us, utc_now_us())
    if state.byte_count > invocation.spec.budget.max_bytes:
        return _failure_envelope(invocation, ObservationCompleteness.PARTIAL, ASYNC_TASK_RESPONSE_LIMIT, started_at_us, utc_now_us())
    return ObservationEnvelope(
        observer_id=invocation.spec.observer_id,
        observer_type=ObserverType.ASYNC_TASK_STATUS,
        phase=invocation.phase,
        target_id=invocation.spec.target.target_id,
        window=ObservationWindow(
            phase=invocation.phase,
            started_at_us=started_at_us,
            finished_at_us=min(utc_now_us(), started_at_us + invocation.spec.budget.timeout_us),
            timeout_us=invocation.spec.budget.timeout_us,
        ),
        correlation=invocation.correlation,
        causality=CausalityStatus.CORRELATED,
        completeness=ObservationCompleteness.COMPLETE,
        state=state,
        provenance=ObservationProvenance(
            provenance_type=ProvenanceType.ASYNC_TASK_API,
            adapter_version="async-task-observer-1",
            target_id=invocation.spec.target.target_id,
            source_sha256=canonical_sha256(responses),
        ),
    )


def child_main(input_path: str, output_path: str) -> int:
    try:
        input_file = Path(input_path)
        if input_file.stat().st_size > OBSERVER_JSON_MAX_BYTES:
            return 3
        invocation = parse_observer_json(input_file.read_bytes(), AsyncTaskObserverInvocation)
        envelope = _run_child(invocation, utc_now_us=_now_us)
        _write_atomic(Path(output_path), envelope.model_dump_json().encode("utf-8"))
        return 0
    except Exception:
        return 3


def _execution_error(spec: ObserverSpec) -> ObserverOutcome:
    return ObserverOutcome(observer_id=spec.observer_id, required=spec.required, status=ObserverOutcomeStatus.EXECUTION_ERROR, reason_codes=(ASYNC_TASK_PROCESS_ERROR,))


def _validate_output_binding(invocation: AsyncTaskObserverInvocation, envelope: ObservationEnvelope) -> None:
    if envelope.observer_id != invocation.spec.observer_id or envelope.observer_type is not ObserverType.ASYNC_TASK_STATUS:
        raise ValueError("async task output binding mismatch")
    if envelope.phase is not invocation.phase or envelope.target_id != invocation.spec.target.target_id or envelope.correlation != invocation.correlation:
        raise ValueError("async task output correlation mismatch")
    if envelope.window.phase is not invocation.phase or envelope.window.timeout_us != invocation.spec.budget.timeout_us:
        raise ValueError("async task output window mismatch")
    if envelope.provenance is not None and envelope.provenance.target_id != invocation.spec.target.target_id:
        raise ValueError("async task output provenance mismatch")


def run_async_task_observer(
    spec: ObserverSpec,
    correlation,
    phase: ObservationPhase,
    *,
    attempt_dir: Path,
    parent_environ: Mapping[str, str] | None = None,
    python_executable: str | None = None,
) -> AsyncTaskObserverResult:
    """在隔离子进程中轮询异步任务状态，并返回与 case/phase 绑定的观察结果。"""

    invocation = AsyncTaskObserverInvocation(spec=spec, correlation=correlation, phase=phase)
    attempt_root = attempt_dir.resolve()
    attempt_root.mkdir(parents=True, exist_ok=True)
    input_path = attempt_root / "async-task-observer-input.json"
    output_path = attempt_root / "async-task-observer-output.json"
    temporary_paths = (input_path.with_name(f".{input_path.name}.tmp"), output_path.with_name(f".{output_path.name}.tmp"))
    started_at_us = _now_us()
    deadline_ns = time.monotonic_ns() + spec.budget.timeout_us * 1_000
    try:
        source_name = _secret_name(spec)
        environment = minimal_process_environment(parent_environ if parent_environ is not None else os.environ, secret_names=(source_name,))
        environment["JIEJIAN_ATTEMPT_DIR"] = str(attempt_root)
        _write_atomic(input_path, invocation.model_dump_json().encode("utf-8"))
        command = [python_executable or sys.executable, "-B", "-m", "product.backend.infra.observers.async_task", "--input", str(input_path), "--output", str(output_path)]
        try:
            process = subprocess.Popen(command, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            return AsyncTaskObserverResult(None, _execution_error(spec))
        try:
            while True:
                if (attempt_root / "cancel.requested").is_file():
                    terminator = getattr(process, "terminate", process.kill)
                    terminator()
                    try:
                        process.wait(timeout=_PROCESS_REAP_TIMEOUT_SECONDS)
                    except subprocess.TimeoutExpired:
                        try:
                            process.kill()
                            process.wait(timeout=_PROCESS_REAP_TIMEOUT_SECONDS)
                        except subprocess.TimeoutExpired:
                            pass
                    envelope = _failure_envelope(invocation, ObservationCompleteness.PARTIAL, ASYNC_TASK_CANCELLED, started_at_us, _now_us())
                    return AsyncTaskObserverResult(envelope, evaluate_observer_outcome(envelope, required=spec.required))
                remaining = (deadline_ns - time.monotonic_ns()) / 1_000_000_000
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, 0)
                try:
                    process.wait(timeout=min(remaining, _SUPERVISION_SLICE_SECONDS))
                    break
                except subprocess.TimeoutExpired:
                    continue
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=_PROCESS_REAP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                pass
            envelope = _failure_envelope(invocation, ObservationCompleteness.TIMED_OUT, ASYNC_TASK_OBSERVATION_TIMEOUT, started_at_us, _now_us())
            return AsyncTaskObserverResult(envelope, evaluate_observer_outcome(envelope, required=spec.required))
        if process.returncode != 0 or not output_path.is_file():
            return AsyncTaskObserverResult(None, _execution_error(spec))
        if output_path.stat().st_size > OBSERVER_JSON_MAX_BYTES:
            return AsyncTaskObserverResult(None, _execution_error(spec))
        try:
            envelope = parse_observer_json(output_path.read_bytes(), ObservationEnvelope, known_secrets=tuple(value for key, value in environment.items() if key == source_name and value))
            _validate_output_binding(invocation, envelope)
        except (OSError, ValueError):
            return AsyncTaskObserverResult(None, _execution_error(spec))
        return AsyncTaskObserverResult(envelope, evaluate_observer_outcome(envelope, required=spec.required))
    finally:
        for path in (input_path, output_path, *temporary_paths):
            path.unlink(missing_ok=True)

import argparse


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    return child_main(args.input, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
