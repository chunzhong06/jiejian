# 验证 Execution storage 中 Run、Job、生命周期和事件记录边界。

from __future__ import annotations
import json
from collections.abc import Iterator
from io import StringIO
from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from sqlalchemy import CheckConstraint, UniqueConstraint, inspect, insert, text
from sqlalchemy.engine import Connection, Engine
pytestmark = pytest.mark.database
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from product.backend.core.lifecycle import JobState, ProjectStatus, RunLifecycle, RunVerdict
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import STAGED_ARTIFACT_MAX_BYTES
from product.backend.infra.runtime.logging import configure_logging
from product.backend.infra.storage import (
    SQLITE_BUSY_TIMEOUT_MS,
    EvidenceIndexRecord,
    JobEventRecord,
    JobRecord,
    ProjectRecord,
    RunRecord,
    StorageUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
    default_database_path,
    upgrade_database,
)
from product.backend.infra.storage.db import _migration_resource_root
from product.backend.infra.storage import Base, EvidenceIndexRow, JobRow, ProjectRow, RunRow
PROJECT_ID = "storage-project"
RUN_ID = "run_" + "1" * 32
JOB_ID = "job_" + "2" * 32
SHA256 = "a" * 64
EVIDENCE_ID = "ev_" + SHA256[:20]
NOW_US = 1_780_000_000_000_000

@pytest.fixture
def migrated_storage(
    tmp_path: Path,
) -> Iterator[tuple[Path, Engine, sessionmaker[Session]]]:
    database_path = tmp_path / "storage.db"
    upgrade_database(database_path)
    engine = create_sqlite_engine(database_path)
    yield database_path, engine, create_session_factory(engine)
    engine.dispose()

def _project(**changes: Any) -> ProjectRecord:
    values = {
        "project_id": PROJECT_ID,
        "name": "存储项目",
        "status": ProjectStatus.READY,
        "created_at_us": NOW_US,
        "updated_at_us": NOW_US + 1,
    }
    return ProjectRecord(**(values | changes))

def _run(**changes: Any) -> RunRecord:
    values = {
        "run_id": RUN_ID,
        "project_id": PROJECT_ID,
        "contract_id": "ownership-contract",
        "contract_version": 3,
        "engine_version": "0.1.0",
        "lifecycle": RunLifecycle.COMPLETED,
        "verdict": RunVerdict.PASS,
        "created_at_us": NOW_US + 2,
        "updated_at_us": NOW_US + 3,
        "finished_at_us": NOW_US + 4,
    }
    return RunRecord(**(values | changes))

def _job(**changes: Any) -> JobRecord:
    values = {
        "job_id": JOB_ID,
        "project_id": PROJECT_ID,
        "run_id": RUN_ID,
        "operation_type": "ACTIVE_RUN",
        "state": JobState.SUCCEEDED,
        "idempotency_key": "storage-request",
        "request_hash": "b" * 64,
        "attempt": 1,
        "max_attempts": 3,
        "available_at_us": NOW_US + 2,
        "lease_owner": "worker-1",
        "fencing_token": 7,
        "lease_expires_at_us": NOW_US + 10_000,
        "cancel_requested_at_us": None,
        "created_at_us": NOW_US + 2,
        "updated_at_us": NOW_US + 4,
    }
    return JobRecord(**(values | changes))

def _event(sequence: int, **changes: Any) -> JobEventRecord:
    values = {
        "job_id": JOB_ID,
        "sequence": sequence,
        "event_type": "STATE_CHANGED",
        "source_state": JobState.RUNNING,
        "target_state": JobState.SUCCEEDED,
        "occurred_at_us": NOW_US + sequence,
        "metadata": {"reason_code": "RUN_COMPLETED", "attempt": 1},
    }
    return JobEventRecord(**(values | changes))

def _evidence(**changes: Any) -> EvidenceIndexRecord:
    values = {
        "evidence_id": EVIDENCE_ID,
        "run_id": RUN_ID,
        "case_id": "foreign-read-case",
        "artifact_path": "evidence/foreign-read.json",
        "sha256": SHA256,
        "byte_count": 512,
        "created_at_us": NOW_US + 4,
    }
    return EvidenceIndexRecord(**(values | changes))

