from __future__ import annotations

import shutil
import os
import time
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from threading import Thread

import pytest
from sqlalchemy.engine import Engine

import product.backend.infra.runtime.worker_supervisor as worker_supervisor_module
from product.backend.core.lifecycle import JobState, RunLifecycle, RunVerdict
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage import (
    StorageUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
    default_database_path,
    upgrade_database,
)
from product.backend.infra.runtime.jobs.attempts import JobAttempts
from product.backend.infra.runtime.jobs.models import ClaimJob, RequestCancellation, WaitingFatalFailure
from product.backend.infra.artifacts.run_publication import RunPublisher
from product.backend.infra.runtime.jobs.queue import JobQueue
from product.backend.infra.runtime.job_requests import ExecutionRequestStore
from product.backend.workflows.runs.submission import RunSubmission, SubmitExecution, SubmitExecution
from product.backend.infra.runtime.runner_supervisor import RunnerSupervisor
from product.backend.infra.runtime.worker_supervisor import LocalWorkerSupervisor
from product.backend.infra.runtime.worker_lifetime import WorkerLifetimeLock
from product.backend.infra.runtime.job_requests import PersistedExecutionRequest
from product.protocols import (
    CleanupResult,
    CleanupStatus,
    RunnerError,
    RunnerInput,
    RunnerResultType,
    RunnerResult,
    canonical_runner_json_bytes,
)
from tests.fixtures.runner import runner_input as make_runner_input

pytestmark = [pytest.mark.database, pytest.mark.process, pytest.mark.slow]

NOW_US = 1_790_000_000_000_000


@dataclass(frozen=True)
class RuntimeParts:
    engine: Engine
    uow_factory: object
    request_store: ExecutionRequestStore
    submission: RunSubmission
    queue: JobQueue
    attempts: JobAttempts


def _runtime(var_dir: Path) -> RuntimeParts:
    database_path = default_database_path(var_dir)
    upgrade_database(database_path)
    engine = create_sqlite_engine(database_path)
    factory = create_session_factory(engine)
    uow_factory = partial(StorageUnitOfWork, factory)
    request_store = ExecutionRequestStore(var_dir)
    return RuntimeParts(
        engine=engine,
        uow_factory=uow_factory,
        request_store=request_store,
        submission=RunSubmission(uow_factory, request_store),
        queue=JobQueue(uow_factory),
        attempts=JobAttempts(uow_factory, jitter_source=lambda _: 0),
    )


def _submit(parts: RuntimeParts, request, suffix: str = "3"):
    return parts.submission.submit(
        SubmitExecution(
            request=request,
            idempotency_key=f"supervisor-{suffix}",
            max_attempts=3,
            available_at_us=NOW_US,
            now_us=NOW_US,
            run_id=f"run_{suffix * 32}",
            job_id=f"job_{suffix * 32}",
        )
    )


def _job(parts: RuntimeParts, job_id: str):
    with parts.uow_factory() as work:
        return work.jobs.get(job_id)


class _ExitedWorker:
    def __init__(self, returncode: int = 1) -> None:
        self.returncode = returncode

    def poll(self) -> int:
        return self.returncode


def test_local_supervisor_nonzero_preclaim_exit_launches_once_and_fails_run(
    tmp_path: Path,
    monkeypatch,
    stage23_request_factory,
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
        submitted = _submit(parts, stage23_request_factory(), "4")
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
        assert [event.event_type for event in events] == [
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
    stage23_request_factory,
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
        submitted = _submit(parts, stage23_request_factory(), "5")
        if failure_point == "request_load":
            monkeypatch.setattr(
                worker_supervisor_module,
                "ExecutionRequestStore",
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
    stage23_request_factory,
    database_state: str,
) -> None:
    parts = _runtime(tmp_path / "var")
    try:
        submitted = _submit(parts, stage23_request_factory(), "6")
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
            assert len(after_events) == len(before_events) + 1
            assert after_events[-1].event_type == "JOB_FAILED"
            assert after_events[-1].metadata["reason_code"] == "WORKER_FATAL"
    finally:
        parts.engine.dispose()


def test_local_supervisor_recovers_expired_job_only_after_worker_lock_is_free(
    tmp_path: Path,
    stage23_request_factory,
) -> None:
    parts = _runtime(tmp_path / "var")
    try:
        submitted = _submit(parts, stage23_request_factory(), "7")
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

        recovered = _job(parts, submitted.job.job_id)
        assert recovered is not None and recovered.state is JobState.RETRY_WAIT
        assert manager.recovered_jobs == 1
    finally:
        parts.engine.dispose()


def test_worker_current_bridge_builds_explicit_input_and_submission_command(tmp_path: Path) -> None:
    runner_input = make_runner_input()
    request = PersistedExecutionRequest(
        schema_version="3",
        budget=runner_input.budget,
        project_snapshot=runner_input.project_snapshot,
    )
    command = SubmitExecution(
        schema_version="2",
        request=request,
        idempotency_key="worker-v2-bridge",
        available_at_us=NOW_US,
        now_us=NOW_US,
        run_id=runner_input.run_id,
        job_id=runner_input.job_id,
    )
    supervisor = RunnerSupervisor(
        var_dir=tmp_path / "var",
        lease_owner="worker-v2-bridge",
        uow_factory=lambda **kwargs: None,
        attempt_service=None,
        request_store=ExecutionRequestStore(tmp_path / "var"),
        publication_service=None,
    )
    job = type("Job", (), {
        "run_id": runner_input.run_id,
        "job_id": runner_input.job_id,
        "attempt": 1,
        "lease_owner": "worker-v2-bridge",
        "fencing_token": 1,
        "updated_at_us": NOW_US,
    })()
    built = supervisor._runner_input(job, command.request)
    assert isinstance(built, RunnerInput)
    assert built.schema_version == "3"
    assert canonical_runner_json_bytes(built)


def test_worker_current_non_success_uses_existing_fatal_lifecycle_bridge(tmp_path: Path) -> None:
    class FatalCapture:
        def __init__(self) -> None:
            self.calls = []

        def record_fatal_failure(self, mutation) -> None:
            self.calls.append(mutation)

    attempts = FatalCapture()
    supervisor = RunnerSupervisor(
        var_dir=tmp_path / "var",
        lease_owner="worker-v2-fatal",
        uow_factory=lambda **kwargs: None,
        attempt_service=attempts,
        request_store=ExecutionRequestStore(tmp_path / "var"),
        publication_service=None,
        utc_now_us=lambda: NOW_US,
    )
    job = type("Job", (), {"job_id": "job_" + "b" * 32, "fencing_token": 3})()
    result = RunnerResult(
        run_id="run_" + "b" * 32,
        job_id=job.job_id,
        attempt=1,
        lease_owner="worker-v2-fatal",
        fencing_token=3,
        finished_at_us=NOW_US,
        result_type=RunnerResultType.FATAL_ERROR,
        run_lifecycle=RunLifecycle.FAILED,
        job_state=JobState.FAILED,
        verdict=None,
        cleanup=CleanupResult(status=CleanupStatus.SUCCEEDED),
        error=RunnerError(code="RUNNER_FATAL", retryable=False),
        plan_fingerprint="0" * 64,
        coverage_record_count=0,
        coverage_gap_count=0,
    )

    supervisor._apply_non_success_result(job, result)

    assert len(attempts.calls) == 1
    assert attempts.calls[0].job_id == job.job_id
