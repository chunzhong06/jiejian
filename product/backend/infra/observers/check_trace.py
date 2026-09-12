# 从本 Case 受控审计窗口提取有界因果 Trace；只采用显式父引用，不推断业务效果或授权范围。
import json

from product.backend.core.verification.trace import ExecutionTrace, TraceEvent


def build_check_trace(*, case, action_id, planned_subject_id, marker, groups):
    """将已验证来源的显式事件转为单 Case DAG；缺口保留为不完整诊断。"""
    reasons, records = set(), {}
    for envelopes, trusted in groups:
        if not trusted or not envelopes:
            reasons.add("TRACE_SOURCE_INCOMPLETE")
            continue
        for envelope in envelopes:
            if envelope.state is None:
                reasons.add("TRACE_SOURCE_INCOMPLETE")
                continue
            rows = envelope.state.canonical_data.get("records")
            if not isinstance(rows, (list, tuple)):
                reasons.add("TRACE_EVENT_INVALID")
                continue
            for row in rows:
                if not isinstance(row, dict) or row.get("case_tag") != marker or row.get("resource_id") != case.resource_id:
                    reasons.add("TRACE_CORRELATION_INVALID")
                    continue
                if row.get("semantic_key") is None:
                    continue
                event_id = row.get("event_id")
                if not isinstance(event_id, str) or row.get("event_type") != row.get("semantic_key"):
                    reasons.add("TRACE_EVENT_INVALID")
                    continue
                if event_id in records and records[event_id] != row:
                    reasons.add("TRACE_EVENT_CONFLICT")
                    records[event_id] = None
                elif event_id not in records:
                    if len(records) >= 512:
                        reasons.add("TRACE_BUDGET_EXCEEDED")
                        continue
                    records[event_id] = row
    events, event_bytes = [], 0
    for row in tuple(records.values())[:512]:
        if row is None:
            continue
        try:
            effect_id = row.get("effect_id")
            if effect_id is not None and effect_id not in case.protected_effect_ids:
                raise ValueError("trace effect is outside frozen protection")
            dispatch_effect_ids = row.get("dispatch_effect_ids", [])
            if not isinstance(dispatch_effect_ids,(list,tuple)) or not set(dispatch_effect_ids) <= set(case.protected_effect_ids):
                raise ValueError("dispatch effects are outside frozen case protection")
            scope = dict(allowed_action_ids=row.get("allowed_action_ids", []),
                allowed_resource_ids=row.get("allowed_resource_ids", []),
                origin_authorization_event_id=row.get("origin_authorization_event_id"),
                delegated_from_event_id=row.get("delegated_from_event_id"))
            payload = dict(event_id=row["event_id"], case_id=case.case_id, action_id=action_id,
                resource_ids=[case.resource_id], kind=row["kind"], semantic_key=row["semantic_key"],
                parent_event_ids=[row["parent_event_id"]] if row.get("parent_event_id") else [],
                subject_id=row.get("subject_id"), actor_id=row.get("actor_id"),
                credential_source=row.get("credential_source"), authority_scope=scope,
                authorization_decision=row.get("authorization_decision"), effect_id=effect_id,
                dispatch_effect_ids=dispatch_effect_ids,
                source_component=row["source_component"], source_location=row["source_location"],
                recorded_at_us=row["recorded_at_us"],
                correlation_kind="EXPLICIT_PARENT" if row.get("parent_event_id") else "CASE_MARKER",
                evidence_refs=[])
            # Evidence 根在 Trace 之后封口；节点属于该根，不构造自引用内容地址。
            event = TraceEvent.model_validate_json(json.dumps(payload), strict=True)
            size = len(event.model_dump_json().encode("utf-8"))
            if event_bytes + size > 262_144:
                reasons.add("TRACE_BUDGET_EXCEEDED")
                continue
            events.append(event)
            event_bytes += size
        except (KeyError, ValueError, TypeError):
            reasons.add("TRACE_EVENT_INVALID")
    while True:
        available = {event.event_id for event in events}
        kept = [event for event in events if all(reference in available for reference in (
            *event.parent_event_ids, *(item for item in (event.authority_scope.origin_authorization_event_id,
                event.authority_scope.delegated_from_event_id) if item is not None)))]
        if len(kept) == len(events):
            break
        reasons.add("TRACE_PARENT_MISSING")
        events = kept
    if not events:
        reasons.add("TRACE_EVENTS_UNAVAILABLE")
    try:
        return ExecutionTrace(case_id=case.case_id, action_id=action_id, planned_subject_id=planned_subject_id,
            events=tuple(events), complete=not reasons, reason_codes=tuple(sorted(reasons)))
    except ValueError:
        return ExecutionTrace(case_id=case.case_id, action_id=action_id, planned_subject_id=planned_subject_id,
            events=(), complete=False, reason_codes=("TRACE_GRAPH_INVALID",))
