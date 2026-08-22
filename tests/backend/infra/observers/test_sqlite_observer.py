from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import (
    Correlation,
    CausalityStatus,
    ObservationCompleteness,
    ObservationPhase,
    ObservationProvenance,
    ObservationWindow,
    ObserverBudget,
    ObserverOutcomeStatus,
    ObserverInvocation,
    ObserverSpec,
    ObserverTarget,
    ObserverType,
    ProvenanceType,
    SqliteQueryLocator,
)
from product.protocols.observer import OBSERVER_JSON_MAX_BYTES
from product.backend.infra.observers.sqlite import (
    SQLITE_BYTE_LIMIT,
    SQLITE_QUERY_UNSUPPORTED,
    SQLITE_ROW_LIMIT,
    SQLITE_SECRET_MISSING,
    SQLITE_UNAVAILABLE,
    run_sqlite_observer,
)
import product.backend.infra.observers.sqlite as sqlite_observer


PYTHON = sys.executable


def _spec(*, timeout_us: int = 5_000_000, max_rows: int = 10, max_bytes: int = 4096, template: str = "resource-state", table: str = "resource_state") -> ObserverSpec:
    return ObserverSpec(
        observer_id="sqlite_observer",
        observer_type=ObserverType.READ_ONLY_SQLITE,
        target=ObserverTarget(
            target_id="sqlite_state",
            locator=SqliteQueryLocator(
                query_template_id=template,
                table_or_view=table,
                database_secret_ref="env:DB_SECRET",
            ),
            normalization_id="resource-state",
            normalization_version="1.0",
        ),
        phases=(ObservationPhase.AFTER,),
        required=True,
        budget=ObserverBudget(timeout_us=timeout_us, max_rows=max_rows, max_bytes=max_bytes),
    )


def _database(path: Path, rows: list[tuple[str, str, str]]) -> None:
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE resource_state (resource_id TEXT, workflow_state TEXT, value TEXT)")
    connection.executemany("INSERT INTO resource_state VALUES (?, ?, ?)", rows)
    connection.commit()
    connection.close()


def _observe(tmp_path: Path, db_path: Path, spec: ObserverSpec | None = None):
    return run_sqlite_observer(
        spec or _spec(),
        Correlation(case_id="case-1", resource_id="document", request_marker="case-1"),
        ObservationPhase.AFTER,
        attempt_dir=tmp_path / "attempt",
        parent_environ={
            **os.environ,
            "DB_SECRET": str(db_path),
            "OTHER_SECRET": "must-not-propagate",
        },
        python_executable=PYTHON,
    )


def test_sqlite_observer_is_read_only_and_normalizes_row_order(tmp_path: Path) -> None:
    first = tmp_path / "first.db"
    second = tmp_path / "second.db"
    rows = [("document", "APPROVED", "safe"), ("document", "DRAFT", "draft")]
    _database(first, rows)
    _database(second, list(reversed(rows)))
    before = hashlib.sha256(first.read_bytes()).hexdigest()
    result = _observe(tmp_path / "first-run", first)
    reordered = _observe(tmp_path / "second-run", second)
    assert result.outcome.status is ObserverOutcomeStatus.AVAILABLE
    assert result.envelope is not None and reordered.envelope is not None
    assert result.envelope.state == reordered.envelope.state
    assert hashlib.sha256(first.read_bytes()).hexdigest() == before
    assert result.envelope.provenance is not None
    assert str(first) not in result.envelope.model_dump_json()

    changed = tmp_path / "changed.db"
    _database(changed, [("document", "APPROVED", "changed")])
    changed_result = _observe(tmp_path / "changed-run", changed)
    assert changed_result.envelope is not None
    assert changed_result.envelope.state is not None and result.envelope.state is not None
    assert changed_result.envelope.state.canonical_sha256 != result.envelope.state.canonical_sha256


