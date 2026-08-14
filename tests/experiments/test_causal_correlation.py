from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest


REQUIRED_FIELDS = frozenset(
    {"event_id", "case_tag", "task_id", "event_type", "sequence", "resource_id"}
)
TERMINAL_STATES = frozenset({"SUCCESS", "FAILED"})


@dataclass(frozen=True)
class ScanBudget:
    max_files: int = 12
    max_bytes: int = 16_384
    max_lines: int = 128
    max_polls: int = 2
    max_states: int = 24


@dataclass(frozen=True)
class CorrelationResult:
    status: str
    reason_codes: tuple[str, ...]
    case_tag: str
    task_id: str | None
    terminal_state: str | None
    resource_value: str | None
    files_scanned: int
    bytes_scanned: int
    lines_scanned: int
    polls: int
    states_scanned: int
    partial_tails: int

    def stable_payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reason_codes": self.reason_codes,
            "case_tag": self.case_tag,
            "task_id": self.task_id,
            "terminal_state": self.terminal_state,
            "resource_value": self.resource_value,
            "files_scanned": self.files_scanned,
            "bytes_scanned": self.bytes_scanned,
            "lines_scanned": self.lines_scanned,
            "polls": self.polls,
            "states_scanned": self.states_scanned,
            "partial_tails": self.partial_tails,
        }


