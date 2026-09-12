# 验证真实文件提升与 SQLite 收据事务的失败窗口；恢复不重新执行任何目标。
import hashlib
from functools import partial

import pytest

from product.backend.core.errors import JiejianError
from product.backend.core.lifecycle import CaseVerdict, JobState, ProjectStatus, RunLifecycle, RunVerdict
from product.backend.infra.artifacts.check_packages import check_final_directory, validate_check_package
from product.backend.infra.artifacts.check_publication import CheckPublisher
from product.backend.infra.runtime.jobs.models import ClaimJob, RequestCancellation
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.storage import ProjectRecord, StorageUnitOfWork
from product.protocols.check_result import CheckCaseOutcome, CheckCaseResult, CheckRunnerResult, canonical_check_document, seal_check_evidence
from product.protocols.check_runtime import canonical_check_runtime_bytes
from product.protocols.execution_v3 import canonical_execution_request_v3_bytes
from tests.fixtures.check_execution import execution_pair

NOW = 1_790_000_000_000_000


@pytest.fixture
def package_parts(worker_services, tmp_path, request):
    options = getattr(request, "param", {})
    request, bundle = execution_pair(**options)
    factory = partial(StorageUnitOfWork, worker_services.session_factory)
    with factory() as work:
        work.projects.add(ProjectRecord(project_id=request.project_id, name="发布检查测试", status=ProjectStatus.READY,
            created_at_us=NOW, updated_at_us=NOW))
        work.commit()
    raw_request = canonical_execution_request_v3_bytes(request)
    request_hash = hashlib.sha256(raw_request).hexdigest()
    submitted = worker_services.queue.submit(worker_services.submit_request(project_id=request.project_id,
        request_hash=request_hash, plan_fingerprint=request.plan_fingerprint, source_fingerprint=request.source_fingerprint,
        policy_epoch=request.policy_epoch, engine_version=request.engine_version, max_attempts=1))
    job = worker_services.attempts.claim(ClaimJob(job_id=submitted.job.job_id, lease_owner="check-worker",
        now_us=NOW + 10, lease_duration_us=1000)).job
    directory = RuntimePaths(tmp_path).jobs / job.job_id / "attempts" / "1-1" / "staging"
    (directory / "evidence").mkdir(parents=True)
    (directory / "request.json").write_bytes(raw_request)
    (directory / "runtime.json").write_bytes(canonical_check_runtime_bytes(bundle))
    results = []
    outcome = CheckCaseOutcome(execution_outcome="UNKNOWN", actual_identity_status="UNKNOWN",
        baseline_trusted=False, recovery_verified=False, run_correlated=False, resource_correlated=False)
    for action in request.actions:
        for case in action.cases:
            evidence = seal_check_evidence(run_id=job.run_id, job_id=job.job_id, attempt=job.attempt,
                action_id=action.action_id, action_revision=action.action_revision, request_hash=request_hash,
                config_hash=request.config_fingerprint, case=case, outcome=outcome, observations=())
            (directory / "evidence" / f"{evidence.evidence_id}.json").write_bytes(canonical_check_document(evidence))
            results.append(CheckCaseResult(case_id=case.case_id, action_id=action.action_id,
                verdict=CaseVerdict.INCONCLUSIVE, reason_codes=("ACTUAL_IDENTITY_UNKNOWN",),
                evidence_ids=(evidence.evidence_id,), outcome=outcome))
    result = CheckRunnerResult(run_id=job.run_id, job_id=job.job_id, attempt=job.attempt,
        lease_owner=job.lease_owner, fencing_token=job.fencing_token, request_hash=request_hash,
        config_hash=request.config_fingerprint, result_type="SUCCESS", lifecycle=RunLifecycle.COMPLETED,
        case_results=tuple(results), verdict=RunVerdict.INCONCLUSIVE, started_at_us=NOW + 11, completed_at_us=NOW + 19)
    (directory / "result.json").write_bytes(canonical_check_document(result))
    return tmp_path, factory, job, directory, result