def test_sqlite_observer_rejects_unregistered_query_boundary(tmp_path: Path) -> None:
    db = tmp_path / "state.db"
    _database(db, [("document", "DRAFT", "safe")])
    result = _observe(tmp_path / "unsupported", db, _spec(template="arbitrary-sql"))
    assert result.envelope is not None
    assert result.envelope.completeness is ObservationCompleteness.UNSUPPORTED
    assert result.envelope.reason_codes == (SQLITE_QUERY_UNSUPPORTED,)
    assert result.outcome.status is ObserverOutcomeStatus.INCONCLUSIVE


@pytest.mark.parametrize(
    ("spec", "reason"),
    [(_spec(max_rows=1), SQLITE_ROW_LIMIT), (_spec(max_bytes=64), SQLITE_BYTE_LIMIT)],
)
def test_sqlite_observer_budget_is_inconclusive(tmp_path: Path, spec: ObserverSpec, reason: str) -> None:
    db = tmp_path / "state.db"
    _database(db, [("document", "DRAFT", "a"), ("document", "APPROVED", "b")])
    result = _observe(tmp_path / reason.lower(), db, spec)
    assert result.envelope is not None
    assert result.envelope.completeness is ObservationCompleteness.PARTIAL
    assert reason in result.envelope.reason_codes
    assert result.outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    if reason == SQLITE_ROW_LIMIT:
        assert result.envelope.provenance is not None
        assert result.envelope.provenance.target_id == "sqlite_state"
        assert result.envelope.provenance.query_template_id == "resource-state"
        assert result.envelope.state is not None
    else:
        assert result.envelope.provenance is None


def test_sqlite_observer_secret_missing_and_child_failure_are_not_safety_results(tmp_path: Path) -> None:
    missing = run_sqlite_observer(
        _spec(),
        Correlation(case_id="case-1", resource_id="document", request_marker="case-1"),
        ObservationPhase.AFTER,
        attempt_dir=tmp_path / "missing",
        parent_environ={},
        python_executable=PYTHON,
    )
    assert missing.envelope is not None
    assert missing.envelope.completeness is ObservationCompleteness.MISSING
    assert missing.envelope.reason_codes == (SQLITE_SECRET_MISSING,)
    assert missing.envelope.provenance is None
    assert missing.outcome.status is ObserverOutcomeStatus.INCONCLUSIVE

    unavailable = _observe(tmp_path / "unavailable", tmp_path / "missing.db")
    assert unavailable.envelope is not None
    assert unavailable.envelope.completeness is ObservationCompleteness.MISSING
    assert unavailable.outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
    assert unavailable.envelope.provenance is None

    crashed = run_sqlite_observer(
        _spec(),
        Correlation(case_id="case-1", resource_id="document", request_marker="case-1"),
        ObservationPhase.AFTER,
        attempt_dir=tmp_path / "crash",
        parent_environ={"DB_SECRET": "C:\\private\\source.db"},
        python_executable=r"C:\missing-python.exe",
    )
    assert crashed.envelope is None
    assert crashed.outcome.status is ObserverOutcomeStatus.EXECUTION_ERROR
    assert not list((tmp_path / "crash").glob("sqlite-observer-*.json"))


