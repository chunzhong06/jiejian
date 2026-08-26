# =============================================================================
# Azure Blob 只读对象观察器
#
# 定位
#   Runner 隔离域内对授权 Blob 范围的多面事实采集
#
# 职责
#   固定 container/prefix｜有界 list、head、get｜SAS 与响应原文隔离
#
# 边界
#   仅形成 Observation，不决定 Verdict；超时、取消或完整性不足均不可视为安全。
#
# 调用链
#   Runner → observer parent → isolated child → Azure Blob REST
# =============================================================================

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from product.backend.infra.runtime.process.tree import release_process_tree, terminate_process_tree
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import quote, unquote

import httpx

from product.backend.core.errors import JiejianError
from product.backend.infra.runtime.process.environment import ProcessEnvironmentRole, spawn_python_module
from product.protocols.observer import AzureBlobObjectLocator, CausalityStatus, Correlation, ObservationCompleteness, ObservationEnvelope, ObservationPhase, ObservationProvenance, ObservationWindow, OBSERVER_JSON_MAX_BYTES, ObserverInvocation, ObserverOutcomeStatus, ObserverOutcome, ObserverSpec, ObserverType, ProvenanceType, build_normalized_state, observer_canonical_sha256, evaluate_observer_outcome, parse_observer_json


AZURE_BLOB_ADAPTER_VERSION = "azure-blob-object-2023-11-03"
AZURE_BLOB_PROCESS_ERROR = "AZURE_BLOB_PROCESS_ERROR"
AZURE_BLOB_UNSUPPORTED = "AZURE_BLOB_UNSUPPORTED"
AZURE_BLOB_SAS_INVALID = "AZURE_BLOB_SAS_INVALID"
AZURE_BLOB_UNAVAILABLE = "AZURE_BLOB_UNAVAILABLE"
AZURE_BLOB_AUTH = "AZURE_BLOB_AUTH"
AZURE_BLOB_RESOURCE_MISSING = "AZURE_BLOB_RESOURCE_MISSING"
AZURE_BLOB_THROTTLED = "AZURE_BLOB_THROTTLED"
AZURE_BLOB_HTTP_ERROR = "AZURE_BLOB_HTTP_ERROR"
AZURE_BLOB_REDIRECT = "AZURE_BLOB_REDIRECT"
AZURE_BLOB_REQUEST_TIMEOUT = "AZURE_BLOB_REQUEST_TIMEOUT"
AZURE_BLOB_OBSERVATION_TIMEOUT = "AZURE_BLOB_OBSERVATION_TIMEOUT"
AZURE_BLOB_CANCELLED = "AZURE_BLOB_CANCELLED"
AZURE_BLOB_RESPONSE_LIMIT = "AZURE_BLOB_RESPONSE_LIMIT"
AZURE_BLOB_PAGE_LIMIT = "AZURE_BLOB_PAGE_LIMIT"
AZURE_BLOB_OBJECT_LIMIT = "AZURE_BLOB_OBJECT_LIMIT"
AZURE_BLOB_OBJECT_BYTES = "AZURE_BLOB_OBJECT_BYTES"
AZURE_BLOB_PREFIX_VIOLATION = "AZURE_BLOB_PREFIX_VIOLATION"
AZURE_BLOB_RESPONSE_INVALID = "AZURE_BLOB_RESPONSE_INVALID"
AZURE_BLOB_OBJECT_INVALID = "AZURE_BLOB_OBJECT_INVALID"
AZURE_BLOB_OBJECT_CONFLICT = "AZURE_BLOB_OBJECT_CONFLICT"
AZURE_BLOB_OBJECT_MISSING = "AZURE_BLOB_OBJECT_MISSING"
AZURE_BLOB_LENGTH_MISMATCH = "AZURE_BLOB_LENGTH_MISMATCH"
AZURE_BLOB_METADATA_INVALID = "AZURE_BLOB_METADATA_INVALID"
AZURE_BLOB_CORRELATION_CONFLICT = "AZURE_BLOB_CORRELATION_CONFLICT"

