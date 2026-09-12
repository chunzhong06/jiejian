# 验证活动 Sample 的普通人工批准、正式录制准备和当前检查输入；不启动产品或完整 L5。
from pathlib import Path
import time

import pytest

from product.backend.composition import ApplicationCore
from product.backend.workflows.official_scenario import OfficialScenarioInstaller
from tests.fixtures.collaboration_golden import InMemorySecretStore
from tests.fixtures.runtime_environment import runtime_identity_environment


@pytest.fixture
def current_sample(tmp_path):
    root = Path(__file__).resolve().parents[3]
    var_dir = tmp_path / "var"
    core = ApplicationCore(var_dir, official_sample_root=root / "samples/web/collaboration_space",
        secret_store=InMemorySecretStore(), environ=runtime_identity_environment(var_dir))
    try:
        yield core
    finally:
        try:
            core.close()
        finally:
            # 测试失败时也只回收本 fixture 管理的进程，保留数据库首错状态。
            core.official_samples.stop()
            core.engine.dispose()


def test_sample_requires_human_approval_then_uses_persistent_recordings(current_sample):
    core = current_sample
    view = core.official_experience.start(consent=True)
    assert view.active
    project = view.project_id
    assert core.official_experience.prepare().pending_tasks == ("HUMAN_BOUNDARY_APPROVAL_REQUIRED",)
    assert core.test_identities.list(project) == ()
    proposal = core.official_experience.boundary_proposal()
    boundary = core.business_boundaries.approve(project, proposal.proposal.proposal_id,
        expected_fingerprint=proposal.proposal.proposal_fingerprint, reason="测试用户确认公开业务规则")
    assert len(boundary.permission_intents) == 3
    prepared = core.official_experience.prepare()
    assert prepared.scenario_prepared, prepared.pending_tasks
    with core.uow_factory() as work:
        jobs = work.jobs.list_for_project(project)
        assert len(jobs) == 3
        assert all(job.state.value == "SUCCEEDED" and job.attempt == 1 for job in jobs)
    assert core.checks.preview(project).can_execute
    assert core.official_experience.prepare() == prepared
    assert core.runtime_secrets.model_dump() == {"session_count": 0}


def prepare_sample(core):
    project = core.official_experience.start(consent=True).project_id
    proposal = core.official_experience.boundary_proposal()
    core.business_boundaries.approve(project, proposal.proposal.proposal_id,
        expected_fingerprint=proposal.proposal.proposal_fingerprint, reason="测试用户确认公开业务规则")
    assert core.official_experience.prepare().scenario_prepared
    return project