def test_supervisor_passes_only_the_referenced_secret_and_no_query_text(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class FailedProcess:
        returncode = 7

        def poll(self) -> int:
            return self.returncode

        def wait(self, **kwargs: object) -> None:
            return None

    def fake_popen(command: list[str], **kwargs: object) -> FailedProcess:
        captured["command"] = command
        captured["env"] = kwargs["env"]
        return FailedProcess()

    monkeypatch.setattr(sqlite_observer.subprocess, "Popen", fake_popen)
    result = run_sqlite_observer(
        _spec(),
        Correlation(case_id="case-1", resource_id="document", request_marker="case-1"),
        ObservationPhase.AFTER,
        attempt_dir=tmp_path / "supervisor",
        parent_environ={"DB_SECRET": "opaque-db-source", "OTHER_SECRET": "must-not-propagate"},
        python_executable=PYTHON,
    )
    assert result.envelope is None
    assert result.outcome.status is ObserverOutcomeStatus.EXECUTION_ERROR
    assert captured["env"]["DB_SECRET"] == "opaque-db-source"
    assert "OTHER_SECRET" not in captured["env"]
    assert "opaque-db-source" not in " ".join(captured["command"])
    assert "SELECT" not in " ".join(captured["command"])


def test_supervisor_rejects_oversized_output_before_reading(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class Process:
        returncode = 0

        def poll(self) -> int:
            return self.returncode

        def wait(self, **kwargs: object) -> None:
            return None

    output_reads = 0
    original_read_bytes = Path.read_bytes

    def guarded_read_bytes(path: Path) -> bytes:
        nonlocal output_reads
        if path.name == "sqlite-observer-output.json":
            output_reads += 1
            raise AssertionError("oversized observer output must be rejected before read_bytes")
        return original_read_bytes(path)

    def fake_popen(command: list[str], **kwargs: object) -> Process:
        Path(command[-1]).write_bytes(b"x" * (OBSERVER_JSON_MAX_BYTES + 1))
        return Process()

    monkeypatch.setattr(sqlite_observer.Path, "read_bytes", guarded_read_bytes)
    monkeypatch.setattr(sqlite_observer.subprocess, "Popen", fake_popen)
    result = run_sqlite_observer(
        _spec(),
        Correlation(case_id="case-1", resource_id="document", request_marker="case-1"),
        ObservationPhase.AFTER,
        attempt_dir=tmp_path / "oversized-output",
        parent_environ={"DB_SECRET": "opaque-db-source"},
        python_executable=PYTHON,
    )
    assert output_reads == 0
    assert result.envelope is None
    assert result.outcome.status is ObserverOutcomeStatus.EXECUTION_ERROR
    assert not list((tmp_path / "oversized-output").glob("sqlite-observer-*.json"))


def test_child_rejects_oversized_invocation_before_reading(tmp_path: Path) -> None:
    input_path = tmp_path / "sqlite-observer-input.json"
    output_path = tmp_path / "sqlite-observer-output.json"
    input_path.write_bytes(b"x" * (OBSERVER_JSON_MAX_BYTES + 1))
    assert sqlite_observer.child_main(str(input_path), str(output_path)) != 0
    assert not output_path.exists()


@pytest.mark.parametrize("field", ["observer_id", "correlation", "phase", "provenance"])
def test_supervisor_rejects_output_bound_to_another_invocation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, field: str) -> None:
    spec = _spec()
    correlation = Correlation(case_id="case-1", resource_id="document", request_marker="case-1")
    state = sqlite_observer.build_normalized_state({"row_count": 1, "rows": [], "truncated": False})
    envelope = sqlite_observer.ObservationEnvelope(
        observer_id=spec.observer_id,
        observer_type=ObserverType.READ_ONLY_SQLITE,
        phase=ObservationPhase.AFTER,
        target_id=spec.target.target_id,
        window=ObservationWindow(phase=ObservationPhase.AFTER, started_at_us=100, finished_at_us=200, timeout_us=spec.budget.timeout_us),
        correlation=correlation,
        causality=CausalityStatus.CORRELATED,
        completeness=ObservationCompleteness.COMPLETE,
        state=state,
        provenance=ObservationProvenance(
            provenance_type=ProvenanceType.SQLITE_QUERY,
            adapter_version="sqlite-observer-1",
            target_id=spec.target.target_id,
            query_template_id="resource-state",
            source_sha256=sqlite_observer.canonical_sha256(state.canonical_data),
        ),
    )
    updates = {
        "observer_id": "other_observer",
        "correlation": Correlation(case_id="other-case", resource_id="document", request_marker="other-case"),
        "phase": ObservationPhase.BEFORE,
        "provenance": envelope.provenance.model_copy(update={"query_template_id": "other-query"}),
    }
    bad = envelope.model_copy(update={field: updates[field]})

    class Process:
        returncode = 0

        def poll(self) -> int:
            return self.returncode

        def wait(self, **kwargs: object) -> None:
            return None

    def fake_popen(command: list[str], **kwargs: object) -> Process:
        Path(command[-1]).write_text(json.dumps(bad.model_dump(mode="json")), encoding="utf-8")
        return Process()

    monkeypatch.setattr(sqlite_observer.subprocess, "Popen", fake_popen)
    result = run_sqlite_observer(
        spec,
        correlation,
        ObservationPhase.AFTER,
        attempt_dir=tmp_path / field,
        parent_environ={"DB_SECRET": "opaque-db-source"},
        python_executable=PYTHON,
    )
    assert result.envelope is None
    assert result.outcome.status is ObserverOutcomeStatus.EXECUTION_ERROR


@pytest.mark.parametrize("source", [r"\\server\share\db", "//server/share/db"])
def test_sqlite_observer_rejects_non_local_database_path(tmp_path: Path, source: str) -> None:
    result = _observe(tmp_path / "non-local", Path(source), _spec())
    assert result.envelope is not None
    assert result.envelope.completeness is ObservationCompleteness.MISSING
    assert result.envelope.reason_codes == (SQLITE_UNAVAILABLE,)
    assert source not in result.envelope.model_dump_json()


def test_atomic_protocol_temp_is_removed_on_replace_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "sqlite-observer-output.json"
    monkeypatch.setattr(sqlite_observer.os, "replace", lambda *args: (_ for _ in ()).throw(OSError("replace failed")))
    with pytest.raises(OSError):
        sqlite_observer._write_atomic(target, b"{}")
    assert not target.exists()
    assert not target.with_name(f".{target.name}.tmp").exists()


def test_parent_wait_timeout_deducts_launch_time(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, float] = {}

    class Process:
        returncode = 7

        def poll(self) -> int:
            return self.returncode

        def wait(self, **kwargs: object) -> None:
            captured["timeout"] = float(kwargs["timeout"])

    monkeypatch.setattr(sqlite_observer.time, "monotonic_ns", iter((1_000, 5_000)).__next__)
    monkeypatch.setattr(sqlite_observer.subprocess, "Popen", lambda *args, **kwargs: Process())
    result = run_sqlite_observer(
        _spec(timeout_us=10),
        Correlation(case_id="case-1", resource_id="document", request_marker="case-1"),
        ObservationPhase.AFTER,
        attempt_dir=tmp_path / "budget",
        parent_environ={"DB_SECRET": "opaque-db-source"},
        python_executable=PYTHON,
    )
    assert captured["timeout"] <= 10 / 1_000_000
    assert captured["timeout"] < 10 / 1_000_000
    assert result.outcome.status is ObserverOutcomeStatus.EXECUTION_ERROR


def test_sqlite_observer_corrupt_output_is_execution_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class CorruptProcess:
        returncode = 0

        def poll(self) -> int:
            return self.returncode

        def wait(self, **kwargs: object) -> None:
            output = Path(kwargs.pop("output_path")) if "output_path" in kwargs else None
            if output is not None:
                output.write_bytes(b"{not-json")

    def fake_popen(command: list[str], **kwargs: object) -> CorruptProcess:
        output = Path(command[-1])
        output.write_bytes(b"{not-json")
        return CorruptProcess()

    monkeypatch.setattr(sqlite_observer.subprocess, "Popen", fake_popen)
    result = run_sqlite_observer(
        _spec(),
        Correlation(case_id="case-1", resource_id="document", request_marker="case-1"),
        ObservationPhase.AFTER,
        attempt_dir=tmp_path / "corrupt",
        parent_environ={"DB_SECRET": "opaque-db-source"},
        python_executable=PYTHON,
    )
    assert result.envelope is None
    assert result.outcome.status is ObserverOutcomeStatus.EXECUTION_ERROR


def test_supervisor_timeout_window_starts_before_child_launch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class TimedOutProcess:
        returncode = -9

        def poll(self) -> int:
            return self.returncode

        def wait(self, **kwargs: object) -> None:
            if kwargs.get("timeout") is not None:
                raise sqlite_observer.subprocess.TimeoutExpired("observer", kwargs["timeout"])

        def kill(self) -> None:
            return None

    ticks = iter((100, 500))
    monkeypatch.setattr(sqlite_observer, "_now_us", lambda: next(ticks))
    monkeypatch.setattr(sqlite_observer.subprocess, "Popen", lambda *args, **kwargs: TimedOutProcess())
    result = run_sqlite_observer(
        _spec(timeout_us=10),
        Correlation(case_id="case-1", resource_id="document", request_marker="case-1"),
        ObservationPhase.AFTER,
        attempt_dir=tmp_path / "timeout-window",
        parent_environ={"DB_SECRET": "opaque-db-source"},
        python_executable=PYTHON,
    )
    assert result.envelope is not None
    assert result.envelope.completeness is ObservationCompleteness.TIMED_OUT
    assert result.envelope.window.started_at_us == 100
    assert result.outcome.status is ObserverOutcomeStatus.INCONCLUSIVE


def test_timeout_reap_is_bounded_when_kill_does_not_exit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    waits: list[object] = []

    class StuckProcess:
        returncode = None

        def poll(self) -> None:
            return None

        def wait(self, **kwargs: object) -> None:
            waits.append(kwargs.get("timeout"))
            raise sqlite_observer.subprocess.TimeoutExpired("observer", kwargs.get("timeout"))

        def kill(self) -> None:
            return None

        def terminate(self) -> None:
            return None

    monkeypatch.setattr(sqlite_observer.subprocess, "Popen", lambda *args, **kwargs: StuckProcess())
    monkeypatch.setattr(sqlite_observer.time, "monotonic_ns", iter((1_000, 1_001)).__next__)
    with pytest.raises(JiejianError) as captured:
        run_sqlite_observer(
            _spec(timeout_us=10),
            Correlation(case_id="case-1", resource_id="document", request_marker="case-1"),
            ObservationPhase.AFTER,
            attempt_dir=tmp_path / "stuck-reap",
            parent_environ={"DB_SECRET": "opaque-db-source"},
            python_executable=PYTHON,
        )
    assert captured.value.code == ErrorCode.PROCESS_TREE_FAILED
    assert len(waits) == 3
    assert waits[0] == pytest.approx(10 / 1_000_000, abs=10e-6)
    assert all(timeout is not None and 0 <= timeout <= 1.0 for timeout in waits[1:])


def test_sqlite_observer_timeout_is_inconclusive(tmp_path: Path) -> None:
    db = tmp_path / "large.db"
    _database(db, [("other", "DRAFT", str(index)) for index in range(50_000)])
    result = _observe(tmp_path / "timeout", db, _spec(timeout_us=1))
    assert result.envelope is not None
    assert result.envelope.completeness is ObservationCompleteness.TIMED_OUT
    assert result.outcome.status is ObserverOutcomeStatus.INCONCLUSIVE


def test_sqlite_query_returned_after_deadline_is_timed_out(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = tmp_path / "deadline.db"
    _database(db, [("document", "DRAFT", "safe")])
    invocation = ObserverInvocation(
        spec=_spec(timeout_us=1),
        correlation=Correlation(case_id="case-1", resource_id="document", request_marker="case-1"),
        phase=ObservationPhase.AFTER,
    )
    ticks = iter((1_000, 2_000, 2_000))
    monkeypatch.setattr(sqlite_observer.time, "monotonic_ns", lambda: next(ticks))
    monkeypatch.setenv("DB_SECRET", str(db))
    envelope = sqlite_observer._run_child(invocation, utc_now_us=lambda: 100)
    assert envelope.completeness is ObservationCompleteness.TIMED_OUT
    assert envelope.reason_codes == (sqlite_observer.SQLITE_QUERY_TIMEOUT,)
