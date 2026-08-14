# =============================================================================
# Runner 隔离域 Azure Queue Peek 观察器
#
# 仅访问固定 Queue REST Peek 窗口；SAS、响应原文和服务定位不进入观察工件。
# =============================================================================

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import unquote

import httpx

from ..execution.process_environment import minimal_process_environment
from ..protocols.observer_v2 import (
    AzureQueuePeekLocatorV2,
    CausalityStatus,
    CorrelationV2,
    ObservationCompleteness,
    ObservationEnvelopeV2,
    ObservationPhase,
    ObservationProvenanceV2,
    ObservationWindowV2,
    OBSERVER_JSON_MAX_BYTES,
    ObserverInvocationV2,
    ObserverOutcomeStatus,
    ObserverOutcomeV2,
    ObserverSpecV2,
    ObserverType,
    ProvenanceType,
    build_normalized_state,
    canonical_json_bytes,
    canonical_sha256,
    evaluate_observer_outcome,
    parse_observer_json,
)


AZURE_QUEUE_ADAPTER_VERSION = "azure-queue-peek-2023-11-03"
AZURE_QUEUE_PROCESS_ERROR = "AZURE_QUEUE_PROCESS_ERROR"
AZURE_QUEUE_UNSUPPORTED = "AZURE_QUEUE_UNSUPPORTED"
AZURE_QUEUE_SAS_INVALID = "AZURE_QUEUE_SAS_INVALID"
AZURE_QUEUE_UNAVAILABLE = "AZURE_QUEUE_UNAVAILABLE"
AZURE_QUEUE_AUTH = "AZURE_QUEUE_AUTH"
AZURE_QUEUE_RESOURCE_MISSING = "AZURE_QUEUE_RESOURCE_MISSING"
AZURE_QUEUE_THROTTLED = "AZURE_QUEUE_THROTTLED"
AZURE_QUEUE_HTTP_ERROR = "AZURE_QUEUE_HTTP_ERROR"
AZURE_QUEUE_REDIRECT = "AZURE_QUEUE_REDIRECT"
AZURE_QUEUE_REQUEST_TIMEOUT = "AZURE_QUEUE_REQUEST_TIMEOUT"
AZURE_QUEUE_OBSERVATION_TIMEOUT = "AZURE_QUEUE_OBSERVATION_TIMEOUT"
AZURE_QUEUE_CANCELLED = "AZURE_QUEUE_CANCELLED"
AZURE_QUEUE_RESPONSE_LIMIT = "AZURE_QUEUE_RESPONSE_LIMIT"
AZURE_QUEUE_MESSAGE_LIMIT = "AZURE_QUEUE_MESSAGE_LIMIT"
AZURE_QUEUE_MESSAGE_BYTES = "AZURE_QUEUE_MESSAGE_BYTES"
AZURE_QUEUE_RESPONSE_INVALID = "AZURE_QUEUE_RESPONSE_INVALID"
AZURE_QUEUE_MESSAGE_CONFLICT = "AZURE_QUEUE_MESSAGE_CONFLICT"
AZURE_QUEUE_CORRELATION_CONFLICT = "AZURE_QUEUE_CORRELATION_CONFLICT"

_ALLOWED_SAS_KEYS = frozenset({"sv", "st", "se", "sp", "sr", "sig", "spr", "sip", "si"})
_REQUIRED_SAS_KEYS = frozenset({"sv", "se", "sp", "sr", "sig"})
_SECRET_MAX_BYTES = 8192
_TEXT_MAX_BYTES = 1024
_SAS_CONTROL = re.compile(r"[\x00-\x20\x7f]")
_PROCESS_REAP_TIMEOUT_SECONDS = 1.0
_SUPERVISION_SLICE_SECONDS = 0.05
_XML_CHUNK_BYTES = 16_384


@dataclass(frozen=True)
class QueueObserverResult:
    envelope: ObservationEnvelopeV2 | None
    outcome: ObserverOutcomeV2


def _now_us() -> int:
    return time.time_ns() // 1_000


def _secret_name(spec: ObserverSpecV2) -> str:
    locator = spec.target.locator
    if not isinstance(locator, AzureQueuePeekLocatorV2):
        raise ValueError("azure queue observer requires a queue locator")
    return locator.read_only_sas_ref.removeprefix("env:")


