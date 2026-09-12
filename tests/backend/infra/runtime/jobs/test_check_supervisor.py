# 当前监督器故障窗口：持久取消、旧租约、非零退出和清理错误均不发布或重放 TARGET。
from functools import partial
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import JobState, ProjectStatus
from product.backend.infra.runtime.check_runner.supervisor import CheckRunnerSupervisor
from product.backend.infra.runtime.jobs.check_requests import CheckRequestStore
from product.backend.infra.runtime.jobs.models import RequestCancellation
from product.backend.infra.storage import ProjectRecord, StorageUnitOfWork
from tests.fixtures.check_execution import execution_pair

NOW = 1_790_000_000_000_000


@pytest.fixture
def supervisor_parts(worker_services, tmp_path):
    request, bundle = execution_pair()
    factory = partial(StorageUnitOfWork, worker_services.session_factory)
    with factory() as work:
        work.projects.add(ProjectRecord(project_id=request.project_id, name="监督器边界", status=ProjectStatus.READY,
            created_at_us=NOW, updated_at_us=NOW))
        work.commit()
    store = CheckRequestStore(tmp_path)
    job_id = "job_" + "1" * 32
    request_hash, _ = store.write(job_id, request)
    store.write_bundle(job_id, bundle)
    submitted = worker_services.queue.submit(worker_services.submit_request(project_id=request.project_id,
        job_id=job_id, request_hash=request_hash, plan_fingerprint=request.plan_fingerprint,
        source_fingerprint=request.source_fingerprint, policy_epoch=request.policy_epoch,
        engine_version=request.engine_version, max_attempts=1))
    supervisor = CheckRunnerSupervisor(tmp_path, lease_owner="worker", uow_factory=factory,
        attempts=worker_services.attempts, environ={"CHECK_TEST_BEARER": "bounded-test-secret"}, clock_us=lambda: NOW + 20)
    return supervisor, factory, submitted.job, worker_services


@pytest.mark.parametrize("mode", ["cancel", "timeout", "nonzero", "lost_fence", "cleanup_after_timeout"])
def test_supervisor_does_not_publish_or_retry_uncertain_attempt(supervisor_parts, monkeypatch, mode):
    supervisor, factory, initial, services = supervisor_parts
    module = "product.backend.infra.runtime.check_runner.supervisor"
    calls = []
    process = SimpleNamespace(returncode=0 if mode != "nonzero" else 64, poll=lambda: 0)
    def spawn(*args, **kwargs):
        calls.append((args, kwargs))
        return process
    monkeypatch.setattr(module + ".spawn_python_module", spawn)
    monkeypatch.setattr(module + ".release_process_tree", lambda process: None)
    monkeypatch.setattr(module + ".terminate_process_tree", lambda *args: None)
    def forbidden(*args, **kwargs):
        raise AssertionError("failed attempt must not publish")
    monkeypatch.setattr(supervisor._publisher, "publish", forbidden)
    def monitor(_process, job, **kwargs):
        assert kwargs["max_duration_us"] == 300_000_000
        if mode == "cancel":
            services.queue.request_cancellation(RequestCancellation(job_id=job.job_id, now_us=NOW + 21))
            monkeypatch.setattr(supervisor, "_clock", lambda: NOW + 22)
        if mode == "lost_fence":
            with factory() as work:
                work._require_session().execute(text("UPDATE jobs SET fencing_token = fencing_token + 1 WHERE job_id = :id"), {"id": job.job_id})
                work.commit()
            raise JiejianError(ErrorCode.JOB_LEASE_MISMATCH, "租约变化")
        return mode in ("timeout", "cleanup_after_timeout"), False
    monkeypatch.setattr(supervisor._control, "monitor", monitor)
    if mode == "cleanup_after_timeout":
        def failed_release(_process):
            raise JiejianError(ErrorCode.PROCESS_TREE_FAILED, "释放失败")
        monkeypatch.setattr(module + ".release_process_tree", failed_release)
    if mode == "cancel":
        assert supervisor.run_job(initial.job_id) is None
    else:
        with pytest.raises(JiejianError) as caught:
            supervisor.run_job(initial.job_id)
        expected = ErrorCode.JOB_LEASE_MISMATCH if mode == "lost_fence" else (
            ErrorCode.RUNNER_PROTOCOL_INVALID if mode == "nonzero" else ErrorCode.RUNNER_TIMEOUT)
        assert caught.value.code == expected.value
    with factory() as work:
        job = work.jobs.get(initial.job_id)
        assert job.state is (JobState.CANCELLED if mode == "cancel" else JobState.RUNNING if mode == "lost_fence" else JobState.FAILED)
        assert work.check_publications.get(initial.run_id) is None
        assert work.runs.get(initial.run_id).verdict is None
    with pytest.raises(JiejianError, match="STATE_PRECONDITION"):
        supervisor.run_job(initial.job_id)
    assert len(calls) == 1
