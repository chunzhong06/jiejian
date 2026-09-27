# 所属业务域的共享测试构造器；不导入测试用例。
from __future__ import annotations
import json
from pathlib import Path
from product.protocols import AuditLogScanBudget, ObservationPhase, ObserverBudget, ObserverSpec, ObserverTarget, ObserverType, StructuredAuditLogLocator

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

TRACE_FIELDS = FIELDS + (
    "parent_event_id",
    "kind",
    "semantic_key",
    "subject_id",
    "actor_id",
    "credential_source",
    "effect_id",
    "origin_authorization_event_id",
    "delegated_from_event_id",
    "authorization_decision",
    "source_component",
    "source_location",
    "recorded_at_us",
)

def _spec(*, phases: tuple[ObservationPhase, ...] = (ObservationPhase.AFTER,), max_files: int = 4, max_lines: int = 100, max_line_bytes: int = 4096, max_rows: int = 100, timeout_us: int = 5_000_000, fields: tuple[str, ...] = FIELDS) -> ObserverSpec:
    return ObserverSpec(
        observer_id="audit_observer",
        observer_type=ObserverType.STRUCTURED_AUDIT_LOG,
        target=ObserverTarget(
            target_id="audit-window",
            locator=StructuredAuditLogLocator(
                authorized_root_ref="env:AUDIT_ROOT",
                relative_file_pattern="audit.jsonl",
                allowed_fields=fields,
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
