# 真实 TARGET 生成显式范围审计，经采集、执行、发布与只读定位验证禁止效果不会被委托解释抹除。
import os
import time
from functools import partial

import pytest

from product.backend.core.lifecycle import ProjectStatus, RunVerdict
from product.backend.infra.artifacts.check_publication import CheckPublisher
from product.backend.infra.execution.check_executor import CheckExecutor
from product.backend.infra.runtime.jobs.models import ClaimJob
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.storage import ProjectRecord, StorageUnitOfWork
from product.backend.workflows.checks.story import CheckStoryBuilder
from product.backend.workflows.checks import story as story_module
from product.protocols.check_result import canonical_check_document
from product.protocols.check_runtime import canonical_check_runtime_bytes
from product.protocols.execution_v3 import canonical_execution_request_v3_bytes
from tests.backend.infra.execution.test_check_executor import check_target, execution_configuration
from tests.backend.infra.observers.test_audit_log_observer import _spec, _record, _write, TRACE_FIELDS


@pytest.mark.parametrize("variant", ["expanded", "legal", "missing", "outside_resource", "cross_case", "wrong_ancestor", "invalid"])
def test_real_scope_collection_publication_and_current_story(worker_services, check_target, tmp_path, variant, monkeypatch):
    from product.backend.workflows.checks.results import CheckResultReader

    fields = tuple(dict.fromkeys((*TRACE_FIELDS, "allowed_action_ids", "allowed_resource_ids")))
    spec = _spec(fields=fields)
    def configure(payload):
        proof = payload["actions"][0]["proofs"][0]
        proof["auxiliary_sources"] = [dict(observer_id=spec.observer_id, descriptor_fingerprint="a" * 64,
            observation_identity_id=proof["observation_identity_id"], level="DIAGNOSIS_REQUIRED",
            source_label="受控审计", source_location="audit/events", trace_namespace="application")]
        payload["observers"].append(spec.model_dump(mode="json"))
    request, bundle, runner_input, environment = execution_configuration(check_target, configure=configure, deny_effect=True)
    environment = {**os.environ, **environment, "AUDIT_ROOT": str(tmp_path)}
    action = request.actions[0]
    identities = {item.identity_id: item for item in bundle.identities}
    allow = next(case for case in action.cases if case.permission.expectation == "ALLOW")
    written = {}
    def emit(case, marker):
        subject = identities[case.subject_test_identity_id].verification.expected_application_subject_id
        rows = []
        def row(name, kind, parent=None, **extra):
            event_id = case.case_id + ":" + name
            value = _record(marker, case.case_id, event_id, name, len(rows) + 1, resource=case.resource_id,
                kind=kind, semantic_key=name, subject_id=subject, actor_id=subject,
                credential_source="session", source_component="business", source_location="business/handler",
                recorded_at_us=time.time_ns() // 1000, **extra)
            if parent is not None:
                value["parent_event_id"] = parent
            rows.append(value)
            return event_id
        entry = row("entry", "ENTRY")
        identity = row("identity", "IDENTITY", entry)
        authorization = row("authorization", "AUTHORIZATION", identity, authorization_decision="ALLOW",
            allowed_action_ids=[action.action_id], allowed_resource_ids=[case.resource_id])
        delegated = row("delegation", "DELEGATION", authorization, delegated_from_event_id=authorization,
            allowed_action_ids=[action.action_id], allowed_resource_ids=[case.resource_id])
        rows[-1]["actor_id"] = "background-worker"
        row("effect", "PERSISTENT_EFFECT", delegated, effect_id=case.protected_effect_ids[0])
        if case.permission.expectation == "DENY":
            scope = rows[3]
            if variant == "expanded":
                scope["allowed_action_ids"] = ["other-action", action.action_id]
            elif variant == "outside_resource":
                scope["allowed_resource_ids"] = ["other-resource"]
            elif variant == "missing":
                for value in rows:
                    value.pop("allowed_action_ids", None)
                    value.pop("allowed_resource_ids", None)
            elif variant == "cross_case":
                scope["parent_event_id"] = allow.case_id + ":authorization"
                scope["delegated_from_event_id"] = allow.case_id + ":authorization"
            elif variant == "wrong_ancestor":
                scope["delegated_from_event_id"] = identity
                scope["allowed_action_ids"] = ["other-action"]
            elif variant == "invalid":
                scope["allowed_action_ids"] = [True]
        written[case.case_id] = rows
        _write(tmp_path / "audit.jsonl", [item for group in written.values() for item in group])
    check_target[1]["after_target"] = emit
    now = time.time_ns() // 1000
    factory = partial(StorageUnitOfWork, worker_services.session_factory)
    with factory() as work:
        work.projects.add(ProjectRecord(project_id=request.project_id, name="审计范围发布", status=ProjectStatus.READY,
            created_at_us=now, updated_at_us=now))
        work.commit()
    submitted = worker_services.queue.submit(worker_services.submit_request(project_id=request.project_id,
        request_hash=runner_input.request_hash, plan_fingerprint=request.plan_fingerprint,
        source_fingerprint=request.source_fingerprint, policy_epoch=request.policy_epoch,
        engine_version=request.engine_version, available_at_us=now, now_us=now))
    job = worker_services.attempts.claim(ClaimJob(job_id=submitted.job.job_id, lease_owner="check-worker",
        now_us=now, lease_duration_us=60_000_000)).job
    runner_input = runner_input.model_copy(update=dict(run_id=job.run_id, job_id=job.job_id, attempt=job.attempt,
        fencing_token=job.fencing_token, lease_owner=job.lease_owner))
    attempt = RuntimePaths(tmp_path).jobs / job.job_id / "attempts" / "1-1"
    output = CheckExecutor(request, bundle, runner_input, environ=environment, attempt_dir=attempt,
        cancellation_requested=lambda: False).execute()
    assert output.result.verdict is RunVerdict.BLOCK
    assert len(check_target[1]["target_calls"]) == 2
    staging = attempt / "staging"
    (staging / "evidence").mkdir(parents=True)
    (staging / "request.json").write_bytes(canonical_execution_request_v3_bytes(request))
    (staging / "runtime.json").write_bytes(canonical_check_runtime_bytes(bundle))
    (staging / "result.json").write_bytes(canonical_check_document(output.result))
    for document in output.evidence:
        (staging / "evidence" / f"{document.evidence_id}.json").write_bytes(canonical_check_document(document))
    package = CheckPublisher(tmp_path, factory).publish(staging)
    reader = CheckResultReader(var_dir=tmp_path, uow_factory=factory)
    story = CheckStoryBuilder(reader).build(job.run_id)
    # 对真实 BLOCK 包关闭新增显示字段，全部既有身份、定位和修复字段必须逐值保持。
    with monkeypatch.context() as context:
        context.setattr(story_module, "_execution_path", lambda documents: None)
        without_path = CheckStoryBuilder(reader).build(job.run_id)
    assert story.model_dump(exclude={"actions": {"__all__": {"execution_path"}}}) == without_path.model_dump(
        exclude={"actions": {"__all__": {"execution_path"}}})
    assert story.verdict is RunVerdict.BLOCK
    deny_story = next(item for item in story.actions if item.permission.expectation == "DENY")
    document = next(item for item in package.evidence if item.case.case_id == deny_story.case_id)
    assert deny_story.execution_path.complete == document.trace.complete
    assert deny_story.execution_path.reason_codes == document.trace.reason_codes
    assert deny_story.execution_path.evidence_refs == (document.evidence_id,)
    assert [(event.event_id, event.parent_event_ids) for event in deny_story.execution_path.events] == [
        (event.event_id, event.parent_event_ids) for event in document.trace.events]
    assert any(item.level == "VERDICT_REQUIRED" and item.state == "CONFIRMED" and item.authoritative
        for item in document.observations)
    assert document.evidence_id in deny_story.technical_references
    assert all(event.case_id == document.case.case_id and event.event_id.startswith(document.case.case_id + ":")
        for event in document.trace.events)
    source_rows = {row["event_id"]: row for row in written[document.case.case_id]}
    for event in document.trace.events:
        source = source_rows[event.event_id]
        assert event.authority_scope.allowed_action_ids == tuple(sorted(source.get("allowed_action_ids", [])))
        assert event.authority_scope.allowed_resource_ids == tuple(sorted(source.get("allowed_resource_ids", [])))
    location = deny_story.breakpoint
    assert location is not None
    types = {location.breakpoint_type, *location.amplifier_types}
    if variant in {"expanded", "outside_resource", "wrong_ancestor"}:
        assert "AUTHORITY_EXPANSION" in types
    elif variant == "legal":
        assert "AUTHORITY_EXPANSION" not in types and "IDENTITY_SUBSTITUTION" not in types
        delegation = next(event for event in document.trace.events if event.kind == "DELEGATION")
        assert delegation.authority_scope.allowed_action_ids == (action.action_id,)
        assert delegation.authority_scope.allowed_resource_ids == (document.case.resource_id,)
    elif variant == "missing":
        assert all(not event.authority_scope.allowed_action_ids and not event.authority_scope.allowed_resource_ids
            for event in document.trace.events)
        assert "AUTHORITY_EXPANSION" not in types and "IDENTITY_SUBSTITUTION" not in types
    else:
        assert not document.trace.complete
    # 重新从收据和不可变文件读取，引用必须仍属于对应 Case，不能仅检查执行器内存对象。
    reread = reader.package(job.run_id)
    assert reread.evidence == package.evidence
    by_case = {item.case.case_id: item.evidence_id for item in reread.evidence}
    for item in story.actions:
        assert all(explanation.evidence_refs == (by_case[item.case_id],) for explanation in item.evidence_explanations)
