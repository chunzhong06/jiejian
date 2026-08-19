from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Iterator

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from product.backend.core.lifecycle import ProjectStatus
from product.backend.infra.storage import (
    ProjectRecord,
    StorageUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
    upgrade_database,
)
from product.backend.infra.runtime.jobs.attempts import JobAttempts
from product.backend.infra.runtime.jobs.models import SubmitJob
from product.backend.infra.runtime.jobs.queue import JobQueue
from product.backend.infra.runtime.jobs.recovery import JobRecovery

PROJECT_ID = "stage22-project"
NOW_US = 1_790_000_000_000_000


@dataclass(frozen=True)
class WorkerServices:
    database_path: Path
    engine: Engine
    session_factory: sessionmaker[Session]
    queue: JobQueue
    attempts: JobAttempts
    recovery: JobRecovery

    def submit_request(self, **changes: Any) -> SubmitJob:
        values = {
            "project_id": PROJECT_ID,
            "operation_type": "ACTIVE_RUN",
            "idempotency_key": "request-1",
            "request_hash": "a" * 64,
            "contract_id": "ownership-contract",
            "contract_version": 3,
            "engine_version": "0.1.0",
            "max_attempts": 3,
            "available_at_us": NOW_US,
            "now_us": NOW_US,
        }
        return SubmitJob(**(values | changes))


@pytest.fixture
def worker_services(tmp_path: Path) -> Iterator[WorkerServices]:
    database_path = tmp_path / "stage22.db"
    upgrade_database(database_path)
    engine = create_sqlite_engine(database_path)
    factory = create_session_factory(engine)
    with StorageUnitOfWork(factory) as work:
        work.projects.add(
            ProjectRecord(
                project_id=PROJECT_ID,
                name="阶段 2.2 项目",
                status=ProjectStatus.READY,
                created_at_us=NOW_US - 100,
                updated_at_us=NOW_US - 100,
            )
        )
        work.commit()
    uow_factory = partial(StorageUnitOfWork, factory)
    yield WorkerServices(
        database_path=database_path,
        engine=engine,
        session_factory=factory,
        queue=JobQueue(uow_factory),
        attempts=JobAttempts(
            uow_factory,
            jitter_source=lambda _: 0,
        ),
        recovery=JobRecovery(
            uow_factory,
            jitter_source=lambda _: 0,
        ),
    )
    engine.dispose()
