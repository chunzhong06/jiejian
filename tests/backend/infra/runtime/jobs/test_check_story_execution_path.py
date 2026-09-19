# 验证故事路径只复制同 Case 已发布 Trace 的显式 DAG，并保留原结果及完整性边界。
from types import SimpleNamespace as N
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from product.backend.core.errors import JiejianError
from product.backend.core.verification.trace import (
    ExecutionTrace, TraceAuthorityScope, TraceAuthorizationDecision, TraceCorrelationKind, TraceEvent, TraceEventKind,
)
from product.backend.infra.artifacts.check_publication import CheckPublisher
from product.backend.workflows.checks import story as story_module
from product.backend.workflows.checks.results import CheckResultReader
from product.backend.workflows.checks.story import CheckStoryBuilder, StoryExecutionPath, _execution_path
from product.protocols.check_result import CheckEvidence, canonical_check_document, seal_check_evidence
from tests.fixtures.check_publication import package_parts, NOW


def branch_trace(case_id="case-path", action_id="action-path", *, reverse=False, later=False):
    edges = {"entry": (), "message": ("entry",), "authorization": ("message",),
        "worker": ("message",), "effect": ("worker",), "final": ("authorization", "effect")}
    kinds = [TraceEventKind.ENTRY, TraceEventKind.MESSAGE, TraceEventKind.AUTHORIZATION,
        TraceEventKind.DELEGATION, TraceEventKind.PERSISTENT_EFFECT, TraceEventKind.FINAL_EFFECT]
    events = tuple(TraceEvent(event_id=key, parent_event_ids=parents, case_id=case_id, action_id=action_id,
        resource_ids=("resource",), kind=kind, semantic_key=key, subject_id="subject", actor_id="actor",
        credential_source="session", authority_scope=TraceAuthorityScope(allowed_action_ids=(action_id,)),
        authorization_decision=TraceAuthorizationDecision.DENY if key == "authorization" else None,
        effect_id="effect-object" if key in {"effect", "final"} else None,
        dispatch_effect_ids=("effect-object",) if key == "message" else (),
        source_component="worker" if key == "worker" else "business", source_location="handler/"+key,
        correlation_kind=TraceCorrelationKind.TEMPORAL, evidence_refs=("audit/line-1",),
        recorded_at_us=100-index if later else index)
        for index, ((key, parents), kind) in enumerate(zip(edges.items(), kinds)))
    return ExecutionTrace(case_id=case_id, action_id=action_id, planned_subject_id="subject",
        events=tuple(reversed(events)) if reverse else events, complete=True)


def test_complete_branch_copies_only_contract_fields_without_inferred_edges():
    trace = branch_trace(reverse=True)
    path = _execution_path((N(trace=trace, evidence_id="document-a"),))
    assert path.complete and path.reason_codes == () and path.evidence_refs == ("document-a",)
    assert [event.event_id for event in path.events] == [event.event_id for event in trace.events]
    expected = {"entry": (), "message": ("entry",), "authorization": ("message",),
        "worker": ("message",), "effect": ("worker",), "final": ("authorization", "effect")}
    assert {event.event_id: event.parent_event_ids for event in path.events} == expected
    fields = {"event_id", "parent_event_ids", "kind", "authorization_decision", "effect_id",
        "dispatch_effect_ids", "source_component", "source_location"}
    for projected, original in zip(path.events, trace.events, strict=True):
        assert set(projected.model_dump()) == fields
        assert all(getattr(projected, key) == getattr(original, key) for key in fields)
    assert set(path.model_dump()) == {"complete", "reason_codes", "events", "evidence_refs"}
    assert "audit/line-1" not in path.evidence_refs
    assert StoryExecutionPath.model_validate_json(path.model_dump_json()) == path


@pytest.mark.parametrize("empty", [False, True])
def test_partial_path_preserves_reasons_and_even_empty_events(empty):
    trace = branch_trace()
    trace = ExecutionTrace(case_id=trace.case_id, action_id=trace.action_id, planned_subject_id=trace.planned_subject_id,
        events=() if empty else trace.events, complete=False, reason_codes=("TRACE_PARTIAL", "MISSING_SOURCE"))
    path = _execution_path((N(trace=trace, evidence_id="document-a"),))
    assert not path.complete and path.reason_codes == trace.reason_codes
    assert len(path.events) == (0 if empty else 6)


