from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from product.protocols import (
    AuditLogScanBudget,
    AuditLogStartCursor,
    Correlation,
    ObservationCompleteness,
    ObservationPhase,
    ObserverBudget,
    ObserverOutcomeStatus,
    ObserverSpec,
    ObserverTarget,
    ObserverType,
    StructuredAuditLogLocator,
)
from product.backend.infra.observers.audit_log import (
    AUDIT_FILE_CHANGED,
    AUDIT_LINE_BYTES_LIMIT,
    AUDIT_RECORD_LIMIT,
    AUDIT_CHAIN_INVALID,
    AUDIT_DUPLICATE_KEY,
    AUDIT_EVENT_CONFLICT,
    AUDIT_INVALID_UTF8,
    AUDIT_OFFSET_PAST_END,
    AUDIT_PARTIAL_LINE,
    AUDIT_TAG_NOT_FOUND,
    run_audit_log_observer,
)
import product.backend.infra.observers.audit_log as audit_module


PYTHON = sys.executable
FIELDS = (
    "event_id",
    "case_tag",
    "task_id",
    "event_type",
    "sequence",
    "resource_id",
    "terminal_state",
    "result",
    "effect",
    "value",
)


def _spec(*, phases: tuple[ObservationPhase, ...] = (ObservationPhase.AFTER,), max_files: int = 4, max_lines: int = 100, max_line_bytes: int = 4096, max_rows: int = 100, timeout_us: int = 5_000_000) -> ObserverSpec:
    return ObserverSpec(
        observer_id="audit_observer",
        observer_type=ObserverType.STRUCTURED_AUDIT_LOG,
        target=ObserverTarget(
            target_id="audit-window",
            locator=StructuredAuditLogLocator(
                authorized_root_ref="env:AUDIT_ROOT",
                relative_file_pattern="audit.jsonl",
                allowed_fields=FIELDS,
                scan_budget=AuditLogScanBudget(max_files=max_files, max_lines=max_lines, max_line_bytes=max_line_bytes),
            ),
            normalization_id="audit-window",
            normalization_version="1.0",
        ),
        phases=phases,
        required=True,
        budget=ObserverBudget(timeout_us=timeout_us, max_rows=max_rows, max_bytes=32_768),
    )


def _record(case: str, task: str, event_id: str, event_type: str, sequence: int, *, terminal: str | None = None, resource: str = "resource-a", **extra: object) -> dict[str, object]:
    record: dict[str, object] = {
        "event_id": event_id,
        "case_tag": case,
        "task_id": task,
        "event_type": event_type,
        "sequence": sequence,
        "resource_id": resource,
    }
    if terminal is not None:
        record["terminal_state"] = terminal
    record.update(extra)
    return record


def _write(path: Path, records: list[dict[str, object]], *, trailing_newline: bool = True) -> int:
    data = b"".join(json.dumps(record, sort_keys=True, separators=(",", ":")).encode() + (b"\n" if trailing_newline else b"") for record in records)
    path.write_bytes(data)
    return len(data)


def _observe(root: Path, *, spec: ObserverSpec | None = None, phase: ObservationPhase = ObservationPhase.AFTER, cursors: tuple[AuditLogStartCursor, ...] = ()):
    return run_audit_log_observer(
        spec or _spec(),
        Correlation(case_id="case-1", resource_id="resource-a", request_marker="case-1"),
        phase,
        attempt_dir=root / "attempt",
        parent_environ={
            **os.environ,
            "AUDIT_ROOT": str(root),
            "UNRELATED_ROOT": "D:/private/audit",
        },
        python_executable=PYTHON,
        start_cursors=cursors,
    )


def test_audit_observer_reads_tagged_rotated_window_and_is_stable(tmp_path: Path) -> None:
    records = [
        _record("other-case", "task-other", "other", "TASK_STATE", 1, terminal="SUCCESS", resource="resource-b"),
        _record("case-1", "task-case-1", "request", "REQUEST", 1),
        _record("case-1", "task-case-1", "queued", "TASK_STATE", 2),
        _record("case-1", "task-case-1", "success", "TASK_STATE", 3, terminal="SUCCESS"),
        _record("case-1", "task-case-1", "effect", "SIDE_EFFECT", 4, effect="APPLIED", value="changed"),
    ]
    active = tmp_path / "audit.jsonl"
    rotated = tmp_path / "audit.1.jsonl"
    _write(rotated, records[:2])
    _write(active, records[2:])
    first = _observe(tmp_path)
    second = _observe(tmp_path)
    assert first.outcome.status is ObserverOutcomeStatus.AVAILABLE
    assert first.envelope is not None and second.envelope is not None
    assert first.envelope.completeness is ObservationCompleteness.COMPLETE
    assert first.envelope.causality.value == "CORRELATED"
    assert first.envelope.state == second.envelope.state
    assert first.envelope.provenance is not None
    assert first.envelope.provenance.target_id == "audit-window"
    assert first.envelope.provenance.query_template_id is None
    assert str(tmp_path) not in first.envelope.model_dump_json()
    assert "UNRELATED_ROOT" not in first.envelope.model_dump_json()