_ALLOWED_SAS_KEYS = frozenset({"sv", "st", "se", "sp", "sr", "sig", "spr", "sip", "si"})
_REQUIRED_SAS_KEYS = frozenset({"sv", "se", "sp", "sr", "sig"})
_SAS_CONTROL = re.compile(r"[\x00-\x20\x7f]")
_TEXT_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SECRET_MAX_BYTES = 8192
_TEXT_MAX_BYTES = 2048
_PROCESS_REAP_TIMEOUT_SECONDS = 1.0
_SUPERVISION_SLICE_SECONDS = 0.05
_MAX_MARKER_BYTES = 4096


@dataclass(frozen=True)
class BlobObserverResult:
    envelope: ObservationEnvelope | None
    outcome: ObserverOutcome


@dataclass(frozen=True)
class _HttpResult:
    status_code: int
    headers: Mapping[str, str]
    body: bytes
    read_bytes: int
    reason: str | None = None


@dataclass(frozen=True)
class _ListedBlob:
    name: str
    etag: str
    content_length: int
    metadata: dict[str, str]


def _now_us() -> int:
    return time.time_ns() // 1_000


def _secret_name(spec: ObserverSpec) -> str:
    locator = spec.target.locator
    if not isinstance(locator, AzureBlobObjectLocator):
        raise ValueError("azure blob observer requires a blob locator")
    return locator.read_only_sas_ref.removeprefix("env:")