def _write_atomic(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _failure_envelope(
    invocation: ObserverInvocationV2,
    completeness: ObservationCompleteness,
    reason: str,
    started_at_us: int,
    finished_at_us: int,
    *,
    state: Mapping[str, Any] | None = None,
    source_sha256: str | None = None,
) -> ObservationEnvelopeV2:
    budget = invocation.spec.budget.timeout_us
    normalized_state = None
    provenance = None
    if state is not None and completeness is ObservationCompleteness.PARTIAL:
        try:
            normalized_state = build_normalized_state(state)
            provenance = ObservationProvenanceV2(
                provenance_type=ProvenanceType.AZURE_QUEUE_PEEK,
                adapter_version=AZURE_QUEUE_ADAPTER_VERSION,
                target_id=invocation.spec.target.target_id,
                source_sha256=source_sha256 or canonical_sha256(state),
            )
        except ValueError:
            normalized_state = None
            provenance = None
    return ObservationEnvelopeV2(
        observer_id=invocation.spec.observer_id,
        observer_type=invocation.spec.observer_type,
        phase=invocation.phase,
        target_id=invocation.spec.target.target_id,
        window=ObservationWindowV2(
            phase=invocation.phase,
            started_at_us=started_at_us,
            finished_at_us=min(max(finished_at_us, started_at_us), started_at_us + budget),
            timeout_us=budget,
        ),
        correlation=invocation.correlation,
        causality=CausalityStatus.CORRELATED if normalized_state is not None else CausalityStatus.UNVERIFIED,
        completeness=completeness,
        state=normalized_state,
        provenance=provenance,
        reason_codes=(reason,),
    )


def _execution_error(spec: ObserverSpecV2) -> ObserverOutcomeV2:
    return ObserverOutcomeV2(
        observer_id=spec.observer_id,
        required=spec.required,
        status=ObserverOutcomeStatus.EXECUTION_ERROR,
        reason_codes=(AZURE_QUEUE_PROCESS_ERROR,),
    )


def _parse_sas(value: str) -> str:
    if len(value.encode("utf-8")) > _SECRET_MAX_BYTES or _SAS_CONTROL.search(value):
        raise ValueError(AZURE_QUEUE_SAS_INVALID)
    normalized = value[1:] if value.startswith("?") else value
    if not normalized or "?" in normalized or "#" in normalized:
        raise ValueError(AZURE_QUEUE_SAS_INVALID)
    values: dict[str, str] = {}
    for part in normalized.split("&"):
        if not part or part.count("=") != 1:
            raise ValueError(AZURE_QUEUE_SAS_INVALID)
        key, raw_value = part.split("=", 1)
        key = unquote(key)
        decoded = unquote(raw_value)
        if (
            _SAS_CONTROL.search(key)
            or _SAS_CONTROL.search(decoded)
            or key in values
            or key not in _ALLOWED_SAS_KEYS
            or not decoded
        ):
            raise ValueError(AZURE_QUEUE_SAS_INVALID)
        values[key] = decoded
    if not _REQUIRED_SAS_KEYS.issubset(values) or values.get("sr") != "q" or values.get("sp") != "r":
        raise ValueError(AZURE_QUEUE_SAS_INVALID)
    return normalized


def _tag(element: ET.Element, name: str) -> str | None:
    return next((child.text for child in element if child.tag.rsplit("}", 1)[-1] == name), None)


def _reject_nonfinite(value: str) -> None:
    raise ValueError(AZURE_QUEUE_RESPONSE_INVALID)


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(AZURE_QUEUE_RESPONSE_INVALID)
        result[key] = value
    return result


def _parse_message_json(
    payload: bytes,
    *,
    allowed_fields: tuple[str, ...],
    known_secrets: tuple[str, ...],
) -> dict[str, Any]:
    if len(payload) > OBSERVER_JSON_MAX_BYTES or payload.startswith(b"\xef\xbb\xbf"):
        raise ValueError(AZURE_QUEUE_RESPONSE_LIMIT)
    parsed = json.loads(
        payload.decode("utf-8"),
        object_pairs_hook=_reject_duplicate_pairs,
        parse_constant=_reject_nonfinite,
    )
    if not isinstance(parsed, dict) or not set(parsed).issubset(allowed_fields):
        raise ValueError(AZURE_QUEUE_RESPONSE_INVALID)
    required = {"event_id", "case_tag", "resource_id", "sequence"}
    if not required.issubset(parsed):
        raise ValueError(AZURE_QUEUE_RESPONSE_INVALID)
    for key in required - {"sequence"}:
        if not isinstance(parsed[key], str) or not parsed[key] or len(parsed[key].encode("utf-8")) > _TEXT_MAX_BYTES:
            raise ValueError(AZURE_QUEUE_RESPONSE_INVALID)
    if isinstance(parsed["sequence"], bool) or not isinstance(parsed["sequence"], int) or parsed["sequence"] < 0:
        raise ValueError(AZURE_QUEUE_RESPONSE_INVALID)
    for key, value in parsed.items():
        if key == "sequence":
            continue
        if isinstance(value, (dict, list)) or not isinstance(value, (str, int, float, bool)):
            raise ValueError(AZURE_QUEUE_RESPONSE_INVALID)
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(AZURE_QUEUE_RESPONSE_INVALID)
        if isinstance(value, str) and len(value.encode("utf-8")) > _TEXT_MAX_BYTES:
            raise ValueError(AZURE_QUEUE_RESPONSE_LIMIT)
    if any(secret and secret in json.dumps(parsed, ensure_ascii=False, separators=(",", ":")) for secret in known_secrets):
        raise ValueError(AZURE_QUEUE_RESPONSE_INVALID)
    return {key: parsed[key] for key in sorted(parsed)}


def _read_response(response: Any, locator: AzureQueuePeekLocatorV2, *, known_secrets: tuple[str, ...]) -> tuple[list[dict[str, Any]] | None, str | None, int]:
    if response.status_code in {401, 403}:
        return None, AZURE_QUEUE_AUTH, 0
    if response.status_code == 404:
        return None, AZURE_QUEUE_RESOURCE_MISSING, 0
    if response.status_code == 408:
        return None, AZURE_QUEUE_REQUEST_TIMEOUT, 0
    if response.status_code == 429:
        return None, AZURE_QUEUE_THROTTLED, 0
    if 500 <= response.status_code <= 599:
        return None, AZURE_QUEUE_UNAVAILABLE, 0
    if 300 <= response.status_code <= 399:
        return None, AZURE_QUEUE_REDIRECT, 0
    if response.status_code != 200:
        return None, AZURE_QUEUE_HTTP_ERROR, 0
    raw = bytearray()
    try:
        for chunk in response.iter_bytes():
            if not isinstance(chunk, bytes):
                raise ValueError(AZURE_QUEUE_RESPONSE_INVALID)
            if len(raw) + len(chunk) > min(locator.peek_budget.max_total_bytes, OBSERVER_JSON_MAX_BYTES):
                return None, AZURE_QUEUE_RESPONSE_LIMIT, len(raw) + len(chunk)
            raw.extend(chunk)
    except UnicodeError:
        return None, AZURE_QUEUE_RESPONSE_INVALID, len(raw)
    if not raw or raw.startswith(b"\xef\xbb\xbf") or b"<!" in raw:
        return None, AZURE_QUEUE_RESPONSE_INVALID, len(raw)
    try:
        root = ET.fromstring(bytes(raw))
        messages = [element for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "QueueMessage"]
        records: list[dict[str, Any]] = []
        total_message_bytes = 0
        for message in messages:
            encoded = _tag(message, "MessageText")
            if encoded is None:
                raise ValueError(AZURE_QUEUE_RESPONSE_INVALID)
            try:
                decoded = base64.b64decode(encoded.encode("ascii"), validate=True)
            except (ValueError, UnicodeError):
                raise ValueError(AZURE_QUEUE_RESPONSE_INVALID) from None
            if len(decoded) > locator.peek_budget.max_message_bytes:
                return None, AZURE_QUEUE_MESSAGE_BYTES, len(raw)
            total_message_bytes += len(decoded)
            if total_message_bytes > locator.peek_budget.max_total_bytes:
                return None, AZURE_QUEUE_MESSAGE_BYTES, len(raw)
            records.append(_parse_message_json(decoded, allowed_fields=locator.allowed_fields, known_secrets=known_secrets))
        if len(records) > locator.peek_budget.max_messages:
            return records[: locator.peek_budget.max_messages], AZURE_QUEUE_MESSAGE_LIMIT, len(raw)
        return records, (AZURE_QUEUE_MESSAGE_LIMIT if len(records) == locator.peek_budget.max_messages else None), len(raw)
    except (ET.ParseError, UnicodeError, ValueError) as exc:
        reason = str(exc)
        return None, reason if reason.startswith("AZURE_QUEUE_") else AZURE_QUEUE_RESPONSE_INVALID, len(raw)


def _request_url(invocation: ObserverInvocationV2, sas: str) -> str:
    locator = invocation.spec.target.locator
    assert isinstance(locator, AzureQueuePeekLocatorV2)
    return f"{locator.service_url}/{locator.queue_name}/messages?{sas}&peekonly=true&numofmessages={locator.peek_budget.max_messages}"


def _run_child(invocation: ObserverInvocationV2, *, utc_now_us: Callable[[], int]) -> ObservationEnvelopeV2:
    started_at_us = utc_now_us()
    locator = invocation.spec.target.locator
    if invocation.spec.observer_type is not ObserverType.AZURE_QUEUE_PEEK or not isinstance(locator, AzureQueuePeekLocatorV2):
        return _failure_envelope(invocation, ObservationCompleteness.UNSUPPORTED, AZURE_QUEUE_UNSUPPORTED, started_at_us, utc_now_us())
    secret_name = _secret_name(invocation.spec)
    sas_value = os.environ.get(secret_name)
    if not sas_value:
        return _failure_envelope(invocation, ObservationCompleteness.MISSING, AZURE_QUEUE_SAS_INVALID, started_at_us, utc_now_us())
    try:
        sas = _parse_sas(sas_value)
    except ValueError:
        return _failure_envelope(invocation, ObservationCompleteness.UNSUPPORTED, AZURE_QUEUE_SAS_INVALID, started_at_us, utc_now_us())
    attempt_dir = Path(os.environ.get("JIEJIAN_ATTEMPT_DIR", "."))
    if (attempt_dir / "cancel.requested").is_file():
        return _failure_envelope(invocation, ObservationCompleteness.PARTIAL, AZURE_QUEUE_CANCELLED, started_at_us, utc_now_us())
    deadline_ns = time.monotonic_ns() + invocation.spec.budget.timeout_us * 1_000
    url = _request_url(invocation, sas)
    try:
        client = httpx.Client(follow_redirects=False, trust_env=False, timeout=locator.peek_budget.per_request_timeout_us / 1_000_000)
    except Exception:
        return _failure_envelope(invocation, ObservationCompleteness.UNSUPPORTED, AZURE_QUEUE_UNSUPPORTED, started_at_us, utc_now_us())
    records: list[dict[str, Any]] | None = None
    reason: str | None = None
    total_response_bytes = 0
    try:
        for attempt in range(locator.peek_budget.max_attempts):
            if time.monotonic_ns() >= deadline_ns:
                reason = AZURE_QUEUE_OBSERVATION_TIMEOUT
                break
            try:
                with client.stream(
                    "GET",
                    url,
                    headers={"x-ms-version": "2023-11-03", "Accept": "application/xml"},
                ) as response:
                    records, reason, response_bytes = _read_response(response, locator, known_secrets=(sas_value,))
                    total_response_bytes += response_bytes
            except httpx.TimeoutException:
                records, reason = None, AZURE_QUEUE_REQUEST_TIMEOUT
            except httpx.RequestError:
                records, reason = None, AZURE_QUEUE_UNAVAILABLE
            if total_response_bytes > invocation.spec.budget.max_bytes:
                records, reason = None, AZURE_QUEUE_RESPONSE_LIMIT
            if reason is None or reason not in {
                AZURE_QUEUE_REQUEST_TIMEOUT,
                AZURE_QUEUE_THROTTLED,
                AZURE_QUEUE_UNAVAILABLE,
            } or attempt + 1 >= locator.peek_budget.max_attempts:
                break
            remaining = max(0, deadline_ns - time.monotonic_ns()) / 1_000_000_000
            time.sleep(min(locator.peek_budget.retry_interval_us / 1_000_000, remaining))
        if time.monotonic_ns() >= deadline_ns and reason is None:
            reason = AZURE_QUEUE_OBSERVATION_TIMEOUT
    finally:
        client.close()
    if reason is not None and records is None:
        completeness = ObservationCompleteness.TIMED_OUT if reason in {AZURE_QUEUE_REQUEST_TIMEOUT, AZURE_QUEUE_OBSERVATION_TIMEOUT} else ObservationCompleteness.PARTIAL
        return _failure_envelope(invocation, completeness, reason, started_at_us, utc_now_us())
    assert records is not None
    if total_response_bytes > invocation.spec.budget.max_bytes:
        return _failure_envelope(invocation, ObservationCompleteness.PARTIAL, AZURE_QUEUE_RESPONSE_LIMIT, started_at_us, utc_now_us())
    by_event: dict[str, bytes] = {}
    matched: list[dict[str, Any]] = []
    conflict = False
    for record in records:
        record_bytes = canonical_json_bytes(record)
        previous = by_event.get(record["event_id"])
        if previous is not None and previous != record_bytes:
            conflict = True
        elif previous is None:
            by_event[record["event_id"]] = record_bytes
        if record["case_tag"] == invocation.correlation.request_marker and record["resource_id"] == invocation.correlation.resource_id:
            if previous is None:
                matched.append(record)
    matched.sort(key=lambda item: (item["sequence"], item["event_id"]))
    state_payload = {
        "messages": matched,
        "scanned_count": len(records),
        "matched_count": len(matched),
        "window_complete": not reason and not conflict,
    }
    state_hash = canonical_sha256(state_payload)
    if conflict:
        return _failure_envelope(invocation, ObservationCompleteness.PARTIAL, AZURE_QUEUE_MESSAGE_CONFLICT, started_at_us, utc_now_us(), state=state_payload, source_sha256=state_hash)
    if reason == AZURE_QUEUE_MESSAGE_LIMIT:
        return _failure_envelope(invocation, ObservationCompleteness.PARTIAL, reason, started_at_us, utc_now_us(), state=state_payload, source_sha256=state_hash)
    try:
        state = build_normalized_state(state_payload, known_secrets=(sas_value,))
    except ValueError:
        return _failure_envelope(invocation, ObservationCompleteness.PARTIAL, AZURE_QUEUE_RESPONSE_INVALID, started_at_us, utc_now_us())
    if state.byte_count > invocation.spec.budget.max_bytes:
        return _failure_envelope(invocation, ObservationCompleteness.PARTIAL, AZURE_QUEUE_RESPONSE_LIMIT, started_at_us, utc_now_us())
    return ObservationEnvelopeV2(
        observer_id=invocation.spec.observer_id,
        observer_type=ObserverType.AZURE_QUEUE_PEEK,
        phase=invocation.phase,
        target_id=invocation.spec.target.target_id,
        window=ObservationWindowV2(
            phase=invocation.phase,
            started_at_us=started_at_us,
            finished_at_us=min(utc_now_us(), started_at_us + invocation.spec.budget.timeout_us),
            timeout_us=invocation.spec.budget.timeout_us,
        ),
        correlation=invocation.correlation,
        causality=CausalityStatus.CORRELATED,
        completeness=ObservationCompleteness.COMPLETE,
        state=state,
        provenance=ObservationProvenanceV2(
            provenance_type=ProvenanceType.AZURE_QUEUE_PEEK,
            adapter_version=AZURE_QUEUE_ADAPTER_VERSION,
            target_id=invocation.spec.target.target_id,
            source_sha256=canonical_sha256(state.canonical_data),
        ),
    )


def child_main(input_path: str, output_path: str) -> int:
    try:
        input_file = Path(input_path)
        if input_file.stat().st_size > OBSERVER_JSON_MAX_BYTES:
            return 3
        invocation = parse_observer_json(input_file.read_bytes(), ObserverInvocationV2)
        envelope = _run_child(invocation, utc_now_us=_now_us)
        _write_atomic(Path(output_path), envelope.model_dump_json().encode("utf-8"))
        return 0
    except Exception:
        return 3


def _reap_after_stop(process: Any) -> None:
    try:
        process.wait(timeout=_PROCESS_REAP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.wait(timeout=_PROCESS_REAP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            pass


def _validate_output_binding(invocation: ObserverInvocationV2, envelope: ObservationEnvelopeV2) -> None:
    if envelope.observer_id != invocation.spec.observer_id or envelope.observer_type is not ObserverType.AZURE_QUEUE_PEEK:
        raise ValueError("azure queue output binding mismatch")
    if envelope.phase is not invocation.phase or envelope.target_id != invocation.spec.target.target_id or envelope.correlation != invocation.correlation:
        raise ValueError("azure queue output correlation mismatch")
    if envelope.window.phase is not invocation.phase or envelope.window.timeout_us != invocation.spec.budget.timeout_us:
        raise ValueError("azure queue output window mismatch")
    if envelope.provenance is not None:
        if envelope.provenance.provenance_type is not ProvenanceType.AZURE_QUEUE_PEEK or envelope.provenance.target_id != invocation.spec.target.target_id:
            raise ValueError("azure queue output provenance mismatch")


def run_azure_queue_observer(
    spec: ObserverSpecV2,
    correlation: CorrelationV2,
    phase: ObservationPhase,
    *,
    attempt_dir: Path,
    parent_environ: Mapping[str, str] | None = None,
    python_executable: str | None = None,
) -> QueueObserverResult:
    invocation = ObserverInvocationV2(spec=spec, correlation=correlation, phase=phase)
    if spec.observer_type is not ObserverType.AZURE_QUEUE_PEEK or not isinstance(spec.target.locator, AzureQueuePeekLocatorV2):
        envelope = _failure_envelope(invocation, ObservationCompleteness.UNSUPPORTED, AZURE_QUEUE_UNSUPPORTED, _now_us(), _now_us())
        return QueueObserverResult(envelope, evaluate_observer_outcome(envelope, required=spec.required))
    attempt_root = attempt_dir.resolve()
    attempt_root.mkdir(parents=True, exist_ok=True)
    input_path = attempt_root / "azure-queue-observer-input.json"
    output_path = attempt_root / "azure-queue-observer-output.json"
    temporary_paths = (
        input_path.with_name(f".{input_path.name}.tmp"),
        output_path.with_name(f".{output_path.name}.tmp"),
    )
    started_at_us = _now_us()
    deadline_ns = time.monotonic_ns() + spec.budget.timeout_us * 1_000
    try:
        source_name = _secret_name(spec)
        environment = minimal_process_environment(parent_environ if parent_environ is not None else os.environ, secret_names=(source_name,))
        environment["JIEJIAN_ATTEMPT_DIR"] = str(attempt_root)
        _write_atomic(input_path, invocation.model_dump_json().encode("utf-8"))
        remaining = (deadline_ns - time.monotonic_ns()) / 1_000_000_000
        if remaining <= 0:
            envelope = _failure_envelope(invocation, ObservationCompleteness.TIMED_OUT, AZURE_QUEUE_OBSERVATION_TIMEOUT, started_at_us, _now_us())
            return QueueObserverResult(envelope, evaluate_observer_outcome(envelope, required=spec.required))
        command = [python_executable or sys.executable, "-B", "-m", "jiejian.runner.azure_queue_observer_process", "--input", str(input_path), "--output", str(output_path)]
        try:
            process = subprocess.Popen(command, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            return QueueObserverResult(None, _execution_error(spec))
        try:
            while True:
                if (attempt_root / "cancel.requested").is_file():
                    terminator = getattr(process, "terminate", process.kill)
                    terminator()
                    _reap_after_stop(process)
                    envelope = _failure_envelope(invocation, ObservationCompleteness.PARTIAL, AZURE_QUEUE_CANCELLED, started_at_us, _now_us())
                    return QueueObserverResult(envelope, evaluate_observer_outcome(envelope, required=spec.required))
                remaining = (deadline_ns - time.monotonic_ns()) / 1_000_000_000
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, 0)
                try:
                    process.wait(timeout=min(remaining, _SUPERVISION_SLICE_SECONDS))
                    break
                except subprocess.TimeoutExpired:
                    continue
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except OSError:
                pass
            _reap_after_stop(process)
            envelope = _failure_envelope(invocation, ObservationCompleteness.TIMED_OUT, AZURE_QUEUE_OBSERVATION_TIMEOUT, started_at_us, _now_us())
            return QueueObserverResult(envelope, evaluate_observer_outcome(envelope, required=spec.required))
        if process.returncode != 0 or not output_path.is_file():
            return QueueObserverResult(None, _execution_error(spec))
        if output_path.stat().st_size > OBSERVER_JSON_MAX_BYTES:
            return QueueObserverResult(None, _execution_error(spec))
        try:
            known_secret = environment.get(source_name, "")
            envelope = parse_observer_json(output_path.read_bytes(), ObservationEnvelopeV2, known_secrets=(known_secret,))
            _validate_output_binding(invocation, envelope)
        except (OSError, ValueError):
            return QueueObserverResult(None, _execution_error(spec))
        return QueueObserverResult(envelope, evaluate_observer_outcome(envelope, required=spec.required))
    finally:
        for path in (input_path, output_path, *temporary_paths):
            path.unlink(missing_ok=True)