def test_audit_observer_complete_does_not_require_task_terminal_state(tmp_path: Path) -> None:
    _write(
        tmp_path / "audit.jsonl",
        [
            _record("case-1", "task-case-1", "request", "REQUEST", 1),
            _record("case-1", "task-case-1", "queued", "TASK_STATE", 2, value="QUEUED"),
        ],
    )
    result = _observe(tmp_path)
    assert result.outcome.status is ObserverOutcomeStatus.AVAILABLE
    assert result.envelope is not None
    assert result.envelope.completeness is ObservationCompleteness.COMPLETE
    assert result.envelope.causality.value == "CORRELATED"


def test_audit_observer_offset_and_eventual_are_explicit_and_bounded(tmp_path: Path) -> None:
    first = _record("case-1", "task-case-1", "old", "REQUEST", 1)
    path = tmp_path / "audit.jsonl"
    offset = _write(path, [first])
    _write(path, [first, _record("case-1", "task-case-1", "success", "TASK_STATE", 2, terminal="SUCCESS"), _record("case-1", "task-case-1", "effect", "SIDE_EFFECT", 3, effect="APPLIED")])
    anchor = path.read_bytes()[:offset]
    cursor = AuditLogStartCursor(file_name="audit.jsonl", offset=offset, anchor_start=0, anchor_length=len(anchor), anchor_sha256=hashlib.sha256(anchor).hexdigest())
    result = _observe(tmp_path, spec=_spec(phases=(ObservationPhase.EVENTUAL,)), phase=ObservationPhase.EVENTUAL, cursors=(cursor,))
    assert result.outcome.status is ObserverOutcomeStatus.AVAILABLE
    assert result.envelope is not None
    assert result.envelope.completeness is ObservationCompleteness.COMPLETE
    assert result.envelope.reason_codes == ()
    assert result.envelope.state is not None
    next_offsets = result.envelope.state.canonical_data["next_offsets"]
    assert next_offsets[0]["file_name"] == "audit.jsonl"

    with pytest.raises(ValueError):
        AuditLogStartCursor(file_name="audit.jsonl", offset=10_000)