class ExperimentHarness:
    """Deterministic target-side stand-in; it is deliberately not production code."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._tick = 0
        self._pending: dict[str, str] = {}
        self.resource_values = {"resource-a": "initial", "resource-b": "initial"}

    def _advance(self) -> int:
        self._tick += 1
        return self._tick

    def _record(
        self,
        stream: str,
        *,
        event_id: str,
        case_tag: str,
        task_id: str,
        event_type: str,
        sequence: int,
        resource_id: str,
        **extra: object,
    ) -> dict[str, object]:
        record: dict[str, object] = {
            "event_id": event_id,
            "case_tag": case_tag,
            "task_id": task_id,
            "event_type": event_type,
            "sequence": sequence,
            "resource_id": resource_id,
            "logical_tick": self._advance(),
            **extra,
        }
        path = self.root / f"{stream}.jsonl"
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            handle.write("\n")
        return record

    def submit(self, case_tag: str, resource_id: str, *, denied: bool) -> None:
        self._record(
            "audit",
            event_id=f"request-{case_tag}",
            case_tag=case_tag,
            task_id="",
            event_type="REQUEST",
            sequence=1,
            resource_id=resource_id,
            decision="DENY" if denied else "ALLOW",
        )
        if denied and case_tag.startswith("vulnerable-"):
            task_id = f"task-{case_tag}"
            self._pending[case_tag] = task_id
            self._record(
                "tasks",
                event_id=f"{task_id}-queued",
                case_tag=case_tag,
                task_id=task_id,
                event_type="TASK_STATE",
                sequence=1,
                resource_id=resource_id,
                state="QUEUED",
            )

    def execute(self, case_tag: str, resource_id: str, *, outcome: str = "SUCCESS") -> None:
        task_id = self._pending.pop(case_tag)
        self._record(
            "tasks",
            event_id=f"{task_id}-running",
            case_tag=case_tag,
            task_id=task_id,
            event_type="TASK_STATE",
            sequence=2,
            resource_id=resource_id,
            state="RUNNING",
        )
        self._record(
            "tasks",
            event_id=f"{task_id}-{outcome.lower()}",
            case_tag=case_tag,
            task_id=task_id,
            event_type="TASK_STATE",
            sequence=3,
            resource_id=resource_id,
            state=outcome,
        )
        if outcome == "SUCCESS":
            self.resource_values[resource_id] = f"changed-{case_tag}"
            self._record(
                "effects",
                event_id=f"effect-{case_tag}",
                case_tag=case_tag,
                task_id=task_id,
                event_type="SIDE_EFFECT",
                sequence=4,
                resource_id=resource_id,
                state="APPLIED",
                value=self.resource_values[resource_id],
            )

    def add_nearby_unbound_task(self, resource_id: str, *, mismatched: bool) -> None:
        case_tag = "other-case" if mismatched else ""
        self._record(
            "tasks",
            event_id="unbound-nearby-task",
            case_tag=case_tag,
            task_id="task-without-correlation",
            event_type="TASK_STATE",
            sequence=1,
            resource_id=resource_id,
            state="SUCCESS",
        )

    def rotate_audit(self) -> None:
        active = self.root / "audit.jsonl"
        rotated = self.root / "audit.1.jsonl"
        if rotated.exists():
            rotated.unlink()
        active.replace(rotated)

    def duplicate_first_audit_record(self) -> None:
        rotated = self.root / "audit.1.jsonl"
        first = json.loads(rotated.read_text(encoding="utf-8").splitlines()[0])
        with (self.root / "audit.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(first, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            handle.write("\n")

    def add_irrelevant_record(self) -> None:
        self._record(
            "audit",
            event_id="unrelated-request",
            case_tag="unrelated-case",
            task_id="",
            event_type="REQUEST",
            sequence=1,
            resource_id="resource-b",
            decision="DENY",
        )

    def append_partial_tail(self, stream: str, record: dict[str, object]) -> None:
        path = self.root / f"{stream}.jsonl"
        with path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _canonical_record(record: dict[str, object]) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def correlate(
    root: Path,
    case_tag: str,
    resource_id: str,
    *,
    budget: ScanBudget = ScanBudget(),
) -> CorrelationResult:
    root = root.resolve()
    reasons: set[str] = set()
    files_scanned = bytes_scanned = lines_scanned = states_scanned = partial_tails = 0
    polls = 1
    records: list[dict[str, object]] = []
    seen: dict[str, str] = {}

    if polls > budget.max_polls:
        reasons.add("POLL_BUDGET_EXCEEDED")
    else:
        paths = sorted(
            [*root.glob("audit*.jsonl"), *root.glob("tasks*.jsonl"), *root.glob("effects*.jsonl")],
            key=lambda path: path.name,
        )
        if len(paths) > budget.max_files:
            reasons.add("FILE_BUDGET_EXCEEDED")
            paths = paths[: budget.max_files]
        for path in paths:
            resolved = path.resolve()
            if not resolved.is_relative_to(root) or resolved != path:
                reasons.add("OUT_OF_SCOPE_FILE")
                continue
            files_scanned += 1
            size = path.stat().st_size
            if bytes_scanned + size > budget.max_bytes:
                reasons.add("BYTE_BUDGET_EXCEEDED")
                break
            data = path.read_bytes()
            bytes_scanned += len(data)
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                reasons.add("MALFORMED_LINE")
                continue
            lines = text.splitlines(keepends=True)
            for index, line in enumerate(lines):
                if lines_scanned >= budget.max_lines:
                    reasons.add("LINE_BUDGET_EXCEEDED")
                    break
                if index == len(lines) - 1 and not line.endswith(("\n", "\r")):
                    partial_tails += 1
                    continue
                lines_scanned += 1
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    reasons.add("MALFORMED_LINE")
                    continue
                if not isinstance(record, dict):
                    reasons.add("MALFORMED_EVENT")
                    continue
                event_id = record.get("event_id")
                if not isinstance(event_id, str) or not event_id:
                    reasons.add("MALFORMED_EVENT")
                    continue
                canonical = _canonical_record(record)
                if event_id in seen:
                    if seen[event_id] != canonical:
                        reasons.add("CONFLICTING_DUPLICATE")
                    continue
                seen[event_id] = canonical
                missing = REQUIRED_FIELDS - record.keys()
                if missing:
                    reasons.add("MALFORMED_EVENT")
                    if "case_tag" in missing:
                        reasons.add("MISSING_CASE_TAG")
                if record.get("event_type") == "TASK_STATE":
                    states_scanned += 1
                    if states_scanned > budget.max_states:
                        reasons.add("STATE_BUDGET_EXCEEDED")
                        break
                records.append(record)
            if "LINE_BUDGET_EXCEEDED" in reasons or "STATE_BUDGET_EXCEEDED" in reasons:
                break

    tagged = [record for record in records if record.get("case_tag") == case_tag]
    requests = [record for record in tagged if record.get("event_type") == "REQUEST"]
    task_events = [record for record in tagged if record.get("event_type") == "TASK_STATE"]
    effects = [record for record in tagged if record.get("event_type") == "SIDE_EFFECT"]
    request = next((record for record in requests if record.get("resource_id") == resource_id), None)
    if request is None:
        reasons.add("REQUEST_NOT_FOUND")

    nearby_unbound = False
    if request is not None:
        request_tick = request.get("logical_tick")
        if isinstance(request_tick, int):
            nearby_unbound = any(
                record.get("resource_id") == resource_id
                and record.get("event_type") in {"TASK_STATE", "SIDE_EFFECT"}
                and record.get("case_tag") != case_tag
                and isinstance(record.get("logical_tick"), int)
                and abs(record["logical_tick"] - request_tick) <= 1
                for record in records
            )
    if not task_events:
        if nearby_unbound:
            reasons.add("CASE_TAG_NOT_PROVABLE")
        elif request is not None and not effects:
            reasons.add("DENIED_WITHOUT_TASK")
    task_ids = {record.get("task_id") for record in task_events if record.get("task_id")}
    if len(task_ids) > 1:
        reasons.add("CONFLICTING_TASK_ID")
    task_id = next(iter(task_ids), None)
    matching_tasks = [record for record in task_events if record.get("task_id") == task_id]
    ordered_tasks = sorted(matching_tasks, key=lambda record: int(record.get("sequence", -1)))
    states = [record.get("state") for record in ordered_tasks]
    if task_events and (not task_id or any(record.get("resource_id") != resource_id for record in task_events)):
        reasons.add("TASK_CHAIN_NOT_UNIQUE")
    if task_events and states[:3] != ["QUEUED", "RUNNING", states[2] if len(states) > 2 else None]:
        reasons.add("TASK_SEQUENCE_INVALID")
    terminal_state = states[-1] if states and states[-1] in TERMINAL_STATES else None
    if task_events and terminal_state is None:
        reasons.add("TASK_NOT_TERMINAL")
    matching_effects = [
        record
        for record in effects
        if record.get("task_id") == task_id and record.get("resource_id") == resource_id
    ]
    if matching_effects and terminal_state != "SUCCESS":
        reasons.add("SIDE_EFFECT_TERMINAL_MISMATCH")
    if terminal_state == "SUCCESS" and len(matching_effects) != 1:
        reasons.add("SIDE_EFFECT_NOT_UNIQUE")
    if partial_tails:
        reasons.add("PARTIAL_TAIL_IGNORED")
    if reasons - {"DENIED_WITHOUT_TASK", "PARTIAL_TAIL_IGNORED"}:
        status = "INCONCLUSIVE"
    elif task_id and terminal_state == "SUCCESS" and len(matching_effects) == 1:
        status = "CONFIRMED_VULNERABLE"
    elif request is not None and not task_id and not effects:
        status = "CONFIRMED_FIXED"
    else:
        status = "INCONCLUSIVE"
    effect_value = matching_effects[0].get("value") if len(matching_effects) == 1 else None
    return CorrelationResult(
        status=status,
        reason_codes=tuple(sorted(reasons)),
        case_tag=case_tag,
        task_id=task_id,
        terminal_state=terminal_state,
        resource_value=effect_value if isinstance(effect_value, str) else None,
        files_scanned=files_scanned,
        bytes_scanned=bytes_scanned,
        lines_scanned=lines_scanned,
        polls=polls,
        states_scanned=states_scanned,
        partial_tails=partial_tails,
    )


def test_fixed_vulnerable_and_inconclusive_facts_repeat_without_wall_clock(tmp_path: Path) -> None:
    expected = {
        "fixed": "CONFIRMED_FIXED",
        "vulnerable": "CONFIRMED_VULNERABLE",
        "inconclusive": "INCONCLUSIVE",
    }
    summaries: dict[str, list[str]] = {name: [] for name in expected}
    for repeat in range(3):
        for variant, status in expected.items():
            root = tmp_path / f"{variant}-{repeat}"
            harness = ExperimentHarness(root)
            case_tag = f"{variant}-case-001"
            harness.submit(case_tag, "resource-a", denied=True)
            if variant == "vulnerable":
                harness.execute(case_tag, "resource-a")
            elif variant == "inconclusive":
                harness.add_nearby_unbound_task("resource-a", mismatched=True)
            result = correlate(root, case_tag, "resource-a")
            assert result.status == status
            summaries[variant].append(json.dumps(result.stable_payload(), sort_keys=True))
    for values in summaries.values():
        assert len(set(values)) == 1


def test_interleaved_cases_rotation_exact_duplicates_and_irrelevant_events_are_stable(tmp_path: Path) -> None:
    harness = ExperimentHarness(tmp_path)
    harness.submit("vulnerable-a", "resource-a", denied=True)
    harness.submit("vulnerable-b", "resource-b", denied=True)
    harness.rotate_audit()
    harness.duplicate_first_audit_record()
    harness.add_irrelevant_record()
    harness.execute("vulnerable-b", "resource-b")
    harness.execute("vulnerable-a", "resource-a")
    for case_tag, resource_id in (("vulnerable-a", "resource-a"), ("vulnerable-b", "resource-b")):
        result = correlate(tmp_path, case_tag, resource_id)
        assert result.status == "CONFIRMED_VULNERABLE"
        assert "CONFLICTING_DUPLICATE" not in result.reason_codes
        assert result.task_id == f"task-{case_tag}"
    assert correlate(tmp_path, "vulnerable-a", "resource-a").stable_payload() == correlate(
        tmp_path, "vulnerable-a", "resource-a"
    ).stable_payload()


def test_missing_or_mismatched_tag_never_uses_time_or_resource_similarity(tmp_path: Path) -> None:
    for mismatched in (False, True):
        root = tmp_path / str(mismatched)
        harness = ExperimentHarness(root)
        harness.submit("inconclusive-case", "resource-a", denied=True)
        harness.add_nearby_unbound_task("resource-a", mismatched=mismatched)
        result = correlate(root, "inconclusive-case", "resource-a")
        assert result.status == "INCONCLUSIVE"
        assert "CASE_TAG_NOT_PROVABLE" in result.reason_codes
        assert result.task_id is None


def test_conflicting_duplicate_partial_tail_and_rotated_budget_are_explicit_gaps(tmp_path: Path) -> None:
    harness = ExperimentHarness(tmp_path)
    harness.submit("vulnerable-case", "resource-a", denied=True)
    harness.rotate_audit()
    harness.duplicate_first_audit_record()
    conflict = json.loads((tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()[0])
    conflict["decision"] = "ALLOW"
    with (tmp_path / "audit.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(_canonical_record(conflict) + "\n")
    harness.append_partial_tail(
        "effects",
        {
            "event_id": "partial-effect",
            "case_tag": "vulnerable-case",
            "task_id": "task-vulnerable-case",
            "event_type": "SIDE_EFFECT",
            "sequence": 4,
            "resource_id": "resource-a",
        },
    )
    result = correlate(tmp_path, "vulnerable-case", "resource-a")
    assert result.status == "INCONCLUSIVE"
    assert "CONFLICTING_DUPLICATE" in result.reason_codes
    assert "PARTIAL_TAIL_IGNORED" in result.reason_codes
    limited = correlate(tmp_path, "vulnerable-case", "resource-a", budget=ScanBudget(max_bytes=32))
    assert limited.status == "INCONCLUSIVE"
    assert "BYTE_BUDGET_EXCEEDED" in limited.reason_codes


def test_failed_task_and_poll_state_budgets_never_become_confirmation(tmp_path: Path) -> None:
    harness = ExperimentHarness(tmp_path)
    harness.submit("vulnerable-failed", "resource-a", denied=True)
    harness._pending["vulnerable-failed"] = "task-vulnerable-failed"
    harness.execute("vulnerable-failed", "resource-a", outcome="FAILED")
    result = correlate(tmp_path, "vulnerable-failed", "resource-a")
    assert result.status == "INCONCLUSIVE"
    assert "TASK_NOT_TERMINAL" not in result.reason_codes
    assert result.terminal_state == "FAILED"
    assert result.polls == 1
    limited = correlate(tmp_path, "vulnerable-failed", "resource-a", budget=ScanBudget(max_states=1))
    assert limited.status == "INCONCLUSIVE"
    assert "STATE_BUDGET_EXCEEDED" in limited.reason_codes


def test_result_fingerprint_is_stable_and_budget_counters_are_observable(tmp_path: Path) -> None:
    harness = ExperimentHarness(tmp_path)
    harness.submit("vulnerable-budget", "resource-a", denied=True)
    harness.execute("vulnerable-budget", "resource-a")
    first = correlate(tmp_path, "vulnerable-budget", "resource-a")
    second = correlate(tmp_path, "vulnerable-budget", "resource-a")
    first_bytes = json.dumps(first.stable_payload(), sort_keys=True).encode("utf-8")
    second_bytes = json.dumps(second.stable_payload(), sort_keys=True).encode("utf-8")
    assert hashlib.sha256(first_bytes).hexdigest() == hashlib.sha256(second_bytes).hexdigest()
    assert first.files_scanned == 3
    assert first.lines_scanned >= 5
    assert first.bytes_scanned <= ScanBudget().max_bytes
    assert first.polls <= ScanBudget().max_polls
    assert first.states_scanned == 3
