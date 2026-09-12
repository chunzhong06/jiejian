# 验证固定录制配方共享正式事务、持久幂等与失败回滚，不启动浏览器或 Worker。
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
import time

import pytest

from product.backend.core.lifecycle import JobState
from product.backend.core.recording import RecordingState
from product.backend.infra.runtime.jobs.models import ClaimJob
from tests.fixtures.recording import RecordingContext, captured_result
from tests.backend.workflows.recording.test_project_submission import _arguments


def _capture(context):
    events = captured_result("rec_" + "a" * 32, project_id=context.project_id).events
    identity = context.harness.identities[0].identity_id
    return tuple(event.model_copy(update={"identity_id": identity}) for event in events)


def test_atomic_recipe_is_persistent_and_not_dispatchable(tmp_path, monkeypatch):
    context = RecordingContext(tmp_path)
    core = context.harness.core
    original = core.recording_submission._persist_success_in_work
    observed = []
    def inspect(work, **kwargs):
        # 第二个连接只读调度候选，不会被本事务未提交的 PENDING/RUNNING 吸引。
        with context.uow_factory() as other:
            observed.append(other.jobs.next_pending(time.time_ns() // 1000))
            assert other.jobs.get(kwargs["job_id"]) is None
        return original(work, **kwargs)
    monkeypatch.setattr(core.recording_submission, "_persist_success_in_work", inspect)
    try:
        first = core.project_recordings.submit_captured(context.project_id, events=_capture(context), **_arguments(context))
        assert first.result.job.state is JobState.SUCCEEDED
        assert (first.result.job.attempt, first.result.job.fencing_token) == (1, 1)
        assert first.result.recording.state is RecordingState.PENDING_REVIEW
        second = core.project_recordings.submit_captured(context.project_id, events=_capture(context), **_arguments(context))
        assert second.request == first.request
        assert not second.result.created
        with context.uow_factory() as work:
            assert len(work.jobs.list_for_project(context.project_id)) == 1
            assert len(work.job_events.list_for_job(first.result.job.job_id)) == 3
        assert context.attempts.claim(ClaimJob(lease_owner="ordinary-worker", now_us=time.time_ns() // 1000,
            lease_duration_us=60_000_000)) is None
        assert observed == [None]
        assert core.runtime_secrets.model_dump() == {"session_count": 0}
    finally:
        context.harness.close()


@pytest.mark.parametrize("boundary", ["_submit_transaction_in_work", "_persist_success_in_work", "claim_in_work"])
def test_atomic_recipe_rolls_back_all_database_records(tmp_path, monkeypatch, boundary):
    context = RecordingContext(tmp_path)
    core = context.harness.core
    owner = core.job_attempts if boundary == "claim_in_work" else core.recording_submission
    original = getattr(owner, boundary)
    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("injected recipe rollback")
    monkeypatch.setattr(owner, boundary, fail)
    try:
        with pytest.raises(RuntimeError, match="injected recipe rollback"):
            core.project_recordings.submit_captured(context.project_id, events=_capture(context), **_arguments(context))
        with context.uow_factory() as work:
            assert work.jobs.list_for_project(context.project_id) == ()
        assert core.runtime_secrets.model_dump() == {"session_count": 0}
    finally:
        context.harness.close()


def test_simultaneous_fixed_submissions_consume_once(tmp_path, monkeypatch):
    context = RecordingContext(tmp_path)
    core = context.harness.core
    barrier = Barrier(2)
    original = core.recording_submission.captured_existing
    def synchronize(*args):
        result = original(*args)
        if result is None:
            barrier.wait(timeout=10)
        return result
    monkeypatch.setattr(core.recording_submission, "captured_existing", synchronize)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(core.project_recordings.submit_captured, context.project_id,
                events=_capture(context), **_arguments(context)) for _ in range(2)]
            results = [future.result(timeout=20) for future in futures]
        assert results[0].request == results[1].request
        with context.uow_factory() as work:
            jobs = work.jobs.list_for_project(context.project_id)
            assert len(jobs) == 1
            assert len(work.job_events.list_for_job(jobs[0].job_id)) == 3
            assert (jobs[0].attempt, jobs[0].fencing_token) == (1, 1)
    finally:
        context.harness.close()


def test_independent_connection_claim_during_transaction_cannot_steal_job(tmp_path, monkeypatch):
    from product.backend.infra.storage.execution.job_control import JobControlRepository
    context = RecordingContext(tmp_path)
    core = context.harness.core
    entered = Event()
    futures = []
    claim = JobControlRepository.claim
    persist = core.recording_submission._persist_success_in_work
    def marked_claim(self, **kwargs):
        if kwargs["lease_owner"] == "competing-worker":
            entered.set()
        return claim(self, **kwargs)
    monkeypatch.setattr(JobControlRepository, "claim", marked_claim)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            def before_commit(work, **kwargs):
                futures.append(pool.submit(context.attempts.claim, ClaimJob(lease_owner="competing-worker",
                    now_us=time.time_ns() // 1000, lease_duration_us=60_000_000)))
                assert entered.wait(timeout=5)
                return persist(work, **kwargs)
            monkeypatch.setattr(core.recording_submission, "_persist_success_in_work", before_commit)
            result = core.project_recordings.submit_captured(context.project_id, events=_capture(context), **_arguments(context))
            assert futures[0].result(timeout=10) is None
            assert result.result.job.fencing_token == 1
        assert context.attempts.claim(ClaimJob(lease_owner="after-commit", now_us=time.time_ns() // 1000,
            lease_duration_us=60_000_000)) is None
    finally:
        context.harness.close()


def test_fixed_key_conflicts_with_changed_business_input_before_new_session(tmp_path):
    from product.backend.core.errors import JiejianError, ErrorCode
    context = RecordingContext(tmp_path)
    core = context.harness.core
    try:
        core.project_recordings.submit_captured(context.project_id, events=_capture(context), **_arguments(context))
        with pytest.raises(JiejianError) as error:
            core.project_recordings.submit_captured(context.project_id, events=_capture(context),
                **(_arguments(context) | {"duration_seconds": 59}))
        assert error.value.code == ErrorCode.JOB_IDEMPOTENCY_CONFLICT.value
        assert core.runtime_secrets.model_dump() == {"session_count": 0}
    finally:
        context.harness.close()