def test_publication_is_immutable_and_repeat_reconciliation_is_idempotent(package_parts):
    var_dir, factory, job, directory, result = package_parts
    publisher = CheckPublisher(var_dir, factory, clock_us=lambda: NOW + 20)
    package = publisher.publish(directory)
    assert not directory.exists()
    assert package.result == result
    assert publisher.complete_existing(package.directory) == package
    with factory() as work:
        assert work.jobs.get(job.job_id).state is JobState.SUCCEEDED
        assert work.runs.get(job.run_id).verdict is RunVerdict.INCONCLUSIVE
        receipt = work.check_publications.get(job.run_id)
        assert receipt.request_hash == job.request_hash
        assert len(work.evidence.list_for_run(job.run_id)) == len(result.case_results)
        assert sum(item.event_type == "JOB_SUCCEEDED" for item in work.job_events.list_for_job(job.job_id)) == 1


def test_file_promoted_database_commit_failed_recovers_after_lease_expiry(package_parts):
    var_dir, factory, job, directory, result = package_parts
    class FailedCommit(StorageUnitOfWork):
        def commit(self):
            raise RuntimeError("injected commit failure")
    failing = lambda **kw: FailedCommit(factory.args[0], **kw)
    publisher = CheckPublisher(var_dir, failing, clock_us=lambda: NOW + 20)
    with pytest.raises(RuntimeError, match="injected"):
        publisher.publish(directory)
    final = check_final_directory(var_dir, job.project_id, job.run_id)
    assert final.is_dir() and not directory.exists()
    with factory() as work:
        assert work.jobs.get(job.job_id).state is JobState.RUNNING
        assert work.check_publications.get(job.run_id) is None
    recovered = CheckPublisher(var_dir, factory, clock_us=lambda: NOW + 2000).complete_existing(final)
    assert recovered.result == result
    with factory() as work:
        assert work.jobs.get(job.job_id).state is JobState.SUCCEEDED


@pytest.mark.parametrize("mutation", ["extra", "missing_evidence", "cross_case", "hash"])
def test_invalid_staging_never_changes_database(package_parts, mutation):
    var_dir, factory, job, directory, result = package_parts
    if mutation == "extra":
        (directory / "unexpected.json").write_bytes(b"{}")
    elif mutation == "missing_evidence":
        next((directory / "evidence").iterdir()).unlink()
    elif mutation == "cross_case":
        changed = result.model_copy(update={"case_results": result.case_results[:-1]})
        (directory / "result.json").write_bytes(canonical_check_document(changed))
    else:
        path = next((directory / "evidence").iterdir())
        path.write_bytes(path.read_bytes().replace(b'"actual_identity_status":"UNKNOWN"', b'"actual_identity_status":"MATCH"'))
    with pytest.raises(JiejianError):
        CheckPublisher(var_dir, factory, clock_us=lambda: NOW + 20).publish(directory)
    with factory() as work:
        assert work.jobs.get(job.job_id).state is JobState.RUNNING
        assert work.check_publications.get(job.run_id) is None


def test_cancelled_check_cannot_promote_files(package_parts, worker_services):
    var_dir, factory, job, directory, _result = package_parts
    worker_services.queue.request_cancellation(RequestCancellation(job_id=job.job_id, now_us=NOW + 15))
    with pytest.raises(JiejianError):
        CheckPublisher(var_dir, factory, clock_us=lambda: NOW + 20).publish(directory)
    assert directory.exists()


def test_published_file_tampering_is_rejected_on_read(package_parts):
    var_dir, factory, _job, directory, _result = package_parts
    package = CheckPublisher(var_dir, factory, clock_us=lambda: NOW + 20).publish(directory)
    path = package.directory / "runtime.json"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(JiejianError):
        validate_check_package(package.directory, published=True)


@pytest.mark.parametrize("forgery", ["case", "aggregate"])
def test_publisher_rejects_verdict_not_supported_by_frozen_facts(package_parts, forgery):
    var_dir, factory, job, directory, result = package_parts
    if forgery == "case":
        result = result.model_copy(update={"case_results": tuple(item.model_copy(update={"verdict": CaseVerdict.SAFE})
            for item in result.case_results), "verdict": RunVerdict.PASS})
    else:
        result = result.model_copy(update={"verdict": RunVerdict.BLOCK})
    (directory / "result.json").write_bytes(canonical_check_document(result))
    with pytest.raises(JiejianError):
        CheckPublisher(var_dir, factory, clock_us=lambda: NOW + 20).publish(directory)
    with factory() as work:
        assert work.jobs.get(job.job_id).state is JobState.RUNNING
        assert work.runs.get(job.run_id).verdict is None