def test_rebuilt_installer_resumes_persistent_review_without_consuming_again(current_sample, monkeypatch):
    core = current_sample
    project = core.official_experience.start(consent=True).project_id
    proposal = core.official_experience.boundary_proposal()
    core.business_boundaries.approve(project, proposal.proposal.proposal_id,
        expected_fingerprint=proposal.proposal.proposal_fingerprint, reason="测试用户确认公开业务规则")
    finalize = core.recording_lifecycle.finalize
    def interrupted(*args, **kwargs):
        raise RuntimeError("controlled interruption before finalize")
    monkeypatch.setattr(core.recording_lifecycle, "finalize", interrupted)
    with pytest.raises(RuntimeError, match="controlled interruption"):
        core.official_experience.prepare()
    with core.uow_factory() as work:
        first = work.jobs.list_for_project(project)[0]
        before = work.recordings.get(first.recording_id)
        draft = work.flow_drafts.latest(first.recording_id)
        assert before.state.value == "PENDING_REVIEW"
    monkeypatch.setattr(core.recording_lifecycle, "finalize", finalize)
    rebuilt = OfficialScenarioInstaller(core.project_recordings, core.recording_submission, core.job_attempts,
        var_dir=core.var_dir, recording_credentials=core.recording_credentials, lifecycle=core.recording_lifecycle,
        clock_us=lambda: time.time_ns() // 1000, preparation=core.preparation)
    core.official_experience._installer = rebuilt
    assert core.official_experience.prepare().scenario_prepared
    with core.uow_factory() as work:
        assert len(work.jobs.list_for_project(project)) == 3
        assert work.recordings.get(first.recording_id).browser_events == before.browser_events
        assert work.flow_drafts.latest(first.recording_id) == draft
        assert len(work.job_events.list_for_job(first.job_id)) == 3
    assert core.runtime_secrets.model_dump() == {"session_count": 0}


def execute_published(core, project, *, key, change_id=None):
    from product.backend.infra.runtime.jobs.models import ClaimJob
    from product.backend.infra.runtime.jobs.check_requests import CheckRequestStore
    from product.backend.infra.execution.web.check_runtime import check_secret_names
    from product.backend.infra.execution.check_executor import CheckExecutor
    from product.backend.infra.artifacts.check_publication import CheckPublisher
    from product.protocols.check_result import CheckRunnerInput, CheckAssetReference, canonical_check_document
    from product.protocols.check_runtime import canonical_check_runtime_bytes
    from product.protocols.execution_v3 import canonical_execution_request_v3_bytes
    preview = core.checks.preview(project, change_id=change_id)
    assert preview.can_execute, preview
    submitted = core.checks.submit(project, expected_plan_fingerprint=preview.plan_fingerprint,
        idempotency_key=key, change_id=change_id)
    job = core.job_attempts.claim(ClaimJob(job_id=submitted.job.job_id, lease_owner="sample-l3",
        now_us=time.time_ns() // 1000, lease_duration_us=180_000_000)).job
    store = CheckRequestStore(core.var_dir)
    request = store.load(job.job_id, expected_hash=job.request_hash)
    bundle = store.load_bundle(job.job_id, expected_hash=request.config_fingerprint)
    runner_input = CheckRunnerInput(run_id=job.run_id, job_id=job.job_id, attempt=job.attempt,
        lease_owner=job.lease_owner, fencing_token=job.fencing_token, created_at_us=job.created_at_us,
        request_hash=job.request_hash, config_hash=request.config_fingerprint,
        assets=(CheckAssetReference(logical_id="request", sha256=job.request_hash),
            CheckAssetReference(logical_id="runtime", sha256=request.config_fingerprint)))
    attempt = core.paths.jobs / job.job_id / "attempts" / "1-1"
    environment = core.environment_for_secret_names(check_secret_names(bundle))
    output = CheckExecutor(request, bundle, runner_input, environ=environment, attempt_dir=attempt,
        cancellation_requested=lambda: False).execute()
    staging = attempt / "staging"
    (staging / "evidence").mkdir(parents=True)
    (staging / "request.json").write_bytes(canonical_execution_request_v3_bytes(request))
    (staging / "runtime.json").write_bytes(canonical_check_runtime_bytes(bundle))
    (staging / "result.json").write_bytes(canonical_check_document(output.result))
    for document in output.evidence:
        (staging / "evidence" / f"{document.evidence_id}.json").write_bytes(canonical_check_document(document))
    CheckPublisher(core.var_dir, core.uow_factory).publish(staging)
    return core.check_results.package(job.run_id), core.check_story.build(job.run_id)


def test_sample_problem_reaches_published_current_story(current_sample):
    core = current_sample
    project = prepare_sample(core)
    package, story = execute_published(core, project, key="problem")
    if story.verdict.value != "BLOCK" or any(case.verdict.value == "INCONCLUSIVE" for case in package.result.case_results):
        print("CASE_DIAGNOSTIC", [(case.verdict.value, case.reason_codes, case.outcome.model_dump(mode="json"))
            for case in package.result.case_results])
    assert story.verdict.value == "BLOCK", [(case.verdict, case.reason_codes) for case in package.result.case_results]
    deny = next(item for item in story.actions if item.permission.expectation == "DENY")
    assert deny.breakpoint.breakpoint_type == "AUTHORIZATION_LATE"
    assert len(package.request.actions) == 2
    assert sum("ALLOW_REGRESSION" in case.roles for action in package.request.actions for case in action.cases) == 2
    assert all(case.verdict.value == "SAFE" for case in package.result.case_results if case.case_id != deny.case_id), [
        (case.verdict, case.reason_codes, case.outcome) for case in package.result.case_results]


def prepare_changed_sample(core, project):
    from product.backend.workflows.business_boundaries.models import BoundaryMaintenanceCommand
    current = core.official_experience.prepare()
    if "HUMAN_IMPLEMENTATION_REBIND_REQUIRED" in current.pending_tasks:
        draft = core.business_boundaries.maintenance_draft(project)
        proposal = core.business_boundaries.create_maintenance_proposal(project, BoundaryMaintenanceCommand(
            expected_boundary_state_fingerprint=draft.boundary_state_fingerprint, actors=draft.actors,
            actions=draft.actions, permissions=draft.permissions, provenance="测试用户复核当前实现映射"))
        core.business_boundaries.approve(project, proposal.proposal.proposal_id,
            expected_fingerprint=proposal.proposal.proposal_fingerprint, reason="仅复核当前实现，不改业务规则")
        current = core.official_experience.prepare()
    assert current.scenario_prepared, current.pending_tasks


def test_sample_observer_failure_and_fixed_new_run_preserve_original_question(current_sample):
    from product.backend.workflows.official_sample import OfficialScenarioVersion
    core = current_sample
    project = prepare_sample(core)
    original, story = execute_published(core, project, key="original")
    assert story.verdict.value == "BLOCK"
    contract = core.check_repairs.contracts(original.result.run_id)[0]
    assert len(contract.regressions) == 2
    policy = core.business_boundaries.view(project).policy_epoch
    descriptor_hash = core.check_registry.snapshot(project).proofs[0].reference.descriptor_fingerprint
    before_switch = len(core.check_results.list_for_project(project))
    limited = core.official_experience.switch_version(version=OfficialScenarioVersion.EVIDENCE_LIMITED)
    assert len(core.check_results.list_for_project(project)) == before_switch
    prepare_changed_sample(core, project)
    assert core.business_boundaries.view(project).policy_epoch == policy
    insufficient, limited_story = execute_published(core, project, key="limited", change_id=limited.vulnerable_change_id)
    if limited_story.verdict.value != "INCONCLUSIVE":
        print("LIMITED_DIAGNOSTIC", [(case.verdict.value, case.reason_codes, case.outcome.model_dump(mode="json"))
            for case in insufficient.result.case_results])
    assert limited_story.verdict.value == "INCONCLUSIVE"
    fixed = core.official_experience.switch_version(version=OfficialScenarioVersion.FIXED, repair_reference=contract.reference())
    assert len(core.check_results.list_for_project(project)) == before_switch + 1
    prepare_changed_sample(core, project)
    assert core.business_boundaries.view(project).policy_epoch == policy
    assert core.check_registry.snapshot(project).proofs[0].reference.descriptor_fingerprint == descriptor_hash
    repaired, fixed_story = execute_published(core, project, key="fixed", change_id=fixed.repair_change_id)
    verification = core.check_repairs.verification(repaired.result.run_id)
    if fixed_story.verdict.value != "PASS" or verification.status != "VERIFIED":
        print("FIXED_DIAGNOSTIC", verification.model_dump(mode="json"),
            [(case.verdict.value, case.reason_codes, case.outcome.model_dump(mode="json")) for case in repaired.result.case_results])
    assert fixed_story.verdict.value == "PASS"
    assert verification.status == "VERIFIED"
    assert core.project_repair.evaluate(project).status == "VERIFIED"
    assert len({original.result.run_id, insufficient.result.run_id, repaired.result.run_id}) == 3
    assert core.check_results.package(original.result.run_id) == original


def test_current_flow_bytes_and_descriptor_rejections_preserve_frozen_material(current_sample):
    import hashlib
    import json
    from product.backend.core.errors import JiejianError
    from product.backend.workflows.checks.local_observer_wiring import load_local_observer_wiring
    from product.backend.workflows.recording.lifecycle import RecordingLifecycle
    core = current_sample
    project = prepare_sample(core)
    boundary = core.business_boundaries.view(project)
    with core.uow_factory() as work:
        recordings = [work.recordings.get(work.action_preparation.execution(action.action_id, action.revision).source_recording_id) for action in boundary.actions]
    paths = [RecordingLifecycle.flow_path(core.var_dir, item) for item in recordings]
    before = {str(path): (path.read_bytes(), hashlib.sha256(path.read_bytes()).hexdigest()) for path in paths}
    assert core.checks.preview(project).can_execute
    assert before == {str(path): (path.read_bytes(), hashlib.sha256(path.read_bytes()).hexdigest()) for path in paths}
    runtime = core.official_samples.active
    path = runtime.check_descriptor_path
    raw = path.read_bytes()
    original = json.loads(raw)
    def load():
        return load_local_observer_wiring(str(path), var_dir=core.var_dir, action_id=boundary.actions[0].action_id,
            expected_origin=runtime.origin, expected_resource_id="campus-digital-museum-package")
    valid = load()
    assert len(valid.observers) == 6
    for fault in ("origin", "resource", "credential", "unknown", "duplicate", "path"):
        value = json.loads(raw)
        if fault == "origin":
            value["application"]["origin"] = "http://127.0.0.1:1"
        elif fault == "resource":
            value["application"]["resource_id"] = "other-resource"
        elif fault == "credential":
            value["owner_api"]["credential_ref"] = "inline-test-secret"
        elif fault == "unknown":
            value["extra"] = True
        elif fault == "path":
            value["sqlite"]["relative_path"] = "../outside.sqlite"
        encoded = json.dumps(value).encode()
        if fault == "duplicate":
            encoded = b'{"application":{},' + encoded[1:]
        try:
            path.write_bytes(encoded)
            with pytest.raises(JiejianError):
                load()
        finally:
            path.write_bytes(raw)
    assert load().descriptor_fingerprint == valid.descriptor_fingerprint


def test_real_zip_without_task_binding_does_not_promote_original_202(current_sample, monkeypatch):
    core = current_sample
    project = prepare_sample(core)
    original = core.check_registry.snapshot(project)
    proofs = tuple(proof.model_copy(update={"auxiliary_sources": tuple(source for source in proof.auxiliary_sources
        if source.spec.observer_type.value != "ASYNC_TASK_STATUS")}) for proof in original.proofs)
    core.check_registry.register(original.model_copy(update={"proofs": proofs}), expected_fingerprint=original.fingerprint)
    calls = []
    from product.backend.infra.execution.web.check_runtime import CheckWebRuntime
    execute = CheckWebRuntime.execute_flow
    def counted(self, action, case, **kwargs):
        calls.append(case.case_id)
        return execute(self, action, case, **kwargs)
    monkeypatch.setattr(CheckWebRuntime, "execute_flow", counted)
    package, _ = execute_published(core, project, key="zip-without-completion")
    export = next(action for action in package.bundle.actions if any(proof.spec.observer_type.value == "AZURE_BLOB_OBJECT" for proof in proofs if proof.effect.effect_id in {value.effect_id for value in action.proofs}))
    allow = next(case for action in package.request.actions if action.action_id == export.action_id for case in action.cases if case.permission.expectation == "ALLOW")
    result = next(item for item in package.result.case_results if item.case_id == allow.case_id)
    assert export.steps[-1].classifier.completion_binding is None
    assert result.outcome.http_status == 202 and result.outcome.execution_outcome == "UNKNOWN"
    document = next(item for item in package.evidence if item.case.case_id == allow.case_id)
    assert any(item.level == "VERDICT_REQUIRED" and item.state == "CONFIRMED" for item in document.observations)
    assert calls.count(allow.case_id) == 1
