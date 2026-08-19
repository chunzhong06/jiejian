# =============================================================================
# Runner 隔离域结构化审计日志观察器
#
# 监督器只注入 authorized_root_ref 对应的单一环境变量；子进程仅读取授权根
# 顶层的固定 JSONL 轮转族，并把显式 case tag 的有界摘要交回 Observer 。
# =============================================================================

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time
import ctypes
import ctypes.wintypes
import msvcrt
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from product.backend.infra.runtime.process_environment import minimal_process_environment
from product.protocols.observer import AuditLogObserverInvocation, AuditLogStartCursor, CausalityStatus, Correlation, ObservationCompleteness, ObservationEnvelope, ObservationPhase, ObservationProvenance, ObservationWindow, ObserverOutcome, ObserverOutcomeStatus, ObserverSpec, ObserverType, OBSERVER_JSON_MAX_BYTES, ProvenanceType, StructuredAuditLogLocator, build_normalized_state, canonical_json_bytes, canonical_sha256, evaluate_observer_outcome, parse_observer_json


AUDIT_OBSERVER_PROCESS_ERROR = "AUDIT_OBSERVER_PROCESS_ERROR"
AUDIT_ROOT_MISSING = "AUDIT_ROOT_MISSING"
AUDIT_ROOT_UNAVAILABLE = "AUDIT_ROOT_UNAVAILABLE"
AUDIT_TAG_NOT_FOUND = "AUDIT_TAG_NOT_FOUND"
AUDIT_EVENT_INVALID = "AUDIT_EVENT_INVALID"
AUDIT_DUPLICATE_KEY = "AUDIT_DUPLICATE_KEY"
AUDIT_EVENT_CONFLICT = "AUDIT_EVENT_CONFLICT"
AUDIT_CHAIN_INVALID = "AUDIT_CHAIN_INVALID"
AUDIT_PARTIAL_LINE = "AUDIT_PARTIAL_LINE"
AUDIT_INVALID_UTF8 = "AUDIT_INVALID_UTF8"
AUDIT_BOM = "AUDIT_BOM"
AUDIT_OFFSET_PAST_END = "AUDIT_OFFSET_PAST_END"
AUDIT_FILE_CHANGED = "AUDIT_FILE_CHANGED"
AUDIT_FILE_LIMIT = "AUDIT_FILE_LIMIT"
AUDIT_LINE_LIMIT = "AUDIT_LINE_LIMIT"
AUDIT_LINE_BYTES_LIMIT = "AUDIT_LINE_BYTES_LIMIT"
AUDIT_RECORD_LIMIT = "AUDIT_RECORD_LIMIT"
AUDIT_BYTE_LIMIT = "AUDIT_BYTE_LIMIT"
AUDIT_CURSOR_UNMATCHED = "AUDIT_CURSOR_UNMATCHED"
AUDIT_CURSOR_AMBIGUOUS = "AUDIT_CURSOR_AMBIGUOUS"
AUDIT_TIMEOUT = "AUDIT_TIMEOUT"
_PROCESS_REAP_TIMEOUT_SECONDS = 1.0
_ROTATED_FILE = re.compile(r"^(?P<prefix>[a-z][a-z0-9_-]{0,48})\.(?P<index>[1-9][0-9]{0,8})\.jsonl$")
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


@dataclass(frozen=True)
class AuditLogObserverResult:
    envelope: ObservationEnvelope | None
    outcome: ObserverOutcome


def _now_us() -> int:
    return time.time_ns() // 1_000


def _secret_name(spec: ObserverSpec) -> str:
    locator = spec.target.locator
    if not isinstance(locator, StructuredAuditLogLocator):
        raise ValueError("audit observer requires an audit locator")
    return locator.authorized_root_ref.removeprefix("env:")