def _seed_project_and_run(connection: Connection) -> None:
    connection.execute(
        insert(ProjectRow).values(
            project_id=PROJECT_ID,
            name="seed",
            status="READY",
            created_at_us=NOW_US,
            updated_at_us=NOW_US,
        )
    )
    connection.execute(
        insert(RunRow).values(
            run_id=RUN_ID,
            project_id=PROJECT_ID,
            contract_id="contract",
            contract_version=1,
            engine_version="0.1.0",
            lifecycle="COMPLETED",
            verdict="PASS",
            created_at_us=NOW_US,
            updated_at_us=NOW_US,
            finished_at_us=NOW_US,
        )
    )

def test_committed_records_survive_engine_restart_with_exact_values(
    migrated_storage: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    path, engine, factory = migrated_storage
    expected_project = _project()
    expected_run = _run()
    expected_job = _job()
    expected_event = _event(1)
    expected_evidence = _evidence()
    with StorageUnitOfWork(factory) as work:
        work.projects.add(expected_project)
        work.runs.add(expected_run)
        work.jobs.add(expected_job)
        work.job_events.append(expected_event)
        work.evidence.add(expected_evidence)
        work.commit()

    engine.dispose()
    restarted = create_sqlite_engine(path)
    try:
        with StorageUnitOfWork(create_session_factory(restarted)) as work:
            assert work.projects.get(PROJECT_ID) == expected_project
            assert work.runs.get(RUN_ID) == expected_run
            assert work.jobs.get(JOB_ID) == expected_job
            assert work.jobs.get_by_idempotency(
                PROJECT_ID,
                "ACTIVE_RUN",
                "storage-request",
            ) == expected_job
            assert work.job_events.list_for_job(JOB_ID) == (expected_event,)
            assert work.evidence.list_for_run(RUN_ID) == (expected_evidence,)
    finally:
        restarted.dispose()

def test_uncommitted_uow_is_invisible_to_another_session_then_commits(
    migrated_storage: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _, _, factory = migrated_storage
    writer = StorageUnitOfWork(factory).begin()
    try:
        writer.projects.add(_project())
        with StorageUnitOfWork(factory) as reader:
            assert reader.projects.get(PROJECT_ID) is None
        writer.commit()
    finally:
        writer.close()
    with StorageUnitOfWork(factory) as reader:
        assert reader.projects.get(PROJECT_ID) == _project()

@pytest.mark.parametrize("raise_inside", [False, True])
def test_uncommitted_or_exceptional_uow_rolls_back_without_partial_write(
    migrated_storage: tuple[Path, Engine, sessionmaker[Session]],
    raise_inside: bool,
) -> None:
    _, _, factory = migrated_storage
    if raise_inside:
        with pytest.raises(RuntimeError, match="rollback probe"):
            with StorageUnitOfWork(factory) as work:
                work.projects.add(_project())
                raise RuntimeError("rollback probe")
    else:
        with StorageUnitOfWork(factory) as work:
            work.projects.add(_project())
    with StorageUnitOfWork(factory) as reader:
        assert reader.projects.get(PROJECT_ID) is None

def test_idempotency_scope_is_unique_and_constraint_error_is_stable(
    migrated_storage: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _, _, factory = migrated_storage
    with StorageUnitOfWork(factory) as work:
        work.projects.add(_project())
        work.runs.add(_run())
        work.jobs.add(_job())
        work.commit()

    second_run_id = "run_" + "3" * 32
    second_job_id = "job_" + "4" * 32
    with pytest.raises(JiejianError) as captured:
        with StorageUnitOfWork(factory) as work:
            work.runs.add(
                _run(
                    run_id=second_run_id,
                    created_at_us=NOW_US + 5,
                    updated_at_us=NOW_US + 5,
                    finished_at_us=NOW_US + 5,
                )
            )
            work.jobs.add(
                _job(
                    job_id=second_job_id,
                    run_id=second_run_id,
                    request_hash="c" * 64,
                )
            )
    assert captured.value.code == ErrorCode.STORAGE_CONSTRAINT.value
    assert captured.value.to_dict()["message"] == "数据库约束拒绝写入"
    serialized_error = str(captured.value) + repr(captured.value.to_dict())
    assert "storage-request" not in serialized_error
    assert "INSERT" not in serialized_error
    assert ".db" not in serialized_error
    with StorageUnitOfWork(factory) as reader:
        assert reader.runs.get(second_run_id) is None

@pytest.mark.parametrize("changes", [{"request_hash": "A" * 64}, {"attempt": 4, "max_attempts": 3}, {"fencing_token": -1}, {"fencing_token": 0}, {"available_at_us": -1}, {"lease_expires_at_us": None}, {"state": "RUNNING", "lease_owner": None, "lease_expires_at_us": None}])
def test_job_database_checks_reject_invalid_protocol_fields(
    migrated_storage: tuple[Path, Engine, sessionmaker[Session]],
    changes: dict[str, Any],
) -> None:
    _, engine, _ = migrated_storage
    with engine.connect() as connection:
        transaction = connection.begin()
        _seed_project_and_run(connection)
        values = {
            "job_id": JOB_ID,
            "project_id": PROJECT_ID,
            "run_id": RUN_ID,
            "operation_type": "ACTIVE_RUN",
            "state": "SUCCEEDED",
            "idempotency_key": "request",
            "request_hash": "b" * 64,
            "attempt": 1,
            "max_attempts": 3,
            "available_at_us": NOW_US,
            "lease_owner": "worker-1",
            "fencing_token": 1,
            "lease_expires_at_us": NOW_US + 1,
            "cancel_requested_at_us": None,
            "created_at_us": NOW_US,
            "updated_at_us": NOW_US,
        }
        with pytest.raises(IntegrityError):
            connection.execute(insert(JobRow).values(**(values | changes)))
        transaction.rollback()

@pytest.mark.parametrize(("lifecycle", "verdict"), [(RunLifecycle.COMPLETED, None), (RunLifecycle.FAILED, RunVerdict.INCONCLUSIVE), (RunLifecycle.CANCELLED, RunVerdict.PASS), (RunLifecycle.RUNNING, RunVerdict.BLOCK)])
def test_run_lifecycle_and_verdict_invalid_combinations_are_rejected(
    lifecycle: RunLifecycle,
    verdict: RunVerdict | None,
) -> None:
    with pytest.raises(ValidationError):
        _run(lifecycle=lifecycle, verdict=verdict)

def test_run_database_check_rejects_infrastructure_error_as_inconclusive(
    migrated_storage: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _, engine, _ = migrated_storage
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(
            insert(ProjectRow).values(
                project_id=PROJECT_ID,
                name="seed",
                status="READY",
                created_at_us=NOW_US,
                updated_at_us=NOW_US,
            )
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                insert(RunRow).values(
                    run_id=RUN_ID,
                    project_id=PROJECT_ID,
                    contract_id="contract",
                    contract_version=1,
                    engine_version="0.1.0",
                    lifecycle="FAILED",
                    verdict="INCONCLUSIVE",
                    created_at_us=NOW_US,
                    updated_at_us=NOW_US,
                    finished_at_us=NOW_US,
                )
            )
        transaction.rollback()

def test_job_events_are_contiguous_append_only_and_read_in_order(
    migrated_storage: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _, _, factory = migrated_storage
    with StorageUnitOfWork(factory) as work:
        work.projects.add(_project())
        work.runs.add(_run())
        work.jobs.add(_job())
        work.job_events.append(
            _event(
                1,
                source_state=JobState.PENDING,
                target_state=JobState.RUNNING,
                occurred_at_us=NOW_US + 1,
            )
        )
        work.job_events.append(_event(2, occurred_at_us=NOW_US + 2))
        with pytest.raises(JiejianError) as captured:
            work.job_events.append(_event(4))
        assert captured.value.code == ErrorCode.STORAGE_CONSTRAINT.value
        work.commit()
    with StorageUnitOfWork(factory) as reader:
        assert [
            item.sequence for item in reader.job_events.list_for_job(JOB_ID)
        ] == [1, 2]