def _write_atomic(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _failure_envelope(
    invocation: ObserverInvocation,
    completeness: ObservationCompleteness,
    reason: str,
    started_at_us: int,
    finished_at_us: int,
    *,
    state: Mapping[str, Any] | None = None,
    source_sha256: str | None = None,
) -> ObservationEnvelope:
    budget = invocation.spec.budget.timeout_us
    normalized = None
    provenance = None
    if state is not None and completeness is ObservationCompleteness.PARTIAL:
        try:
            normalized = build_normalized_state(state)
            provenance = ObservationProvenance(
                provenance_type=ProvenanceType.AZURE_BLOB_OBJECT,
                adapter_version=AZURE_BLOB_ADAPTER_VERSION,
                target_id=invocation.spec.target.target_id,
                source_sha256=source_sha256 or observer_canonical_sha256(state),
            )
        except ValueError:
            normalized = None
            provenance = None
    return ObservationEnvelope(
        observer_id=invocation.spec.observer_id,
        observer_type=invocation.spec.observer_type,
        phase=invocation.phase,
        target_id=invocation.spec.target.target_id,
        window=ObservationWindow(
            phase=invocation.phase,
            started_at_us=started_at_us,
            finished_at_us=min(max(finished_at_us, started_at_us), started_at_us + budget),
            timeout_us=budget,
        ),
        correlation=invocation.correlation,
        causality=CausalityStatus.CORRELATED if normalized is not None else CausalityStatus.UNVERIFIED,
        completeness=completeness,
        state=normalized,
        provenance=provenance,
        reason_codes=(reason,),
    )


def _execution_error(spec: ObserverSpec) -> ObserverOutcome:
    return ObserverOutcome(
        observer_id=spec.observer_id,
        required=spec.required,
        status=ObserverOutcomeStatus.EXECUTION_ERROR,
        reason_codes=(AZURE_BLOB_PROCESS_ERROR,),
    )


def _parse_sas(value: str) -> str:
    if len(value.encode("utf-8")) > _SECRET_MAX_BYTES or _SAS_CONTROL.search(value):
        raise ValueError(AZURE_BLOB_SAS_INVALID)
    normalized = value[1:] if value.startswith("?") else value
    if not normalized or "?" in normalized or "#" in normalized:
        raise ValueError(AZURE_BLOB_SAS_INVALID)
    values: dict[str, str] = {}
    for part in normalized.split("&"):
        if not part or part.count("=") != 1:
            raise ValueError(AZURE_BLOB_SAS_INVALID)
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
            raise ValueError(AZURE_BLOB_SAS_INVALID)
        values[key] = decoded
    if not _REQUIRED_SAS_KEYS.issubset(values) or values.get("sr") != "c" or values.get("sp") != "rl":
        raise ValueError(AZURE_BLOB_SAS_INVALID)
    return normalized


def _local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _child_text(element: ET.Element, name: str) -> str | None:
    return next((child.text for child in element if _local_name(child) == name), None)


def _safe_blob_name(name: str, prefix: str) -> str:
    if (
        not name
        or not name.startswith(prefix)
        or "\\" in name
        or "?" in name
        or "#" in name
        or "%" in name
        or _TEXT_CONTROL.search(name)
    ):
        raise ValueError(AZURE_BLOB_OBJECT_INVALID)
    relative = name[len(prefix) :]
    if not relative or any(segment in {"", ".", ".."} for segment in relative.split("/")):
        raise ValueError(AZURE_BLOB_OBJECT_INVALID)
    return relative


def _safe_text(value: str | None, *, required: bool = True) -> str:
    if value is None:
        if required:
            raise ValueError(AZURE_BLOB_RESPONSE_INVALID)
        return ""
    if not value or len(value.encode("utf-8")) > _TEXT_MAX_BYTES or _TEXT_CONTROL.search(value):
        raise ValueError(AZURE_BLOB_RESPONSE_INVALID)
    return value


def _normalize_etag(value: str | None) -> str:
    if value is None or not value or len(value.encode("utf-8")) > _TEXT_MAX_BYTES or _TEXT_CONTROL.search(value):
        raise ValueError(AZURE_BLOB_RESPONSE_INVALID)
    if value.startswith(("W/", "w/")):
        raise ValueError(AZURE_BLOB_RESPONSE_INVALID)
    starts_quoted = value.startswith('"')
    ends_quoted = value.endswith('"')
    if starts_quoted != ends_quoted:
        raise ValueError(AZURE_BLOB_RESPONSE_INVALID)
    normalized = value[1:-1] if starts_quoted else value
    if not normalized or '"' in normalized or "\\" in normalized:
        raise ValueError(AZURE_BLOB_RESPONSE_INVALID)
    return normalized


def _parse_metadata(element: ET.Element | None, allowed: tuple[str, ...]) -> dict[str, str]:
    if element is None:
        return {}
    allowed_set = set(allowed)
    result: dict[str, str] = {}
    for child in element:
        key = _local_name(child).lower()
        value = _safe_text(child.text)
        if key in result or key not in allowed_set:
            raise ValueError(AZURE_BLOB_METADATA_INVALID)
        result[key] = value
    return {key: result[key] for key in sorted(result)}


def _parse_list(body: bytes, locator: AzureBlobObjectLocator, prefix: str) -> tuple[list[_ListedBlob], str | None]:
    if not body or body.startswith(b"\xef\xbb\xbf") or b"<!" in body:
        raise ValueError(AZURE_BLOB_RESPONSE_INVALID)
    root = ET.fromstring(body)
    blobs: list[_ListedBlob] = []
    for element in root.iter():
        if _local_name(element) != "Blob":
            continue
        name = _safe_blob_name(_safe_text(_child_text(element, "Name")), prefix)
        properties = next((child for child in element if _local_name(child) == "Properties"), None)
        if properties is None:
            raise ValueError(AZURE_BLOB_RESPONSE_INVALID)
        etag = _normalize_etag(_child_text(properties, "Etag"))
        length_text = _safe_text(_child_text(properties, "Content-Length"))
        try:
            content_length = int(length_text)
        except ValueError:
            raise ValueError(AZURE_BLOB_RESPONSE_INVALID) from None
        if content_length < 0:
            raise ValueError(AZURE_BLOB_RESPONSE_INVALID)
        metadata_element = next((child for child in element if _local_name(child) == "Metadata"), None)
        metadata = _parse_metadata(metadata_element, locator.allowed_metadata_fields)
        blobs.append(_ListedBlob(name, etag, content_length, metadata))
    marker = _child_text(root, "NextMarker") or ""
    if marker and (len(marker.encode("utf-8")) > _MAX_MARKER_BYTES or _TEXT_CONTROL.search(marker)):
        raise ValueError(AZURE_BLOB_RESPONSE_INVALID)
    return blobs, marker or None


def _status_reason(status_code: int, *, head: bool = False) -> str:
    if status_code in {401, 403}:
        return AZURE_BLOB_AUTH
    if status_code == 404:
        return AZURE_BLOB_OBJECT_MISSING if head else AZURE_BLOB_RESOURCE_MISSING
    if status_code == 408:
        return AZURE_BLOB_REQUEST_TIMEOUT
    if status_code == 429:
        return AZURE_BLOB_THROTTLED
    if 500 <= status_code <= 599:
        return AZURE_BLOB_UNAVAILABLE
    if 300 <= status_code <= 399:
        return AZURE_BLOB_REDIRECT
    return AZURE_BLOB_HTTP_ERROR


def _read_body(response: Any, *, max_bytes: int) -> tuple[bytes, int, str | None]:
    raw = bytearray()
    try:
        for chunk in response.iter_bytes():
            if not isinstance(chunk, bytes):
                return b"", len(raw), AZURE_BLOB_RESPONSE_INVALID
            if len(raw) + len(chunk) > max_bytes:
                return b"", len(raw) + len(chunk), AZURE_BLOB_RESPONSE_LIMIT
            raw.extend(chunk)
    except (UnicodeError, ValueError):
        return b"", len(raw), AZURE_BLOB_RESPONSE_INVALID
    return bytes(raw), len(raw), None


def _request_with_retry(
    client: Any,
    method: str,
    url: str,
    *,
    headers: Mapping[str, str],
    locator: AzureBlobObjectLocator,
    deadline_ns: int,
    total_bytes: int,
    total_limit: int,
) -> tuple[_HttpResult | None, int, str | None]:
    budget = locator.scan_budget
    retry_reason = {AZURE_BLOB_REQUEST_TIMEOUT, AZURE_BLOB_THROTTLED, AZURE_BLOB_UNAVAILABLE}
    last_reason: str | None = None
    for attempt in range(budget.max_attempts):
        if time.monotonic_ns() >= deadline_ns:
            return None, total_bytes, AZURE_BLOB_OBSERVATION_TIMEOUT
        try:
            with client.stream(method, url, headers=headers) as response:
                if method == "HEAD":
                    body, read_bytes, reason = b"", 0, None
                else:
                    body, read_bytes, reason = _read_body(
                        response,
                        max_bytes=min(locator.scan_budget.max_total_bytes - total_bytes, total_limit - total_bytes, OBSERVER_JSON_MAX_BYTES),
                    )
                total_bytes += read_bytes
                status_ok = response.status_code == 200 or (method == "GET" and "Range" in headers and response.status_code == 206)
                status_reason = _status_reason(response.status_code, head=method == "HEAD") if not status_ok else reason
                result = _HttpResult(response.status_code, dict(response.headers), body, read_bytes, status_reason)
        except httpx.TimeoutException:
            result = None
            read_bytes = 0
            total_bytes += read_bytes
            status_reason = AZURE_BLOB_REQUEST_TIMEOUT
        except httpx.RequestError:
            result = None
            read_bytes = 0
            total_bytes += read_bytes
            status_reason = AZURE_BLOB_UNAVAILABLE
        if total_bytes > locator.scan_budget.max_total_bytes or total_bytes > total_limit or total_bytes > OBSERVER_JSON_MAX_BYTES:
            return result, total_bytes, AZURE_BLOB_RESPONSE_LIMIT
        if result is not None and result.reason is None:
            return result, total_bytes, None
        last_reason = status_reason
        if last_reason not in retry_reason or attempt + 1 >= budget.max_attempts:
            return result, total_bytes, last_reason
        remaining = max(0, deadline_ns - time.monotonic_ns()) / 1_000_000_000
        time.sleep(min(budget.retry_interval_us / 1_000_000, remaining))
    return None, total_bytes, last_reason or AZURE_BLOB_UNAVAILABLE


def _object_url(locator: AzureBlobObjectLocator, name: str, sas: str) -> str:
    return f"{locator.service_url}/{locator.container_name}/{quote(name, safe='/')}?{sas}"


def _list_url(locator: AzureBlobObjectLocator, prefix: str, sas: str, marker: str | None) -> str:
    query = f"restype=container&comp=list&prefix={quote(prefix, safe='')}&include=metadata&maxresults={locator.scan_budget.page_size}"
    if marker:
        query += f"&marker={quote(marker, safe='')}"
    return f"{locator.service_url}/{locator.container_name}?{sas}&{query}"


def _parse_headers_metadata(headers: Mapping[str, str], allowed: tuple[str, ...]) -> dict[str, str]:
    allowed_set = set(allowed)
    result: dict[str, str] = {}
    for key, value in headers.items():
        lower = str(key).lower()
        if not lower.startswith("x-ms-meta-"):
            continue
        name = lower.removeprefix("x-ms-meta-")
        if name in result or name not in allowed_set:
            raise ValueError(AZURE_BLOB_METADATA_INVALID)
        result[name] = _safe_text(str(value))
    if not set(allowed).issuperset(result):
        raise ValueError(AZURE_BLOB_METADATA_INVALID)
    return {key: result[key] for key in sorted(result)}


def _run_child(invocation: ObserverInvocation, *, utc_now_us: Callable[[], int]) -> ObservationEnvelope:
    started_at_us = utc_now_us()
    locator = invocation.spec.target.locator
    if invocation.spec.observer_type is not ObserverType.AZURE_BLOB_OBJECT or not isinstance(locator, AzureBlobObjectLocator):
        return _failure_envelope(invocation, ObservationCompleteness.UNSUPPORTED, AZURE_BLOB_UNSUPPORTED, started_at_us, utc_now_us())
    secret_name = _secret_name(invocation.spec)
    sas_value = os.environ.get(secret_name)
    if not sas_value:
        return _failure_envelope(invocation, ObservationCompleteness.MISSING, AZURE_BLOB_SAS_INVALID, started_at_us, utc_now_us())
    try:
        sas = _parse_sas(sas_value)
    except ValueError:
        return _failure_envelope(invocation, ObservationCompleteness.UNSUPPORTED, AZURE_BLOB_SAS_INVALID, started_at_us, utc_now_us())
    attempt_dir = Path(os.environ.get("JIEJIAN_ATTEMPT_DIR", "."))
    if (attempt_dir / "cancel.requested").is_file():
        return _failure_envelope(invocation, ObservationCompleteness.PARTIAL, AZURE_BLOB_CANCELLED, started_at_us, utc_now_us())
    deadline_ns = time.monotonic_ns() + invocation.spec.budget.timeout_us * 1_000
    prefix = locator.prefix_template.replace("{request_marker}", invocation.correlation.request_marker)
    try:
        client = httpx.Client(follow_redirects=False, trust_env=False, timeout=locator.scan_budget.per_request_timeout_us / 1_000_000)
    except Exception:
        return _failure_envelope(invocation, ObservationCompleteness.UNSUPPORTED, AZURE_BLOB_UNSUPPORTED, started_at_us, utc_now_us())
    total_bytes = 0
    blobs: list[_ListedBlob] = []
    marker: str | None = None
    seen_markers: set[str] = set()
    reason: str | None = None
    try:
        for page in range(locator.scan_budget.max_pages):
            if (attempt_dir / "cancel.requested").is_file():
                reason = AZURE_BLOB_CANCELLED
                break
            result, total_bytes, reason = _request_with_retry(
                client,
                "GET",
                _list_url(locator, prefix, sas, marker),
                headers={"x-ms-version": "2023-11-03", "Accept": "application/xml"},
                locator=locator,
                deadline_ns=deadline_ns,
                total_bytes=total_bytes,
                total_limit=invocation.spec.budget.max_bytes,
            )
            if result is None or reason is not None:
                break
            try:
                page_blobs, next_marker = _parse_list(result.body, locator, prefix)
            except (ET.ParseError, UnicodeError, ValueError) as exc:
                reason = str(exc) if str(exc).startswith("AZURE_BLOB_") else AZURE_BLOB_RESPONSE_INVALID
                break
            blobs.extend(page_blobs)
            if len(blobs) > locator.scan_budget.max_objects:
                reason = AZURE_BLOB_OBJECT_LIMIT
                break
            if not next_marker:
                marker = None
                break
            if next_marker in seen_markers:
                reason = AZURE_BLOB_RESPONSE_INVALID
                break
            seen_markers.add(next_marker)
            marker = next_marker
        else:
            if marker is not None:
                reason = AZURE_BLOB_PAGE_LIMIT
        if reason is None and marker is not None:
            reason = AZURE_BLOB_PAGE_LIMIT
        if reason is None and time.monotonic_ns() >= deadline_ns:
            reason = AZURE_BLOB_OBSERVATION_TIMEOUT
        if reason is None:
            by_name: dict[str, _ListedBlob] = {}
            conflict = False
            for item in blobs:
                previous = by_name.get(item.name)
                if previous is not None and previous != item:
                    conflict = True
                else:
                    by_name[item.name] = item
            if conflict:
                reason = AZURE_BLOB_OBJECT_CONFLICT
            else:
                for item in by_name.values():
                    if "case_tag" not in item.metadata or "resource_id" not in item.metadata:
                        reason = AZURE_BLOB_METADATA_INVALID
                        break
                    if (
                        item.metadata["case_tag"] != invocation.correlation.request_marker
                        or item.metadata["resource_id"] != invocation.correlation.resource_id
                    ):
                        reason = AZURE_BLOB_CORRELATION_CONFLICT
                        break
                normalized_objects: list[dict[str, Any]] = []
                for item in (sorted(by_name.values(), key=lambda value: value.name) if reason is None else ()):
                    if item.content_length > locator.scan_budget.max_object_bytes:
                        reason = AZURE_BLOB_OBJECT_BYTES
                        break
                    head, total_bytes, head_reason = _request_with_retry(
                        client,
                        "HEAD",
                        _object_url(locator, f"{prefix}{item.name}", sas),
                        headers={"x-ms-version": "2023-11-03"},
                        locator=locator,
                        deadline_ns=deadline_ns,
                        total_bytes=total_bytes,
                        total_limit=invocation.spec.budget.max_bytes,
                    )
                    if head is None or head_reason is not None:
                        reason = head_reason or AZURE_BLOB_UNAVAILABLE
                        break
                    try:
                        etag = _normalize_etag(head.headers.get("etag"))
                        length = int(_safe_text(head.headers.get("content-length")))
                        metadata = _parse_headers_metadata(head.headers, locator.allowed_metadata_fields)
                        if length != item.content_length or etag != item.etag:
                            raise ValueError(AZURE_BLOB_OBJECT_CONFLICT)
                        if item.metadata and item.metadata != metadata:
                            raise ValueError(AZURE_BLOB_OBJECT_CONFLICT)
                        if not {"case_tag", "resource_id"}.issubset(metadata):
                            raise ValueError(AZURE_BLOB_METADATA_INVALID)
                    except (TypeError, ValueError) as exc:
                        reason = str(exc) if str(exc).startswith("AZURE_BLOB_") else AZURE_BLOB_RESPONSE_INVALID
                        break
                    if length > locator.scan_budget.max_object_bytes:
                        reason = AZURE_BLOB_OBJECT_BYTES
                        break
                    get_headers = {"x-ms-version": "2023-11-03"}
                    if length:
                        get_headers["Range"] = f"bytes=0-{length - 1}"
                    content, total_bytes, get_reason = _request_with_retry(
                        client,
                        "GET",
                        _object_url(locator, f"{prefix}{item.name}", sas),
                        headers=get_headers,
                        locator=locator,
                        deadline_ns=deadline_ns,
                        total_bytes=total_bytes,
                        total_limit=invocation.spec.budget.max_bytes,
                    )
                    if content is None or get_reason is not None:
                        reason = get_reason or AZURE_BLOB_UNAVAILABLE
                        break
                    if len(content.body) != length:
                        reason = AZURE_BLOB_LENGTH_MISMATCH
                        break
                    normalized_objects.append(
                        {
                            "content_length": length,
                            "content_sha256": hashlib.sha256(content.body).hexdigest(),
                            "etag": etag,
                            "metadata": metadata,
                            "metadata_sha256": observer_canonical_sha256(metadata),
                            "name": item.name,
                        }
                    )
                state_payload = {
                    "objects": normalized_objects,
                    "scanned_count": len(blobs),
                    "window_complete": reason is None,
                }
                if reason is not None:
                    completeness = ObservationCompleteness.TIMED_OUT if reason in {AZURE_BLOB_REQUEST_TIMEOUT, AZURE_BLOB_OBSERVATION_TIMEOUT} else ObservationCompleteness.PARTIAL
                    return _failure_envelope(invocation, completeness, reason, started_at_us, utc_now_us(), state=state_payload, source_sha256=observer_canonical_sha256(state_payload))
                state = build_normalized_state(state_payload, known_secrets=(sas_value,))
                if state.byte_count > invocation.spec.budget.max_bytes:
                    return _failure_envelope(invocation, ObservationCompleteness.PARTIAL, AZURE_BLOB_RESPONSE_LIMIT, started_at_us, utc_now_us())
                return ObservationEnvelope(
                    observer_id=invocation.spec.observer_id,
                    observer_type=ObserverType.AZURE_BLOB_OBJECT,
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
                        provenance_type=ProvenanceType.AZURE_BLOB_OBJECT,
                        adapter_version=AZURE_BLOB_ADAPTER_VERSION,
                        target_id=invocation.spec.target.target_id,
                        source_sha256=observer_canonical_sha256(state.canonical_data),
                    ),
                )
        completeness = ObservationCompleteness.TIMED_OUT if reason in {AZURE_BLOB_REQUEST_TIMEOUT, AZURE_BLOB_OBSERVATION_TIMEOUT} else ObservationCompleteness.PARTIAL
        return _failure_envelope(invocation, completeness, reason or AZURE_BLOB_RESPONSE_INVALID, started_at_us, utc_now_us())
    finally:
        client.close()


