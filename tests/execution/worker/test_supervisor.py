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

from jiejian.domain.lifecycle import JobState, RunVerdict
from jiejian.errors import ErrorCode, JiejianError
from jiejian.storage import (
    StorageUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
    default_database_path,
    upgrade_database,
)
from jiejian.execution.attempts import JobAttemptService
from jiejian.execution.models import RequestCancellationV1
from jiejian.execution.publication import RunPublicationService
from jiejian.execution.queue import JobQueueService
from jiejian.execution.request_store import ExecutionRequestStore
from jiejian.execution.submission import ExecutionSubmissionService, SubmitExecutionV1
from jiejian.execution.supervisor import WorkerSupervisor

pytestmark = [pytest.mark.database, pytest.mark.process, pytest.mark.slow]

NOW_US = 1_790_000_000_000_000


@dataclass(frozen=True)
class RuntimeParts:
    engine: Engine
    uow_factory: object
    request_store: ExecutionRequestStore
    submission: ExecutionSubmissionService
    queue: JobQueueService
    attempts: JobAttemptService


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
        submission=ExecutionSubmissionService(uow_factory, request_store),
        queue=JobQueueService(uow_factory),
        attempts=JobAttemptService(uow_factory, jitter_source=lambda _: 0),
    )


def _submit(parts: RuntimeParts, request, suffix: str = "3"):
    return parts.submission.submit(
        SubmitExecutionV1(
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


def test_supervisor_uses_persisted_snapshot_after_yaml_removal_and_publishes(
    sample_server_factory,
    stage1_project_factory,
    stage23_request_factory,
    tmp_path: Path,
) -> None:
    server = sample_server_factory("safe")
    project = stage1_project_factory(server.port)
    request = stage23_request_factory(project)
    parts = _runtime(tmp_path / "var")
    clock = iter((NOW_US, NOW_US + 3_000_000, NOW_US + 4_000_000))
    try:
        submitted = _submit(parts, request)
        shutil.rmtree(project.parent)
        staged = WorkerSupervisor(
            var_dir=tmp_path / "var",
            lease_owner="worker-supervisor-success",
            uow_factory=parts.uow_factory,
            attempt_service=parts.attempts,
            request_store=parts.request_store,
            publication_service=RunPublicationService(
                tmp_path / "var",
                parts.uow_factory,
                utc_now_us=lambda: NOW_US + 4_000_000,
            ),
            environ=os.environ | server.environ,
            utc_now_us=lambda: next(clock),
        ).run_job(submitted.job.job_id)

        assert staged is not None
        assert staged.result.verdict is RunVerdict.PASS
        assert staged.paths.receipt_path.is_file()
        assert staged.paths.result_path.is_file()
        assert (
            tmp_path
            / "var"
            / "projects"
            / request.project_snapshot.project_id
            / "runs"
            / submitted.run.run_id
        ).is_dir()
        current = _job(parts, submitted.job.job_id)
        assert current.state is JobState.SUCCEEDED
        assert server.server.runner_process_ids
    finally:
        parts.engine.dispose()


def test_running_cancellation_notifies_runner_and_completes_after_cleanup(
    sample_server_factory,
    stage1_project_factory,
    stage23_request_factory,
    tmp_path: Path,
) -> None:
    server = sample_server_factory("safe", request_delay_seconds=0.15)
    request = stage23_request_factory(stage1_project_factory(server.port))
    parts = _runtime(tmp_path / "var")
    submitted = _submit(parts, request, "4")
    outcome: list[object] = []
    clock = iter((NOW_US, NOW_US + 3_000_000, NOW_US + 4_000_000))

    def supervise() -> None:
        try:
            outcome.append(
                WorkerSupervisor(
                    var_dir=tmp_path / "var",
                    lease_owner="worker-supervisor-cancel",
                    uow_factory=parts.uow_factory,
                    attempt_service=parts.attempts,
                    request_store=parts.request_store,
                    publication_service=RunPublicationService(
                        tmp_path / "var",
                        parts.uow_factory,
                        utc_now_us=lambda: NOW_US + 4_000_000,
                    ),
                    environ=os.environ | server.environ,
                    utc_now_us=lambda: next(clock),
                ).run_job(submitted.job.job_id)
            )
        except Exception as exc:
            outcome.append(exc)

    thread = Thread(target=supervise)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while _job(parts, submitted.job.job_id).state is not JobState.RUNNING:
            if time.monotonic() >= deadline:
                raise AssertionError("job was not claimed")
            time.sleep(0.01)
        parts.queue.request_cancellation(
            RequestCancellationV1(
                job_id=submitted.job.job_id,
                now_us=NOW_US + 2_000_000,
            )
        )
        thread.join(timeout=20)
        assert not thread.is_alive()
        assert outcome and not isinstance(outcome[0], Exception), outcome
        assert _job(parts, submitted.job.job_id).state is JobState.CANCELLED
    finally:
        parts.engine.dispose()


def test_expired_fence_rejects_completed_result_without_trusted_receipt(
    sample_server_factory,
    stage1_project_factory,
    stage23_request_factory,
    tmp_path: Path,
) -> None:
    server = sample_server_factory("safe")
    request = stage23_request_factory(stage1_project_factory(server.port))
    parts = _runtime(tmp_path / "var")
    submitted = _submit(parts, request, "5")
    moments = iter((NOW_US, NOW_US + 31_000_000))
    supervisor = WorkerSupervisor(
        var_dir=tmp_path / "var",
        lease_owner="worker-expired-result",
        uow_factory=parts.uow_factory,
        attempt_service=parts.attempts,
        request_store=parts.request_store,
        publication_service=RunPublicationService(
            tmp_path / "var",
            parts.uow_factory,
            utc_now_us=lambda: NOW_US + 4_000_000,
        ),
        environ=os.environ | server.environ,
        utc_now_us=lambda: next(moments),
    )
    try:
        with pytest.raises(JiejianError) as captured:
            supervisor.run_job(submitted.job.job_id)
        assert captured.value.code == ErrorCode.JOB_LEASE_EXPIRED.value
        current = _job(parts, submitted.job.job_id)
        assert current.state is JobState.RUNNING
        attempt_root = (
            tmp_path
            / "var"
            / "jobs"
            / submitted.job.job_id
            / "attempts"
            / "1-1"
        )
        assert (attempt_root / "staging" / "result.json").is_file()
        assert not (attempt_root / "trusted-result.json").exists()
    finally:
        parts.engine.dispose()
