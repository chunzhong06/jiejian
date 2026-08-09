"""独立单任务 Worker 进程入口；本模块不具备目标请求能力。"""

from __future__ import annotations

import argparse
import os
import time
from functools import partial
from pathlib import Path

from ..storage import (
    StorageUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
    default_database_path,
    upgrade_database,
)
from .attempts import JobAttemptService
from .publication import RunPublicationService
from .reconciliation import RunReconciliationService
from .request_store import ExecutionRequestStore, required_secret_names
from .supervisor import WorkerSupervisor
from ..domain.lifecycle import JobState
from ..errors import JiejianError
from ..protocols import RunnerResultType


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m jiejian.worker.runtime")
    parser.add_argument("--var-dir", type=Path, required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--lease-owner", required=True)
    arguments = parser.parse_args()
    var_dir = arguments.var_dir.resolve()
    var_dir.mkdir(parents=True, exist_ok=True)
    database_path = default_database_path(var_dir)
    upgrade_database(database_path)
    engine = create_sqlite_engine(database_path)
    try:
        factory = create_session_factory(engine)
        uow_factory = partial(StorageUnitOfWork, factory)
        request_store = ExecutionRequestStore(var_dir)
        with uow_factory() as work:
            initial_job = work.jobs.get(arguments.job_id)
        if initial_job is None:
            return 1
        request = request_store.load(arguments.job_id, expected_hash=initial_job.request_hash)
        known_secrets = tuple(
            os.environ[name]
            for name in required_secret_names(request)
            if os.environ.get(name)
        )
        publication = RunPublicationService(var_dir, uow_factory)
        reconciliation = RunReconciliationService(
            var_dir,
            uow_factory,
            publication,
        )
        reconciliation.reconcile(known_secrets=known_secrets)
        supervisor = WorkerSupervisor(
            var_dir=var_dir,
            lease_owner=arguments.lease_owner,
            uow_factory=uow_factory,
            attempt_service=JobAttemptService(uow_factory),
            request_store=request_store,
            publication_service=publication,
            environ=os.environ,
        )
        while True:
            try:
                staged = supervisor.run_job(arguments.job_id)
            except JiejianError:
                staged = None
                reconciliation.reconcile(known_secrets=known_secrets)
            with uow_factory() as work:
                job = work.jobs.get(arguments.job_id)
            if job is None:
                return 1
            if job.state is JobState.SUCCEEDED:
                return 0
            if job.state is JobState.RETRY_WAIT and job.attempt < job.max_attempts:
                delay_us = max(job.available_at_us - time.time_ns() // 1_000, 0)
                time.sleep(delay_us / 1_000_000)
                continue
            if staged is not None and staged.result.result_type in {
                RunnerResultType.SUCCESS,
                RunnerResultType.SAFETY_STOPPED,
                RunnerResultType.CANCELLED,
            }:
                return 0
            return 1
    except Exception:
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