def _write_atomic(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _failure_envelope(
    invocation: AuditLogObserverInvocation,
    completeness: ObservationCompleteness,
    reason: str,
    started_at_us: int,
    finished_at_us: int,
) -> ObservationEnvelope:
    timeout = invocation.spec.budget.timeout_us
    finished = min(max(finished_at_us, started_at_us), started_at_us + timeout)
    return ObservationEnvelope(
        observer_id=invocation.spec.observer_id,
        observer_type=ObserverType.STRUCTURED_AUDIT_LOG,
        phase=invocation.phase,
        target_id=invocation.spec.target.target_id,
        window=ObservationWindow(
            phase=invocation.phase,
            started_at_us=started_at_us,
            finished_at_us=finished,
            timeout_us=timeout,
        ),
        correlation=invocation.correlation,
        causality=CausalityStatus.UNVERIFIED,
        completeness=completeness,
        reason_codes=(reason,),
    )


def _execution_error(spec: ObserverSpec) -> ObserverOutcome:
    return ObserverOutcome(
        observer_id=spec.observer_id,
        required=spec.required,
        status=ObserverOutcomeStatus.EXECUTION_ERROR,
        reason_codes=(AUDIT_OBSERVER_PROCESS_ERROR,),
    )


def _is_non_local_root(value: str) -> bool:
    return value.startswith(("\\\\", "//", "\\??\\", "\\Device\\", "\\\\?\\", "\\\\.\\"))


def _is_reparse_or_symlink(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
        return bool(attributes & _REPARSE_POINT)
    except OSError:
        return True


def _file_names(locator: StructuredAuditLogLocator, root: Path) -> list[Path]:
    base = locator.relative_file_pattern
    prefix = base[:-6]
    candidates = [base, *(f"{prefix}.{index}.jsonl" for index in range(1, locator.scan_budget.max_files))]
    return [root / name for name in candidates if (root / name).exists()]


def _handle_final_path(handle: Any) -> Path | None:
    if os.name != "nt":
        try:
            return Path(os.path.realpath(f"/proc/self/fd/{handle.fileno()}"))
        except (OSError, ValueError):
            return None
    try:
        kernel32 = ctypes.windll.kernel32
        get_final_path = kernel32.GetFinalPathNameByHandleW
        get_final_path.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.LPWSTR, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD]
        get_final_path.restype = ctypes.wintypes.DWORD
        buffer = ctypes.create_unicode_buffer(32768)
        length = get_final_path(msvcrt.get_osfhandle(handle.fileno()), buffer, len(buffer), 0)
        if not length or length >= len(buffer):
            return None
        value = buffer.value
        if value.startswith("\\\\?\\"):
            value = value[4:]
        return Path(value)
    except (AttributeError, OSError, ValueError):
        return None


def _same_file_stat(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        left.st_size,
        left.st_mtime_ns,
        left.st_ctime_ns,
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_size,
        right.st_mtime_ns,
        right.st_ctime_ns,
    )


def _open_snapshot(
    path: Path,
    root: Path,
    offset: int,
    *,
    read_end: int | None = None,
    max_bytes: int | None = None,
) -> tuple[Any, bytes] | None:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        if _is_reparse_or_symlink(path):
            return None
        fd = os.open(path, flags | nofollow)
        handle = os.fdopen(fd, "rb", closefd=True)
        if _is_reparse_or_symlink(path):
            handle.close()
            return None
        before_handle = os.fstat(handle.fileno())
        final_path = _handle_final_path(handle)
        if final_path is None:
            handle.close()
            return None
        final_path = final_path.resolve(strict=True)
        final_parent = os.path.normcase(os.path.normpath(str(final_path.parent)))
        root_name = os.path.normcase(os.path.normpath(str(root)))
        if final_parent != root_name:
            handle.close()
            return None
        snapshot_size = before_handle.st_size
        if offset > snapshot_size:
            handle.close()
            return None
        end = snapshot_size if read_end is None else min(read_end, snapshot_size)
        if end < offset or (max_bytes is not None and end - offset > max_bytes):
            handle.close()
            return None
        handle.seek(offset)
        data = handle.read(end - offset)
        after_handle = os.fstat(handle.fileno())
        after_path = path.stat()
        if not _same_file_stat(before_handle, after_handle) or not os.path.samestat(after_handle, after_path) or (
            after_handle.st_dev,
            after_handle.st_ino,
            after_handle.st_size,
            after_handle.st_mtime_ns,
        ) != (
            after_path.st_dev,
            after_path.st_ino,
            after_path.st_size,
            after_path.st_mtime_ns,
        ):
            handle.close()
            return None
        return handle, data
    except (OSError, ValueError):
        try:
            handle.close()
        except (UnboundLocalError, AttributeError):
            pass
        return None


def _cursor_anchor(path: Path, offset: int) -> tuple[int, int, str] | None:
    if offset <= 0:
        return None
    start = max(0, offset - 256)
    with path.open("rb") as handle:
        handle.seek(start)
        data = handle.read(offset - start)
    if len(data) != offset - start:
        return None
    return start, len(data), hashlib.sha256(data).hexdigest()


def _cursor_payload(file_name: str, base_offset: int, data: bytes, next_offset: int) -> dict[str, Any]:
    if next_offset == 0:
        return {"file_name": file_name, "offset": 0}
    start = max(base_offset, next_offset - 256)
    anchor = data[start - base_offset : next_offset - base_offset]
    return {
        "file_name": file_name,
        "offset": next_offset,
        "anchor_start": start,
        "anchor_length": len(anchor),
        "anchor_sha256": hashlib.sha256(anchor).hexdigest(),
    }


def _strict_json_line(line: bytes) -> dict[str, Any]:
    if line.startswith(b"\xef\xbb\xbf"):
        raise ValueError(AUDIT_BOM)

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(AUDIT_DUPLICATE_KEY)
            result[key] = value
        return result

    def reject_nonfinite(value: str) -> None:
        raise ValueError(AUDIT_EVENT_INVALID)

    parsed = json.loads(
        line.decode("utf-8"),
        object_pairs_hook=reject_duplicates,
        parse_constant=reject_nonfinite,
    )
    if not isinstance(parsed, dict):
        raise ValueError(AUDIT_EVENT_INVALID)
    return parsed


def _audit_state(
    records: list[dict[str, Any]],
    next_offsets: list[dict[str, Any]],
    counters: Mapping[str, int],
) -> dict[str, Any]:
    return {
        "records": records,
        "next_offsets": next_offsets,
        "scan_counters": dict(counters),
    }


def _audit_envelope(
    invocation: AuditLogObserverInvocation,
    records: list[dict[str, Any]],
    next_offsets: list[dict[str, Any]],
    counters: Mapping[str, int],
    source_sha256: str,
    started_at_us: int,
    finished_at_us: int,
    *,
    completeness: ObservationCompleteness = ObservationCompleteness.COMPLETE,
    reason_codes: tuple[str, ...] = (),
) -> ObservationEnvelope:
    payload = _audit_state(records, next_offsets, counters)
    state = build_normalized_state(payload)
    return ObservationEnvelope(
        observer_id=invocation.spec.observer_id,
        observer_type=ObserverType.STRUCTURED_AUDIT_LOG,
        phase=invocation.phase,
        target_id=invocation.spec.target.target_id,
        window=ObservationWindow(
            phase=invocation.phase,
            started_at_us=started_at_us,
            finished_at_us=min(finished_at_us, started_at_us + invocation.spec.budget.timeout_us),
            timeout_us=invocation.spec.budget.timeout_us,
        ),
        correlation=invocation.correlation,
        causality=CausalityStatus.CORRELATED if records else CausalityStatus.UNVERIFIED,
        completeness=completeness,
        state=state,
        provenance=ObservationProvenance(
            provenance_type=ProvenanceType.AUDIT_LOG_WINDOW,
            adapter_version="audit-log-observer-1",
            target_id=invocation.spec.target.target_id,
            source_sha256=source_sha256,
        ),
        reason_codes=reason_codes,
    )


def _run_child(invocation: AuditLogObserverInvocation, *, utc_now_us: Callable[[], int]) -> ObservationEnvelope:
    started_at_us = utc_now_us()
    locator = invocation.spec.target.locator
    if invocation.spec.observer_type is not ObserverType.STRUCTURED_AUDIT_LOG or not isinstance(locator, StructuredAuditLogLocator):
        return _failure_envelope(invocation, ObservationCompleteness.UNSUPPORTED, AUDIT_ROOT_UNAVAILABLE, started_at_us, utc_now_us())
    source = os.environ.get(_secret_name(invocation.spec))
    if not source:
        return _failure_envelope(invocation, ObservationCompleteness.MISSING, AUDIT_ROOT_MISSING, started_at_us, utc_now_us())
    if _is_non_local_root(source) or "\x00" in source:
        return _failure_envelope(invocation, ObservationCompleteness.MISSING, AUDIT_ROOT_UNAVAILABLE, started_at_us, utc_now_us())
    root = Path(source)
    if not root.is_absolute() or _is_reparse_or_symlink(root):
        return _failure_envelope(invocation, ObservationCompleteness.MISSING, AUDIT_ROOT_UNAVAILABLE, started_at_us, utc_now_us())
    try:
        root = root.resolve(strict=True)
        if not root.is_dir() or _is_reparse_or_symlink(root):
            raise OSError
        files = _file_names(locator, root)
    except (OSError, ValueError):
        return _failure_envelope(invocation, ObservationCompleteness.MISSING, AUDIT_ROOT_UNAVAILABLE, started_at_us, utc_now_us())
    budget = invocation.spec.budget
    scan_budget = locator.scan_budget
    deadline_ns = time.monotonic_ns() + budget.timeout_us * 1_000
    cursor_paths: dict[str, AuditLogStartCursor] = {}
    reasons: set[str] = set()
    for cursor in invocation.start_cursors:
        if cursor.offset == 0:
            cursor_paths[cursor.file_name] = cursor
            continue
        matches: list[str] = []
        anchor_start = cursor.anchor_start
        assert anchor_start is not None and cursor.anchor_length is not None and cursor.anchor_sha256 is not None
        for candidate in files:
            try:
                if candidate.stat().st_size < cursor.offset:
                    continue
                opened = _open_snapshot(candidate, root, anchor_start, read_end=cursor.offset)
                if opened is None:
                    continue
                handle, anchor = opened
                handle.close()
                if len(anchor) == cursor.anchor_length and hashlib.sha256(anchor).hexdigest() == cursor.anchor_sha256:
                    matches.append(candidate.name)
            except OSError:
                continue
        if not matches:
            reasons.add(AUDIT_CURSOR_UNMATCHED)
        elif len(matches) > 1:
            reasons.add(AUDIT_CURSOR_AMBIGUOUS)
        else:
            cursor_paths[matches[0]] = cursor
    records: list[dict[str, Any]] = []
    seen: dict[str, bytes] = {}
    next_offsets: list[dict[str, Any]] = []
    consumed: list[dict[str, Any]] = []
    counters = {"files": 0, "bytes": 0, "lines": 0, "records": 0}
    for path in files:
        try:
            before = path.stat()
            cursor = cursor_paths.get(path.name)
            offset = cursor.offset if cursor is not None else 0
            if offset > before.st_size:
                reasons.add(AUDIT_OFFSET_PAST_END)
                continue
            remaining = budget.max_bytes - counters["bytes"]
            if before.st_size - offset > remaining:
                reasons.add(AUDIT_BYTE_LIMIT)
                break
            opened = _open_snapshot(path, root, offset, read_end=before.st_size, max_bytes=remaining)
            if opened is None:
                reasons.add(AUDIT_FILE_CHANGED)
                continue
            handle, data = opened
            handle.close()
            if time.monotonic_ns() >= deadline_ns:
                reasons.add(AUDIT_TIMEOUT)
                break
        except (OSError, ValueError):
            reasons.add(AUDIT_ROOT_UNAVAILABLE)
            continue
        counters["files"] += 1
        counters["bytes"] += len(data)
        position = offset
        lines = data.splitlines(keepends=True)
        for index, line in enumerate(lines):
            if time.monotonic_ns() >= deadline_ns:
                reasons.add(AUDIT_TIMEOUT)
                break
            line_start = position
            position += len(line)
            if index == len(lines) - 1 and not line.endswith((b"\n", b"\r")):
                next_offsets.append(_cursor_payload(path.name, offset, data, line_start))
                reasons.add(AUDIT_PARTIAL_LINE)
                continue
            counters["lines"] += 1
            if len(line) > scan_budget.max_line_bytes:
                reasons.add(AUDIT_LINE_BYTES_LIMIT)
                break
            if counters["lines"] > scan_budget.max_lines:
                reasons.add(AUDIT_LINE_LIMIT)
                break
            try:
                record = _strict_json_line(line.rstrip(b"\r\n"))
            except (UnicodeDecodeError, ValueError) as error:
                if isinstance(error, UnicodeDecodeError):
                    reasons.add(AUDIT_INVALID_UTF8)
                elif str(error) in {AUDIT_BOM, AUDIT_DUPLICATE_KEY}:
                    reasons.add(str(error))
                else:
                    reasons.add(AUDIT_EVENT_INVALID)
                continue
            if set(record) - set(locator.allowed_fields) or any(
                isinstance(value, (dict, list, tuple)) for value in record.values()
            ):
                reasons.add(AUDIT_EVENT_INVALID)
                continue
            if not all(field in record for field in ("event_id", "case_tag", "task_id", "event_type", "sequence", "resource_id")):
                reasons.add(AUDIT_EVENT_INVALID)
                continue
            if not all(
                isinstance(record[field], str)
                for field in ("event_id", "case_tag", "task_id", "event_type", "resource_id")
            ) or not isinstance(record["sequence"], int) or isinstance(record["sequence"], bool):
                reasons.add(AUDIT_EVENT_INVALID)
                continue
            event_id = record["event_id"]
            canonical = canonical_json_bytes(record)
            if event_id in seen:
                if seen[event_id] != canonical:
                    reasons.add(AUDIT_EVENT_CONFLICT)
                continue
            seen[event_id] = canonical
            counters["records"] += 1
            if record["case_tag"] == invocation.correlation.request_marker:
                if len(records) >= budget.max_rows:
                    reasons.add(AUDIT_RECORD_LIMIT)
                    break
                records.append({key: record[key] for key in locator.allowed_fields if key in record})
                consumed.append({"file_name": path.name, "offset": line_start, "length": len(line), "record_sha256": hashlib.sha256(canonical).hexdigest()})
        if not any(item["file_name"] == path.name for item in next_offsets):
            next_offsets.append(_cursor_payload(path.name, offset, data, before.st_size))
        if reasons & {AUDIT_TIMEOUT, AUDIT_BYTE_LIMIT, AUDIT_LINE_LIMIT, AUDIT_LINE_BYTES_LIMIT, AUDIT_RECORD_LIMIT}:
            break
    records.sort(key=lambda record: (int(record["sequence"]) if isinstance(record["sequence"], int) else -1, str(record["event_id"])))
    task_ids = {record["task_id"] for record in records if record.get("task_id")}
    resource_ids = {record["resource_id"] for record in records}
    if not records:
        reasons.add(AUDIT_TAG_NOT_FOUND)
    if len(task_ids) > 1 or len(resource_ids) > 1:
        reasons.add(AUDIT_CHAIN_INVALID)
    if records and any(record["resource_id"] != invocation.correlation.resource_id for record in records):
        reasons.add(AUDIT_CHAIN_INVALID)
    sequences = [record["sequence"] for record in records]
    if any(not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0 for sequence in sequences):
        reasons.add(AUDIT_CHAIN_INVALID)
    elif sequences and len(set(sequences)) != len(sequences):
        reasons.add(AUDIT_CHAIN_INVALID)
    elif sequences and sequences != list(range(min(sequences), max(sequences) + 1)):
        reasons.add(AUDIT_CHAIN_INVALID)
    terminal_values: set[str] = set()
    for record in records:
        terminal_state = record.get("terminal_state")
        result = record.get("result")
        if terminal_state is not None and result is not None and terminal_state != result:
            reasons.add(AUDIT_CHAIN_INVALID)
        for value in (terminal_state, result):
            if value in {"SUCCESS", "FAILED"}:
                terminal_values.add(value)
    if len(terminal_values) > 1:
        reasons.add(AUDIT_CHAIN_INVALID)
    if time.monotonic_ns() >= deadline_ns:
        reasons.add(AUDIT_TIMEOUT)
    next_offsets.sort(key=lambda item: item["file_name"])
    consumed.sort(key=lambda item: (item["file_name"], item["offset"], item["record_sha256"]))
    source_sha256 = canonical_sha256(consumed)
    if AUDIT_TIMEOUT in reasons:
        return _failure_envelope(invocation, ObservationCompleteness.TIMED_OUT, AUDIT_TIMEOUT, started_at_us, utc_now_us())
    if AUDIT_CURSOR_UNMATCHED in reasons or AUDIT_CURSOR_AMBIGUOUS in reasons:
        completeness = ObservationCompleteness.PARTIAL
    elif reasons:
        completeness = ObservationCompleteness.PARTIAL
    else:
        completeness = ObservationCompleteness.COMPLETE
    if completeness is ObservationCompleteness.COMPLETE and not records:
        completeness = ObservationCompleteness.MISSING
    if completeness is ObservationCompleteness.MISSING:
        return _failure_envelope(invocation, completeness, AUDIT_TAG_NOT_FOUND, started_at_us, utc_now_us())
    if completeness is ObservationCompleteness.PARTIAL:
        return _audit_envelope(invocation, records, next_offsets, counters, source_sha256, started_at_us, utc_now_us(), completeness=completeness, reason_codes=tuple(sorted(reasons)))
    return _audit_envelope(invocation, records, next_offsets, counters, source_sha256, started_at_us, utc_now_us())


def child_main(input_path: str, output_path: str) -> int:
    try:
        input_file = Path(input_path)
        if input_file.stat().st_size > OBSERVER_JSON_MAX_BYTES:
            return 3
        invocation = parse_observer_json(input_file.read_bytes(), AuditLogObserverInvocation)
        envelope = _run_child(invocation, utc_now_us=_now_us)
        _write_atomic(Path(output_path), envelope.model_dump_json().encode("utf-8"))
        return 0
    except Exception:
        return 3


def _validate_output_binding(invocation: AuditLogObserverInvocation, envelope: ObservationEnvelope) -> None:
    if envelope.observer_id != invocation.spec.observer_id or envelope.observer_type is not ObserverType.STRUCTURED_AUDIT_LOG:
        raise ValueError("audit output binding mismatch")
    if envelope.phase is not invocation.phase or envelope.target_id != invocation.spec.target.target_id:
        raise ValueError("audit output phase or target mismatch")
    if envelope.correlation != invocation.correlation:
        raise ValueError("audit output correlation mismatch")
    if envelope.window.phase is not invocation.phase or envelope.window.timeout_us != invocation.spec.budget.timeout_us:
        raise ValueError("audit output window mismatch")
    if envelope.provenance is not None:
        if envelope.provenance.target_id != invocation.spec.target.target_id or envelope.provenance.provenance_type is not ProvenanceType.AUDIT_LOG_WINDOW:
            raise ValueError("audit output provenance mismatch")


def run_audit_log_observer(
    spec: ObserverSpec,
    correlation: Correlation,
    phase: ObservationPhase,
    *,
    attempt_dir: Path,
    parent_environ: Mapping[str, str] | None = None,
    python_executable: str | None = None,
    start_cursors: tuple[AuditLogStartCursor, ...] = (),
) -> AuditLogObserverResult:
    """在固定日志根和起始游标内读取有界审计事件，并形成不可越权的观察摘要。"""

    invocation = AuditLogObserverInvocation(spec=spec, correlation=correlation, phase=phase, start_cursors=start_cursors)
    attempt_root = attempt_dir.resolve()
    attempt_root.mkdir(parents=True, exist_ok=True)
    input_path = attempt_root / "audit-observer-input.json"
    output_path = attempt_root / "audit-observer-output.json"
    temporary_paths = (input_path.with_name(f".{input_path.name}.tmp"), output_path.with_name(f".{output_path.name}.tmp"))
    parent_started_at_us = _now_us()
    parent_deadline_ns = time.monotonic_ns() + spec.budget.timeout_us * 1_000
    try:
        source_name = _secret_name(spec)
        environment = minimal_process_environment(parent_environ if parent_environ is not None else os.environ, secret_names=(source_name,))
        _write_atomic(input_path, invocation.model_dump_json().encode("utf-8"))
        command = [python_executable or sys.executable, "-B", "-m", "product.backend.infra.observers.audit_log", "--input", str(input_path), "--output", str(output_path)]
        try:
            process = subprocess.Popen(command, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            return AuditLogObserverResult(None, _execution_error(spec))
        try:
            remaining = (parent_deadline_ns - time.monotonic_ns()) / 1_000_000_000
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, 0)
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=_PROCESS_REAP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                pass
            envelope = _failure_envelope(invocation, ObservationCompleteness.TIMED_OUT, AUDIT_TIMEOUT, parent_started_at_us, _now_us())
            return AuditLogObserverResult(envelope, evaluate_observer_outcome(envelope, required=spec.required))
        if process.returncode != 0 or not output_path.is_file():
            return AuditLogObserverResult(None, _execution_error(spec))
        if output_path.stat().st_size > OBSERVER_JSON_MAX_BYTES:
            return AuditLogObserverResult(None, _execution_error(spec))
        payload = output_path.read_bytes()
        try:
            envelope = parse_observer_json(payload, ObservationEnvelope)
            _validate_output_binding(invocation, envelope)
        except (OSError, ValueError):
            return AuditLogObserverResult(None, _execution_error(spec))
        return AuditLogObserverResult(envelope, evaluate_observer_outcome(envelope, required=spec.required))
    finally:
        for path in (input_path, output_path, *temporary_paths):
            path.unlink(missing_ok=True)

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    return child_main(args.input, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