def test_missing_conflicting_and_equal_traces_keep_only_supporting_document_ids():
    trace = branch_trace()
    different = ExecutionTrace(case_id=trace.case_id, action_id=trace.action_id,
        planned_subject_id=trace.planned_subject_id, events=trace.events, complete=False, reason_codes=("PARTIAL",))
    a, b, c = N(trace=trace, evidence_id="document-a"), N(trace=trace, evidence_id="document-b"), N(trace=None, evidence_id="document-c")
    assert _execution_path(()) is None and _execution_path((c,)) is None
    assert _execution_path((a, N(trace=different, evidence_id="document-d"))) is None
    path = _execution_path((b, c, a, b))
    assert len(path.events) == 6 and path.evidence_refs == ("document-b", "document-a")


def test_input_order_and_time_changes_do_not_invent_or_remove_edges():
    paths = [_execution_path((N(trace=branch_trace(reverse=reverse, later=later), evidence_id="document-a"),))
        for reverse, later in [(False, False), (True, False), (True, True)]]
    edges = lambda path: {item.event_id: item.parent_event_ids for item in path.events}
    assert paths[0] == paths[1]
    assert edges(paths[0]) == edges(paths[2])
    for path in paths:
        seen = set()
        for item in path.events:
            assert set(item.parent_event_ids) <= seen
            seen.add(item.event_id)


def test_all_512_nodes_are_projected_and_dto_rejects_overflow():
    prototype = branch_trace().events[0]
    events = tuple(prototype.model_copy(update={"event_id": f"node-{i}", "parent_event_ids": ()}) for i in range(512))
    trace = ExecutionTrace(case_id=prototype.case_id, action_id=prototype.action_id,
        planned_subject_id="subject", events=events, complete=True)
    path = _execution_path((N(trace=trace, evidence_id="document-a"),))
    assert path.complete and len(path.events) == 512
    assert [item.event_id for item in path.events] == [item.event_id for item in trace.events]
    with pytest.raises(ValidationError):
        StoryExecutionPath(complete=True, reason_codes=(), events=(*path.events, path.events[0]), evidence_refs=())


def test_real_published_story_keeps_case_isolation_and_existing_facts(package_parts, monkeypatch):
    var_dir, factory, job, staging, template = package_parts
    results, document_ids = [], {}
    for result in template.case_results:
        old_path = staging / "evidence" / f"{result.evidence_ids[0]}.json"
        document = CheckEvidence.model_validate_json(old_path.read_bytes())
        trace = branch_trace(document.case.case_id, document.action_id)
        replacement = seal_check_evidence(**{name: getattr(document, name) for name in CheckEvidence.model_fields
            if name not in {"evidence_id", "trace"}}, trace=trace)
        old_path.unlink()
        (staging / "evidence" / f"{replacement.evidence_id}.json").write_bytes(canonical_check_document(replacement))
        document_ids[result.case_id] = replacement.evidence_id
        results.append(result.model_copy(update={"evidence_ids": (replacement.evidence_id,)}))
    (staging / "result.json").write_bytes(canonical_check_document(template.model_copy(update={"case_results": tuple(results)})))
    package = CheckPublisher(var_dir, factory, clock_us=lambda: NOW+20).publish(staging)
    reader = CheckResultReader(var_dir=var_dir, uow_factory=factory)
    builder = CheckStoryBuilder(reader)
    # 对同一已发布包关闭新增投影，比较全部旧字段；不以替身 reader 冒充完整性通过。
    with monkeypatch.context() as context:
        context.setattr(story_module, "_execution_path", lambda documents: None)
        before = builder.build(job.run_id)
    read_package = Mock(wraps=reader.package)
    monkeypatch.setattr(reader, "package", read_package)
    forbidden = Mock(side_effect=AssertionError("projection cannot recompute verdict"))
    monkeypatch.setattr("product.backend.core.verification.checks.evaluate_check_case", forbidden)
    after = builder.build(job.run_id)
    assert read_package.call_count == 1
    assert after.model_dump(exclude={"actions": {"__all__": {"execution_path"}}}) == before.model_dump(
        exclude={"actions": {"__all__": {"execution_path"}}})
    assert after.verdict == package.result.verdict
    assert len(after.actions) >= 2
    for item in after.actions:
        assert item.execution_path.evidence_refs == (document_ids[item.case_id],)
        assert {event.event_id for event in item.execution_path.events} == {"entry", "message", "authorization", "worker", "effect", "final"}
        evidence = reader.evidence(job.run_id, document_ids[item.case_id])
        assert evidence.case.case_id == item.case_id
    forbidden.assert_not_called()
    (package.directory / "result.json").write_bytes(b"{}")
    with pytest.raises(JiejianError):
        builder.build(job.run_id)