def test_audit_observer_cursor_survives_rotation_without_rereading_old_records(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    first = _record("case-1", "task-case-1", "request", "REQUEST", 1)
    offset = _write(path, [first])
    anchor = path.read_bytes()[:offset]
    cursor = AuditLogStartCursor(file_name="audit.jsonl", offset=offset, anchor_start=0, anchor_length=len(anchor), anchor_sha256=hashlib.sha256(anchor).hexdigest())
    path.rename(tmp_path / "audit.1.jsonl")
    _write(path, [_record("case-1", "task-case-1", "task", "TASK_STATE", 2, value="QUEUED")])
    result = _observe(tmp_path, cursors=(cursor,))
    assert result.outcome.status is ObserverOutcomeStatus.AVAILABLE
    assert result.envelope is not None and result.envelope.state is not None
    assert [item["event_id"] for item in result.envelope.state.canonical_data["records"]] == ["task"]


def test_audit_observer_cursor_window_accepts_task_and_effect_without_request(tmp_path: Path) -> None:
    first = _record("case-1", "task-case-1", "request", "REQUEST", 1)
    path = tmp_path / "audit.jsonl"
    offset = _write(path, [first])
    tail = [
        _record("case-1", "task-case-1", "task", "TASK_STATE", 2, value="QUEUED"),
        _record("case-1", "task-case-1", "effect", "SIDE_EFFECT", 3, effect="APPLIED"),
    ]
    with path.open("ab") as handle:
        handle.write(b"".join(json.dumps(item, sort_keys=True, separators=(",", ":")).encode() + b"\n" for item in tail))
    anchor = path.read_bytes()[:offset]
    cursor = AuditLogStartCursor(file_name="audit.jsonl", offset=offset, anchor_start=0, anchor_length=len(anchor), anchor_sha256=hashlib.sha256(anchor).hexdigest())
    result = _observe(tmp_path, cursors=(cursor,))
    assert result.outcome.status is ObserverOutcomeStatus.AVAILABLE
    assert result.envelope is not None
    assert result.envelope.completeness is ObservationCompleteness.COMPLETE
    assert [item["event_type"] for item in result.envelope.state.canonical_data["records"]] == ["TASK_STATE", "SIDE_EFFECT"]


@pytest.mark.parametrize("kind", ["missing", "mismatch", "conflict", "partial", "invalid"])
def test_audit_observer_never_uses_time_or_resource_similarity(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "audit.jsonl"
    if kind == "missing":
        _write(path, [_record("other-case", "task-other", "other", "TASK_STATE", 1, terminal="SUCCESS")])
    elif kind == "mismatch":
        _write(path, [_record("case-1", "task-case-1", "bad", "TASK_STATE", 1, terminal="SUCCESS", resource="resource-b")])
    elif kind == "conflict":
        _write(path, [_record("case-1", "task-case-1", "same", "REQUEST", 1)])
        with path.open("ab") as handle:
            handle.write(json.dumps(_record("case-1", "task-case-1", "same", "REQUEST", 2)).encode() + b"\n")
    elif kind == "partial":
        _write(path, [_record("case-1", "task-case-1", "request", "REQUEST", 1)])
        with path.open("ab") as handle:
            handle.write(b'{"event_id":"tail","case_tag":"case-1"')
    else:
        path.write_bytes(b"\xef\xbb\xbf" + json.dumps(_record("case-1", "task-case-1", "request", "REQUEST", 1)).encode() + b"\n")
    result = _observe(tmp_path)
    assert result.outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    assert result.envelope is not None
    assert result.envelope.completeness in {ObservationCompleteness.MISSING, ObservationCompleteness.PARTIAL}
    if kind == "missing":
        assert AUDIT_TAG_NOT_FOUND in result.envelope.reason_codes
    if kind == "mismatch":
        assert AUDIT_CHAIN_INVALID in result.envelope.reason_codes
    if kind == "conflict":
        assert AUDIT_EVENT_CONFLICT in result.envelope.reason_codes
    if kind == "partial":
        assert AUDIT_PARTIAL_LINE in result.envelope.reason_codes
    if kind == "invalid":
        assert result.envelope.reason_codes


def test_audit_observer_rejects_nested_unallowed_and_invalid_utf8(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    path.write_bytes(json.dumps(_record("case-1", "task-case-1", "nested", "REQUEST", 1, payload={"x": 1})).encode() + b"\n" + b"\xff\n")
    result = _observe(tmp_path)
    assert result.outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    assert result.envelope is not None
    assert "AUDIT_EVENT_INVALID" in result.envelope.reason_codes
    assert AUDIT_INVALID_UTF8 in result.envelope.reason_codes


def test_audit_observer_budget_and_secret_environment_boundary(tmp_path: Path) -> None:
    _write(tmp_path / "audit.jsonl", [_record("case-1", "task-case-1", f"event-{index}", "REQUEST", index) for index in range(1, 8)])
    result = _observe(tmp_path, spec=_spec(max_lines=2))
    assert result.outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    assert result.envelope is not None
    assert "AUDIT_LINE_LIMIT" in result.envelope.reason_codes
    assert "D:/private/audit" not in result.envelope.model_dump_json()
    assert not (tmp_path / "attempt" / "audit-observer-input.json").exists()
    assert not (tmp_path / "attempt" / "audit-observer-output.json").exists()


def test_audit_observer_matching_record_limit_is_inconclusive(tmp_path: Path) -> None:
    _write(tmp_path / "audit.jsonl", [
        _record("case-1", "task-case-1", "first", "TASK_STATE", 1),
        _record("case-1", "task-case-1", "second", "SIDE_EFFECT", 2),
    ])
    result = _observe(tmp_path, spec=_spec(max_rows=1))
    assert result.outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    assert result.envelope is not None
    assert result.envelope.completeness is ObservationCompleteness.PARTIAL
    assert AUDIT_RECORD_LIMIT in result.envelope.reason_codes


def test_audit_observer_line_byte_limit_is_inconclusive(tmp_path: Path) -> None:
    _write(tmp_path / "audit.jsonl", [_record("case-1", "task-case-1", "wide", "TASK_STATE", 1, value="x" * 256)])
    result = _observe(tmp_path, spec=_spec(max_line_bytes=64))
    assert result.outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    assert result.envelope is not None
    assert result.envelope.completeness is ObservationCompleteness.PARTIAL
    assert AUDIT_LINE_BYTES_LIMIT in result.envelope.reason_codes


def test_audit_observer_child_deadline_is_timed_out_not_execution_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path / "audit.jsonl", [_record("case-1", "task-case-1", "event", "TASK_STATE", 1)])
    spec = _spec(timeout_us=1)
    invocation = audit_module.AuditLogObserverInvocation(
        spec=spec,
        correlation=Correlation(case_id="case-1", resource_id="resource-a", request_marker="case-1"),
        phase=ObservationPhase.AFTER,
    )
    monkeypatch.setenv("AUDIT_ROOT", str(tmp_path))
    calls = 0

    def expired_clock() -> int:
        nonlocal calls
        calls += 1
        return 0 if calls == 1 else 1_000

    monkeypatch.setattr(audit_module.time, "monotonic_ns", expired_clock)
    envelope = audit_module._run_child(invocation, utc_now_us=lambda: 100)
    assert envelope.completeness is ObservationCompleteness.TIMED_OUT
    assert audit_module.evaluate_observer_outcome(envelope, required=True).status is ObserverOutcomeStatus.INCONCLUSIVE


def test_audit_observer_parent_timeout_kills_reaps_and_cleans(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class HangingProcess:
        returncode = None

        def __init__(self) -> None:
            self.killed = False
            self.wait_timeouts: list[float | None] = []

        def wait(self, timeout: float | None = None) -> int:
            self.wait_timeouts.append(timeout)
            if not self.killed:
                raise subprocess.TimeoutExpired("audit", timeout)
            return 0

        def poll(self) -> int | None:
            return -9 if self.killed else None

        def terminate(self) -> None:
            return None

        def kill(self) -> None:
            self.killed = True

    process = HangingProcess()
    monkeypatch.setattr(audit_module.subprocess, "Popen", lambda *args, **kwargs: process)
    clock = iter((0, 500_000))
    monkeypatch.setattr(audit_module.time, "monotonic_ns", lambda: next(clock))
    result = _observe(tmp_path, spec=_spec(timeout_us=1_000))
    assert result.outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    assert result.envelope is not None
    assert result.envelope.completeness is ObservationCompleteness.TIMED_OUT
    assert process.killed
    assert len(process.wait_timeouts) == 4
    assert process.wait_timeouts[0] is not None and process.wait_timeouts[0] <= 0.001
    assert all(
        timeout is not None
        and 0 <= timeout <= audit_module._PROCESS_REAP_TIMEOUT_SECONDS
        for timeout in process.wait_timeouts[1:]
    )
    assert not list((tmp_path / "attempt").glob("audit-observer-*.json"))
    assert not list((tmp_path / "attempt").glob(".*audit-observer-*.tmp"))


def test_audit_observer_rejects_symlink_or_reparse_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outside = tmp_path.parent / "audit-outside.jsonl"
    _write(outside, [_record("case-1", "task-case-1", "outside", "TASK_STATE", 1)])
    link = tmp_path / "audit.jsonl"
    tmp_path.mkdir(exist_ok=True)
    try:
        link.symlink_to(outside)
    except OSError:
        monkeypatch.setattr(audit_module, "_is_reparse_or_symlink", lambda candidate: candidate == link)
    result = _observe(tmp_path)
    assert result.outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    assert result.envelope is not None
    assert result.envelope.completeness is not ObservationCompleteness.COMPLETE


def test_audit_observer_rejects_read_time_replacement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path / "audit.jsonl", [_record("case-1", "task-case-1", "event", "TASK_STATE", 1)])
    spec = _spec()
    invocation = audit_module.AuditLogObserverInvocation(
        spec=spec,
        correlation=Correlation(case_id="case-1", resource_id="resource-a", request_marker="case-1"),
        phase=ObservationPhase.AFTER,
    )
    monkeypatch.setenv("AUDIT_ROOT", str(tmp_path))
    real_fstat = audit_module.os.fstat
    calls = 0

    def replaced_fstat(fd: int) -> os.stat_result:
        nonlocal calls
        calls += 1
        result = real_fstat(fd)
        if calls == 2:
            fields = list(result)
            fields[6] += 1
            return os.stat_result(fields)
        return result

    monkeypatch.setattr(audit_module.os, "fstat", replaced_fstat)
    envelope = audit_module._run_child(invocation, utc_now_us=lambda: 100)
    assert envelope.completeness is ObservationCompleteness.PARTIAL
    assert AUDIT_FILE_CHANGED in envelope.reason_codes
    assert audit_module.evaluate_observer_outcome(envelope, required=True).status is ObserverOutcomeStatus.INCONCLUSIVE


def test_audit_observer_rejects_invalid_locator_and_subdirectory(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        StructuredAuditLogLocator(authorized_root_ref="env:AUDIT_ROOT", relative_file_pattern="**/*.jsonl", allowed_fields=FIELDS)
    with pytest.raises(ValueError):
        StructuredAuditLogLocator(authorized_root_ref="env:AUDIT_ROOT", relative_file_pattern="../audit.jsonl", allowed_fields=FIELDS)
    nested = tmp_path / "nested"
    nested.mkdir()
    _write(nested / "audit.jsonl", [_record("case-1", "task-case-1", "nested", "REQUEST", 1)])
    result = _observe(tmp_path)
    assert result.outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    assert result.envelope is not None
    assert AUDIT_TAG_NOT_FOUND in result.envelope.reason_codes
