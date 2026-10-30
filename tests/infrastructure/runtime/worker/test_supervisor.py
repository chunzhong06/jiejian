# 验证作业运行时中的Worker 监督与失败回收。

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

import product.backend.infrastructure.runtime.worker.supervisor as worker_supervisor_module
from product.backend.domain.lifecycle import JobState, RunLifecycle
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.infrastructure.storage.unit_of_work import StorageUnitOfWork
from product.backend.infrastructure.storage.db import create_session_factory, create_sqlite_engine, default_database_path, prepare_database
from product.backend.infrastructure.runtime.jobs.attempts import JobAttempts
from product.backend.infrastructure.runtime.jobs.models import ClaimJob, RequestCancellation, WaitingFatalFailure
from product.backend.infrastructure.runtime.jobs.queue import JobQueue
from product.backend.infrastructure.runtime.jobs.models import SubmitJob
from product.backend.infrastructure.runtime.jobs.check_requests import CheckRequestStore
from tests.support.builders.checks.check_execution import execution_pair
from product.backend.domain.lifecycle import ProjectStatus
from product.backend.infrastructure.storage.applications.projects import ProjectRecord
from types import SimpleNamespace
from product.backend.infrastructure.runtime.worker.supervisor import LocalWorkerSupervisor
from product.backend.infrastructure.runtime.worker.lifetime import WorkerLifetimeLock

pytestmark = [pytest.mark.level3, pytest.mark.database]

NOW_US = 1_790_000_000_000_000


@dataclass(frozen=True)
class RuntimeParts:
    engine: Engine
    uow_factory: object
    request_store: CheckRequestStore
    queue: JobQueue
    attempts: JobAttempts


def _runtime(var_dir: Path) -> RuntimeParts:
    database_path = default_database_path(var_dir)
    prepare_database(database_path)
    engine = create_sqlite_engine(database_path)
    factory = create_session_factory(engine)
    uow_factory = partial(StorageUnitOfWork, factory)
    request_store = CheckRequestStore(var_dir)
    return RuntimeParts(
        engine=engine,
        uow_factory=uow_factory,
        request_store=request_store,
        queue=JobQueue(uow_factory),
        attempts=JobAttempts(uow_factory, jitter_source=lambda _: 0),
    )


def _submit(parts: RuntimeParts, suffix: str = "3"):
    # 控制器级测试冻结当前 CHECK 输入，不依赖已退役的 ACTIVE_RUN 提交。
    current, bundle = execution_pair(state_changing=True)
    with parts.uow_factory() as work:
        if work.projects.get(current.project_id) is None:
            work.projects.add(ProjectRecord(project_id=current.project_id, name="进程生命周期测试",
                status=ProjectStatus.READY, created_at_us=NOW_US, updated_at_us=NOW_US))
        work.commit()
    job_id = f"job_{suffix * 32}"
    parts.request_store.write_bundle(job_id, bundle)
    request_hash, _ = parts.request_store.write(job_id, current)
    return parts.queue.submit(SubmitJob(project_id=current.project_id, operation_type="CHECK",
        request_hash=request_hash, plan_fingerprint=current.plan_fingerprint,
        source_fingerprint=current.source_fingerprint, policy_epoch=current.policy_epoch, engine_version="supervisor-test",
        idempotency_key=f"supervisor-{suffix}", max_attempts=3, available_at_us=NOW_US,
        now_us=NOW_US, run_id=f"run_{suffix * 32}", job_id=job_id))


def _job(parts: RuntimeParts, job_id: str):
    with parts.uow_factory() as work:
        return work.jobs.get(job_id)


@pytest.mark.parametrize('changed', ['lease', 'fence', 'terminal'])
def test_recovery_candidate_never_reconciles_a_changed_authoritative_job(tmp_path, monkeypatch, changed):
    candidate = SimpleNamespace(job_id='job_'+'9'*32, lease_owner='old-worker', fencing_token=1)
    job = SimpleNamespace(lease_owner='old-worker', fencing_token=1, state=JobState.RUNNING)
    if changed == 'lease': job.lease_owner = 'new-worker'
    elif changed == 'fence': job.fencing_token = 2
    else: job.state = JobState.SUCCEEDED
    manager = object.__new__(LocalWorkerSupervisor)
    manager.var_dir = tmp_path
    manager._read_job = lambda job_id: job
    manager._reconcile_check = lambda job: pytest.fail('stale recovery must not publish another lease')
    monkeypatch.setattr(WorkerLifetimeLock, 'execution_has_exited', lambda *args: True)
    manager._confirm_exited_recovery(candidate, NOW_US)


