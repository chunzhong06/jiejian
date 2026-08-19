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
from product.backend.infra.runtime.jobs.models import RequestCancellation
from product.backend.infra.artifacts.run_publication import RunPublisher
from product.backend.infra.runtime.jobs.queue import JobQueue
from product.backend.infra.runtime.job_requests import ExecutionRequestStore
from product.backend.workflows.runs.submission import RunSubmission, SubmitExecution, SubmitExecution
from product.backend.infra.runtime.runner_supervisor import RunnerSupervisor
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


def test_worker_current_bridge_builds_explicit_input_and_submission_command(tmp_path: Path) -> None:
    runner_input = make_runner_input()
    request = PersistedExecutionRequest(
        schema_version="2",
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
