# 当前 CHECK 的发布 CAS 同时约束请求、取消和租约，并保留恢复失败后的 BLOCK。
import pytest

from product.backend.core.lifecycle import JobState, RunLifecycle, RunVerdict
from product.backend.infra.runtime.jobs.models import ClaimJob, RequestCancellation
from product.backend.infra.storage import StorageUnitOfWork
from product.backend.infra.storage.results.check_publications import CheckPublicationRecord

NOW = 1_790_000_000_000_000


def claim(worker_services):
    submitted = worker_services.queue.submit(worker_services.submit_request())
    return worker_services.attempts.claim(ClaimJob(job_id=submitted.job.job_id, lease_owner="worker-1",
        now_us=NOW + 10, lease_duration_us=1000)).job


def complete(work, job, **updates):
    return work.job_control.complete_published_result(**(dict(job_id=job.job_id, run_id=job.run_id,
        attempt=job.attempt, lease_owner=job.lease_owner, fencing_token=job.fencing_token,
        lifecycle=RunLifecycle.SAFETY_STOPPED, verdict=RunVerdict.BLOCK,
        completed_at_us=NOW + 20, require_active_lease=True, request_hash=job.request_hash) | updates))


def test_safety_stop_and_receipt_commit_in_same_transaction(worker_services):
    job = claim(worker_services)
    receipt = CheckPublicationRecord(run_id=job.run_id, job_id=job.job_id, attempt=job.attempt,
        fencing_token=job.fencing_token, request_hash=job.request_hash,
        result_hash="b" * 64, manifest_hash="c" * 64, published_at_us=NOW + 20)
    with StorageUnitOfWork(worker_services.session_factory) as work:
        completed = complete(work, job)
        assert completed[0].state is JobState.SUCCEEDED
        assert completed[1].verdict is RunVerdict.BLOCK
        work.check_publications.add(receipt)
        work.commit()
    with StorageUnitOfWork(worker_services.session_factory) as work:
        assert work.check_publications.get(job.run_id) == receipt
        assert work.runs.get(job.run_id).lifecycle is RunLifecycle.SAFETY_STOPPED
        assert complete(work, job) is None


@pytest.mark.parametrize("updates", [dict(fencing_token=2), dict(attempt=2), dict(lease_owner="other"),
    dict(request_hash="f" * 64), dict(completed_at_us=NOW + 1010, require_active_lease=False)])
def test_stale_or_mismatched_publication_has_no_database_effect(worker_services, updates):
    job = claim(worker_services)
    with StorageUnitOfWork(worker_services.session_factory) as work:
        assert complete(work, job, **updates) is None
        work.commit()
    with StorageUnitOfWork(worker_services.session_factory) as work:
        assert work.jobs.get(job.job_id).state is JobState.RUNNING
        assert work.runs.get(job.run_id).verdict is None
        assert work.check_publications.get(job.run_id) is None


def test_cancelled_check_cannot_publish_success(worker_services):
    job = claim(worker_services)
    worker_services.queue.request_cancellation(RequestCancellation(job_id=job.job_id, now_us=NOW + 15))
    with StorageUnitOfWork(worker_services.session_factory) as work:
        assert complete(work, job) is None
        assert work.runs.get(job.run_id).verdict is None


def test_aborted_publication_transaction_does_not_finish_job(worker_services):
    job = claim(worker_services)
    with StorageUnitOfWork(worker_services.session_factory) as work:
        assert complete(work, job) is not None
        # 模拟文件已形成但收据事务失败；退出必须回滚完成态，不能重跑目标补结果。
    with StorageUnitOfWork(worker_services.session_factory) as work:
        assert work.jobs.get(job.job_id).state is JobState.RUNNING
        assert work.runs.get(job.run_id).verdict is None