class _TerminalJobQueue:
    def request_cancellation(self, _command: RequestCancellation) -> None:
        raise JiejianError(ErrorCode.JOB_TERMINAL_CONFLICT, "终态任务不能取消")


class _ExitedWorker:
    def __init__(self, returncode: int = 1) -> None:
        self.returncode = returncode

    def poll(self) -> int:
        return self.returncode


def test_local_supervisor_accepts_terminal_conflict_during_shutdown(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    manager = LocalWorkerSupervisor(
        tmp_path / "var",
        lambda: None,
        job_queue=_TerminalJobQueue(),
    )
    manager._job_id = "job_" + "f" * 32

    with caplog.at_level("ERROR", logger="jiejian.runtime.worker_supervisor"):
        manager._request_worker_cancellation()

    assert not any(
        getattr(record, "event_code", None) == "WORKER_CANCEL_REQUEST_FAILED"
        for record in caplog.records
    )


def test_local_supervisor_nonzero_preclaim_exit_launches_once_and_fails_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    parts = _runtime(tmp_path / "var")
    launches: list[str] = []

    class FakeDispatcher:
        def __init__(self, **_kwargs) -> None:
            pass

        def start(self, *, job_id: str, **_kwargs):
            launches.append(job_id)
            return _ExitedWorker()

    monkeypatch.setattr(worker_supervisor_module, "WorkerDispatcher", FakeDispatcher)
    try:
        submitted = _submit(parts, "4")
        manager = LocalWorkerSupervisor(
            tmp_path / "var",
            parts.uow_factory,
            parts.queue,
            attempt_service=parts.attempts,
            clock_us=lambda: NOW_US + 10,
        )

        manager._start_job(submitted.job)
        manager._reap_finished_worker()

        with parts.uow_factory() as work:
            job = work.jobs.get(submitted.job.job_id)
            run = work.runs.get(submitted.run.run_id)
            events = work.job_events.list_for_job(submitted.job.job_id)
        assert launches == [submitted.job.job_id]
        assert job is not None and job.state is JobState.FAILED
        assert job.attempt == 0 and job.fencing_token == 0
        assert run is not None and run.lifecycle is RunLifecycle.FAILED
        assert run.verdict is None
        assert [event.event_type for event in events if event.event_type in {"JOB_SUBMITTED", "JOB_FAILED"}] == [
            "JOB_SUBMITTED",
            "JOB_FAILED",
        ]
        assert manager._next_job() is None
    finally:
        parts.engine.dispose()


@pytest.mark.parametrize("failure_point", ("request_load", "process_start"))
def test_local_supervisor_bootstrap_failures_finish_waiting_job(
    tmp_path: Path,
    monkeypatch,
    failure_point: str,
) -> None:
    parts = _runtime(tmp_path / "var")

    class FailingRequestStore:
        def __init__(self, _var_dir: Path) -> None:
            pass

        def load(self, *_args, **_kwargs):
            raise JiejianError(ErrorCode.JOB_REQUEST_MISSING, "request missing")

    class FailingDispatcher:
        def __init__(self, **_kwargs) -> None:
            pass

        def start(self, **_kwargs):
            raise OSError("worker start failed")

    try:
        submitted = _submit(parts, "5")
        if failure_point == "request_load":
            monkeypatch.setattr(
                worker_supervisor_module,
                "CheckRequestStore",
                FailingRequestStore,
            )
        else:
            monkeypatch.setattr(
                worker_supervisor_module,
                "WorkerDispatcher",
                FailingDispatcher,
            )
        manager = LocalWorkerSupervisor(
            tmp_path / "var",
            parts.uow_factory,
            parts.queue,
            attempt_service=parts.attempts,
            clock_us=lambda: NOW_US + 10,
        )

        manager._start_job(submitted.job)

        with parts.uow_factory() as work:
            job = work.jobs.get(submitted.job.job_id)
            run = work.runs.get(submitted.run.run_id)
            events = work.job_events.list_for_job(submitted.job.job_id)
        assert job is not None and job.state is JobState.FAILED
        assert run is not None and run.lifecycle is RunLifecycle.FAILED
        assert events[-1].event_type == "JOB_FAILED"
        assert events[-1].metadata["reason_code"] == "WORKER_FATAL"
    finally:
        parts.engine.dispose()


@pytest.mark.parametrize("database_state", ("failed", "running"))
def test_local_supervisor_exit_accepts_terminal_or_closes_owned_running_state(
    tmp_path: Path,
    database_state: str,
) -> None:
    parts = _runtime(tmp_path / "var")
    try:
        submitted = _submit(parts, "6")
        if database_state == "failed":
            parts.attempts.record_waiting_fatal_failure(
                WaitingFatalFailure(
                    job_id=submitted.job.job_id,
                    now_us=NOW_US + 10,
                )
            )
            expected = JobState.FAILED
        else:
            claimed = parts.attempts.claim(
                ClaimJob(
                    job_id=submitted.job.job_id,
                    lease_owner="concurrent-worker",
                    now_us=NOW_US + 10,
                    lease_duration_us=10_000,
                )
            )
            assert claimed is not None
            expected = JobState.FAILED
        with parts.uow_factory() as work:
            before_events = work.job_events.list_for_job(submitted.job.job_id)
        manager = LocalWorkerSupervisor(
            tmp_path / "var",
            parts.uow_factory,
            parts.queue,
            attempt_service=parts.attempts,
            clock_us=lambda: NOW_US + 20,
        )
        manager._process = _ExitedWorker()
        manager._job_id = submitted.job.job_id
        manager._lease_owner = "concurrent-worker" if database_state == "running" else None

        manager._reap_finished_worker()

        with parts.uow_factory() as work:
            job = work.jobs.get(submitted.job.job_id)
            after_events = work.job_events.list_for_job(submitted.job.job_id)
        assert job is not None and job.state is expected
        if database_state == "failed":
            assert after_events == before_events
        else:
            assert after_events[:len(before_events)] == before_events
            failures = [event for event in after_events[len(before_events):] if event.event_type == "JOB_FAILED"]
            assert len(failures) == 1
            assert failures[0].metadata["reason_code"] == "WORKER_FATAL"
    finally:
        parts.engine.dispose()


def test_local_supervisor_recovers_expired_job_only_after_exit_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parts = _runtime(tmp_path / "var")
    try:
        submitted = _submit(parts, "7")
        claimed = parts.attempts.claim(
            ClaimJob(
                job_id=submitted.job.job_id,
                lease_owner="expired-worker",
                now_us=NOW_US,
                lease_duration_us=10,
            )
        )
        assert claimed is not None
        manager = LocalWorkerSupervisor(
            tmp_path / "var",
            parts.uow_factory,
            parts.queue,
            attempt_service=parts.attempts,
            clock_us=lambda: NOW_US + 20,
        )

        lifetime = WorkerLifetimeLock.acquire(
            tmp_path / "var",
            submitted.job.job_id,
            "expired-worker",
        )
        manager._recover_expired_workers()
        still_running = _job(parts, submitted.job.job_id)
        assert still_running is not None and still_running.state is JobState.RUNNING
        lifetime.release()
        manager._next_recovery_scan_us = 0
        manager._recover_expired_workers()
        no_tree_proof = _job(parts, submitted.job.job_id)
        assert no_tree_proof is not None and no_tree_proof.state is JobState.RUNNING

        monkeypatch.setattr(
            WorkerLifetimeLock,
            "execution_has_exited",
            staticmethod(lambda *_args: True),
        )
        manager._next_recovery_scan_us = 0
        manager._recover_expired_workers()

        recovered = _job(parts, submitted.job.job_id)
        assert recovered is not None and recovered.state is JobState.RETRY_WAIT
        assert manager.recovered_jobs == 1
    finally:
        parts.engine.dispose()