def child_main(input_path: str, output_path: str) -> int:
    try:
        input_file = Path(input_path)
        if input_file.stat().st_size > OBSERVER_JSON_MAX_BYTES:
            return 3
        invocation = parse_observer_json(input_file.read_bytes(), ObserverInvocation)
        envelope = _run_child(invocation, utc_now_us=_now_us)
        _write_atomic(Path(output_path), envelope.model_dump_json().encode("utf-8"))
        return 0
    except Exception:
        return 3


def _validate_output_binding(invocation: ObserverInvocation, envelope: ObservationEnvelope) -> None:
    if envelope.observer_id != invocation.spec.observer_id or envelope.observer_type is not ObserverType.AZURE_BLOB_OBJECT:
        raise ValueError("azure blob output binding mismatch")
    if envelope.phase is not invocation.phase or envelope.target_id != invocation.spec.target.target_id or envelope.correlation != invocation.correlation:
        raise ValueError("azure blob output correlation mismatch")
    if envelope.window.phase is not invocation.phase or envelope.window.timeout_us != invocation.spec.budget.timeout_us:
        raise ValueError("azure blob output window mismatch")
    if envelope.provenance is not None:
        if envelope.provenance.provenance_type is not ProvenanceType.AZURE_BLOB_OBJECT or envelope.provenance.target_id != invocation.spec.target.target_id:
            raise ValueError("azure blob output provenance mismatch")


