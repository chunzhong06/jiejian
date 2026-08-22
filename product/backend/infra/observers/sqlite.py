# =============================================================================
# Runner 隔离域只读 SQLite 观察器
#
# 只允许预注册的 resource-state 查询。父进程仅传递最小环境和无秘密调用，
# 子进程以 SQLite URI mode=ro 及 query_only 读取，并把结果交回严格  envelope。
# =============================================================================

from __future__ import annotations

import json
import os
import subprocess
from product.backend.infra.runtime.process_tree import release_process_tree, terminate_process_tree
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from product.backend.infra.runtime.process_environment import spawn_python_module
from product.protocols.observer import CausalityStatus, Correlation, ObservationCompleteness, ObservationEnvelope, ObservationPhase, ObservationProvenance, ObservationWindow, ObserverInvocation, ObserverOutcome, ObserverOutcomeStatus, ObserverSpec, ObserverType, OBSERVER_JSON_MAX_BYTES, ProvenanceType, build_normalized_state, canonical_sha256, evaluate_observer_outcome, parse_observer_json


SQLITE_OBSERVER_PROCESS_ERROR = "SQLITE_OBSERVER_PROCESS_ERROR"
SQLITE_QUERY_TIMEOUT = "SQLITE_QUERY_TIMEOUT"
SQLITE_SECRET_MISSING = "SQLITE_SECRET_MISSING"
SQLITE_UNAVAILABLE = "SQLITE_UNAVAILABLE"
SQLITE_QUERY_UNSUPPORTED = "SQLITE_QUERY_UNSUPPORTED"
SQLITE_QUERY_ERROR = "SQLITE_QUERY_ERROR"
SQLITE_ROW_LIMIT = "SQLITE_ROW_LIMIT"
SQLITE_BYTE_LIMIT = "SQLITE_BYTE_LIMIT"
_QUERY_TEMPLATE_ID = "resource-state"
_TABLE_OR_VIEW = "resource_state"
_QUERY = (
    "SELECT resource_id, workflow_state, value "
    "FROM resource_state WHERE resource_id = ? "
    "ORDER BY resource_id, workflow_state, value"
)
_PROCESS_REAP_TIMEOUT_SECONDS = 1.0


@dataclass(frozen=True)
class SqliteObserverResult:
    envelope: ObservationEnvelope | None
    outcome: ObserverOutcome


def _now_us() -> int:
    return time.time_ns() // 1_000


def _deadline_reached(deadline_ns: int) -> bool:
    return time.monotonic_ns() >= deadline_ns


def _secret_name(spec: ObserverSpec) -> str:
    locator = spec.target.locator
    if not hasattr(locator, "database_secret_ref"):
        raise ValueError("sqlite observer requires a database secret reference")
    return locator.database_secret_ref.removeprefix("env:")


