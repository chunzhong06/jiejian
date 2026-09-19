# 验证真实文件提升与 SQLite 收据事务的失败窗口；恢复不重新执行任何目标。
import pytest

from product.backend.core.errors import JiejianError
from product.backend.core.lifecycle import CaseVerdict, JobState, RunVerdict
from product.backend.infra.artifacts.check_packages import check_final_directory, validate_check_package
from product.backend.infra.artifacts.check_publication import CheckPublisher
from product.backend.infra.runtime.jobs.models import RequestCancellation
from product.backend.infra.storage import StorageUnitOfWork
from product.protocols.check_result import canonical_check_document
from tests.fixtures.check_publication import package_parts, NOW


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