def run_azure_blob_observer(
    spec: ObserverSpec,
    correlation: Correlation,
    phase: ObservationPhase,
    *,
    attempt_dir: Path,
    parent_environ: Mapping[str, str] | None = None,
    python_executable: str | None = None,
) -> BlobObserverResult:
    """在独立进程中读取授权 Blob 视图；取消、超时和不完整响应显式降级。"""

    invocation = ObserverInvocation(spec=spec, correlation=correlation, phase=phase)
    if spec.observer_type is not ObserverType.AZURE_BLOB_OBJECT or not isinstance(spec.target.locator, AzureBlobObjectLocator):
        envelope = _failure_envelope(invocation, ObservationCompleteness.UNSUPPORTED, AZURE_BLOB_UNSUPPORTED, _now_us(), _now_us())
        return BlobObserverResult(envelope, evaluate_observer_outcome(envelope, required=spec.required))
    attempt_root = attempt_dir.resolve()
    attempt_root.mkdir(parents=True, exist_ok=True)
    input_path = attempt_root / "azure-blob-observer-input.json"
    output_path = attempt_root / "azure-blob-observer-output.json"
    temporary_paths = (input_path.with_name(f".{input_path.name}.tmp"), output_path.with_name(f".{output_path.name}.tmp"))
    started_at_us = _now_us()
    deadline_ns = time.monotonic_ns() + spec.budget.timeout_us * 1_000
    try:
        source_name = _secret_name(spec)
        environment = dict(parent_environ if parent_environ is not None else os.environ)
        environment.setdefault("JIEJIAN_VAR_DIR", str(attempt_root))
        _write_atomic(input_path, invocation.model_dump_json().encode("utf-8"))
        remaining = (deadline_ns - time.monotonic_ns()) / 1_000_000_000
        if remaining <= 0:
            envelope = _failure_envelope(invocation, ObservationCompleteness.TIMED_OUT, AZURE_BLOB_OBSERVATION_TIMEOUT, started_at_us, _now_us())
            return BlobObserverResult(envelope, evaluate_observer_outcome(envelope, required=spec.required))
        command = ["product.backend.infra.observers.azure_blob", "--input", str(input_path), "--output", str(output_path)]
        try:
            process = spawn_python_module(
                environment,
                command[0],
                *command[1:],
                role=ProcessEnvironmentRole.OBSERVER,
                secret_names=(source_name,),
                extra_environment={"JIEJIAN_ATTEMPT_DIR": str(attempt_root)},
                cwd=attempt_root,
                python_executable=python_executable,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            return BlobObserverResult(None, _execution_error(spec))
        try:
            while True:
                if (attempt_root / "cancel.requested").is_file():
                    terminate_process_tree(process, _PROCESS_REAP_TIMEOUT_SECONDS)
                    envelope = _failure_envelope(invocation, ObservationCompleteness.PARTIAL, AZURE_BLOB_CANCELLED, started_at_us, _now_us())
                    return BlobObserverResult(envelope, evaluate_observer_outcome(envelope, required=spec.required))
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
                terminate_process_tree(process, _PROCESS_REAP_TIMEOUT_SECONDS)
            except OSError:
                pass
            envelope = _failure_envelope(invocation, ObservationCompleteness.TIMED_OUT, AZURE_BLOB_OBSERVATION_TIMEOUT, started_at_us, _now_us())
            return BlobObserverResult(envelope, evaluate_observer_outcome(envelope, required=spec.required))
        if process.returncode != 0 or not output_path.is_file():
            return BlobObserverResult(None, _execution_error(spec))
        if output_path.stat().st_size > OBSERVER_JSON_MAX_BYTES:
            return BlobObserverResult(None, _execution_error(spec))
        try:
            known_secret = environment.get(source_name, "")
            envelope = parse_observer_json(output_path.read_bytes(), ObservationEnvelope, known_secrets=(known_secret,))
            _validate_output_binding(invocation, envelope)
        except (OSError, ValueError, JiejianError):
            return BlobObserverResult(None, _execution_error(spec))
        return BlobObserverResult(envelope, evaluate_observer_outcome(envelope, required=spec.required))
    finally:
        if "process" in locals():
            release_process_tree(process)
        for path in (input_path, output_path, *temporary_paths):
            path.unlink(missing_ok=True)

import argparse


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    return child_main(arguments.input, arguments.output)


if __name__ == "__main__":
    raise SystemExit(main())