def _write_atomic(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_output_binding(invocation: ObserverInvocation, envelope: ObservationEnvelope) -> None:
    locator = invocation.spec.target.locator
    if envelope.observer_id != invocation.spec.observer_id:
        raise ValueError("observer output is bound to a different observer")
    if envelope.observer_type is not ObserverType.READ_ONLY_SQLITE:
        raise ValueError("observer output type does not match SQLite observer")
    if envelope.phase is not invocation.phase or envelope.target_id != invocation.spec.target.target_id:
        raise ValueError("observer output phase or target does not match invocation")
    if envelope.correlation != invocation.correlation:
        raise ValueError("observer output correlation does not match invocation")
    if envelope.window.phase is not invocation.phase or envelope.window.timeout_us != invocation.spec.budget.timeout_us:
        raise ValueError("observer output window does not match invocation budget")
    if envelope.provenance is not None:
        if envelope.provenance.target_id != invocation.spec.target.target_id:
            raise ValueError("observer output provenance target does not match invocation")
        if envelope.provenance.query_template_id != locator.query_template_id:
            raise ValueError("observer output provenance query does not match invocation")


def _failure_envelope(
    invocation: ObserverInvocation,
    completeness: ObservationCompleteness,
    reason: str,
    started_at_us: int,
    finished_at_us: int,
) -> ObservationEnvelope:
    budget = invocation.spec.budget.timeout_us
    finished = min(max(finished_at_us, started_at_us), started_at_us + budget)
    return ObservationEnvelope(
        observer_id=invocation.spec.observer_id,
        observer_type=ObserverType.READ_ONLY_SQLITE,
        phase=invocation.phase,
        target_id=invocation.spec.target.target_id,
        window=ObservationWindow(
            phase=invocation.phase,
            started_at_us=started_at_us,
            finished_at_us=finished,
            timeout_us=budget,
        ),
        correlation=invocation.correlation,
        causality=CausalityStatus.UNVERIFIED,
        completeness=completeness,
        reason_codes=(reason,),
    )


def _complete_envelope(
    invocation: ObserverInvocation,
    state_payload: Mapping[str, object],
    started_at_us: int,
    finished_at_us: int,
    *,
    known_secrets: tuple[str, ...],
) -> ObservationEnvelope:
    state = build_normalized_state(state_payload, known_secrets=known_secrets)
    return ObservationEnvelope(
        observer_id=invocation.spec.observer_id,
        observer_type=ObserverType.READ_ONLY_SQLITE,
        phase=invocation.phase,
        target_id=invocation.spec.target.target_id,
        window=ObservationWindow(
            phase=invocation.phase,
            started_at_us=started_at_us,
            finished_at_us=min(finished_at_us, started_at_us + invocation.spec.budget.timeout_us),
            timeout_us=invocation.spec.budget.timeout_us,
        ),
        correlation=invocation.correlation,
        causality=CausalityStatus.CORRELATED,
        completeness=ObservationCompleteness.COMPLETE,
        state=state,
        provenance=ObservationProvenance(
            provenance_type=ProvenanceType.SQLITE_QUERY,
            adapter_version="sqlite-observer-1",
            target_id=invocation.spec.target.target_id,
            query_template_id=_QUERY_TEMPLATE_ID,
            source_sha256=canonical_sha256(state.canonical_data),
        ),
    )


def _run_child(invocation: ObserverInvocation, *, utc_now_us: Callable[[], int]) -> ObservationEnvelope:
    import sqlite3
    from urllib.parse import unquote, urlsplit

    started_at_us = utc_now_us()
    locator = invocation.spec.target.locator
    if (
        invocation.spec.observer_type is not ObserverType.READ_ONLY_SQLITE
        or locator.locator_type != "READ_ONLY_SQLITE"
        or locator.query_template_id != _QUERY_TEMPLATE_ID
        or locator.table_or_view != _TABLE_OR_VIEW
    ):
        return _failure_envelope(invocation, ObservationCompleteness.UNSUPPORTED, SQLITE_QUERY_UNSUPPORTED, started_at_us, utc_now_us())

    source = os.environ.get(_secret_name(invocation.spec))
    if not source:
        return _failure_envelope(invocation, ObservationCompleteness.MISSING, SQLITE_SECRET_MISSING, started_at_us, utc_now_us())
    if "\x00" in source:
        return _failure_envelope(invocation, ObservationCompleteness.MISSING, SQLITE_UNAVAILABLE, started_at_us, utc_now_us())

    def is_non_local_path(value: str) -> bool:
        return value.startswith(("\\\\", "//", "\\??\\", "\\Device\\", "\\\\?\\", "\\\\.\\"))

    if source.startswith("file:"):
        parsed = urlsplit(source)
        path_value = unquote(parsed.path)
        if parsed.scheme != "file" or parsed.netloc or parsed.query or parsed.fragment or not path_value:
            return _failure_envelope(invocation, ObservationCompleteness.MISSING, SQLITE_UNAVAILABLE, started_at_us, utc_now_us())
        if os.name == "nt" and len(path_value) > 2 and path_value[0] == "/" and path_value[2] == ":":
            path_value = path_value[1:]
        if is_non_local_path(path_value):
            return _failure_envelope(invocation, ObservationCompleteness.MISSING, SQLITE_UNAVAILABLE, started_at_us, utc_now_us())
        source_path = Path(path_value)
    else:
        if is_non_local_path(source):
            return _failure_envelope(invocation, ObservationCompleteness.MISSING, SQLITE_UNAVAILABLE, started_at_us, utc_now_us())
        source_path = Path(source)
    if not source_path.is_absolute():
        return _failure_envelope(invocation, ObservationCompleteness.MISSING, SQLITE_UNAVAILABLE, started_at_us, utc_now_us())

    try:
        uri = f"file:{source_path.resolve().as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=0)
    except (OSError, sqlite3.Error):
        return _failure_envelope(invocation, ObservationCompleteness.MISSING, SQLITE_UNAVAILABLE, started_at_us, utc_now_us())

    deadline_ns = time.monotonic_ns() + invocation.spec.budget.timeout_us * 1_000
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.set_progress_handler(lambda: int(_deadline_reached(deadline_ns)), 1_000)
        rows = connection.execute(_QUERY, (invocation.correlation.resource_id,)).fetchmany(invocation.spec.budget.max_rows + 1)
        if _deadline_reached(deadline_ns):
            return _failure_envelope(invocation, ObservationCompleteness.TIMED_OUT, SQLITE_QUERY_TIMEOUT, started_at_us, utc_now_us())
    except sqlite3.OperationalError as error:
        if _deadline_reached(deadline_ns) or "interrupt" in str(error).lower():
            return _failure_envelope(invocation, ObservationCompleteness.TIMED_OUT, SQLITE_QUERY_TIMEOUT, started_at_us, utc_now_us())
        return _failure_envelope(invocation, ObservationCompleteness.ERROR, SQLITE_QUERY_ERROR, started_at_us, utc_now_us())
    except sqlite3.Error:
        return _failure_envelope(invocation, ObservationCompleteness.ERROR, SQLITE_QUERY_ERROR, started_at_us, utc_now_us())
    finally:
        connection.close()

    normalized_rows = sorted(
        ({"resource_id": str(row[0]), "workflow_state": str(row[1]), "value": str(row[2])} for row in rows),
        key=lambda row: (row["resource_id"], row["workflow_state"], row["value"]),
    )
    truncated = len(normalized_rows) > invocation.spec.budget.max_rows
    state_rows = normalized_rows[: invocation.spec.budget.max_rows]
    payload = {
        "row_count": len(normalized_rows),
        "rows": state_rows,
        "truncated": truncated,
    }
    try:
        state = build_normalized_state(payload, known_secrets=(source,))
    except ValueError:
        return _failure_envelope(invocation, ObservationCompleteness.PARTIAL, SQLITE_BYTE_LIMIT, started_at_us, utc_now_us())
    if state.byte_count > invocation.spec.budget.max_bytes:
        return _failure_envelope(invocation, ObservationCompleteness.PARTIAL, SQLITE_BYTE_LIMIT, started_at_us, utc_now_us())
    if _deadline_reached(deadline_ns):
        return _failure_envelope(invocation, ObservationCompleteness.TIMED_OUT, SQLITE_QUERY_TIMEOUT, started_at_us, utc_now_us())
    if truncated:
        return ObservationEnvelope(
            observer_id=invocation.spec.observer_id,
            observer_type=ObserverType.READ_ONLY_SQLITE,
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
            completeness=ObservationCompleteness.PARTIAL,
            state=state,
            provenance=ObservationProvenance(
                provenance_type=ProvenanceType.SQLITE_QUERY,
                adapter_version="sqlite-observer-1",
                target_id=invocation.spec.target.target_id,
                query_template_id=_QUERY_TEMPLATE_ID,
                source_sha256=canonical_sha256(state.canonical_data),
            ),
            reason_codes=(SQLITE_ROW_LIMIT,),
        )
    return _complete_envelope(invocation, payload, started_at_us, utc_now_us(), known_secrets=(source,))


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


def _execution_error(spec: ObserverSpec) -> ObserverOutcome:
    return ObserverOutcome(
        observer_id=spec.observer_id,
        required=spec.required,
        status=ObserverOutcomeStatus.EXECUTION_ERROR,
        reason_codes=(SQLITE_OBSERVER_PROCESS_ERROR,),
    )


def run_sqlite_observer(
    spec: ObserverSpec,
    correlation: Correlation,
    phase: ObservationPhase,
    *,
    attempt_dir: Path,
    parent_environ: Mapping[str, str] | None = None,
    python_executable: str | None = None,
) -> SqliteObserverResult:
    """通过只读 SQLite 子进程查询授权资源状态，并严格重验输出绑定。"""

    invocation = ObserverInvocation(spec=spec, correlation=correlation, phase=phase)
    attempt_root = attempt_dir.resolve()
    attempt_root.mkdir(parents=True, exist_ok=True)
    input_path = attempt_root / "sqlite-observer-input.json"
    output_path = attempt_root / "sqlite-observer-output.json"
    temporary_paths = (
        input_path.with_name(f".{input_path.name}.tmp"),
        output_path.with_name(f".{output_path.name}.tmp"),
    )
    source = None
    parent_started_at_us = _now_us()
    parent_deadline_ns = time.monotonic_ns() + spec.budget.timeout_us * 1_000
    try:
        if parent_environ is not None:
            source = parent_environ.get(_secret_name(spec))
        _write_atomic(input_path, invocation.model_dump_json().encode("utf-8"))
        source_name = _secret_name(spec)
        environment = dict(parent_environ if parent_environ is not None else os.environ)
        environment.setdefault("JIEJIAN_VAR_DIR", str(attempt_root))
        command = ["product.backend.infra.observers.sqlite", "--input", str(input_path), "--output", str(output_path)]
        try:
            process = spawn_python_module(
                environment,
                command[0],
                *command[1:],
                secret_names=(source_name,),
                cwd=attempt_root,
                python_executable=python_executable,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            return SqliteObserverResult(None, _execution_error(spec))
        try:
            remaining_seconds = (parent_deadline_ns - time.monotonic_ns()) / 1_000_000_000
            if remaining_seconds <= 0:
                raise subprocess.TimeoutExpired(command, 0)
            process.wait(timeout=remaining_seconds)
        except subprocess.TimeoutExpired:
            terminate_process_tree(process, _PROCESS_REAP_TIMEOUT_SECONDS)
            envelope = _failure_envelope(invocation, ObservationCompleteness.TIMED_OUT, SQLITE_QUERY_TIMEOUT, parent_started_at_us, _now_us())
            return SqliteObserverResult(envelope, evaluate_observer_outcome(envelope, required=spec.required))
        if process.returncode != 0 or not output_path.is_file():
            return SqliteObserverResult(None, _execution_error(spec))
        try:
            if output_path.stat().st_size > OBSERVER_JSON_MAX_BYTES:
                return SqliteObserverResult(None, _execution_error(spec))
            payload = output_path.read_bytes()
            envelope = parse_observer_json(payload, ObservationEnvelope, known_secrets=((source,) if source else ()))
            _validate_output_binding(invocation, envelope)
        except (OSError, ValueError):
            return SqliteObserverResult(None, _execution_error(spec))
        return SqliteObserverResult(envelope, evaluate_observer_outcome(envelope, required=spec.required))
    finally:
        if "process" in locals():
            release_process_tree(process)
        for path in (input_path, output_path):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        for path in temporary_paths:
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
