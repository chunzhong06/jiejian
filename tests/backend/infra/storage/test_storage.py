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

PROJECT_ID = "stage21-project"
RUN_ID = "run_" + "1" * 32
JOB_ID = "job_" + "2" * 32
SHA256 = "a" * 64
EVIDENCE_ID = "ev_" + SHA256[:20]
NOW_US = 1_780_000_000_000_000


@pytest.fixture
def migrated_storage(
    tmp_path: Path,
) -> Iterator[tuple[Path, Engine, sessionmaker[Session]]]:
    database_path = tmp_path / "stage21.db"
    upgrade_database(database_path)
    engine = create_sqlite_engine(database_path)
    yield database_path, engine, create_session_factory(engine)
    engine.dispose()


def _project(**changes: Any) -> ProjectRecord:
    values = {
        "project_id": PROJECT_ID,
        "name": "阶段 2.1 项目",
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
        "idempotency_key": "stage21-request",
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


def test_source_migration_resource_root_uses_backend_single_source() -> None:
    with _migration_resource_root() as root:
        assert root == Path(__file__).resolve().parents[4] / "product" / "backend"
        assert (root / "alembic.ini").is_file()
        assert (root / "migrations").is_dir()


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


def test_blank_database_upgrade_is_repeatable_and_at_head(tmp_path: Path) -> None:
    path = tmp_path / "blank.db"
    upgrade_database(path)
    upgrade_database(path)
    engine = create_sqlite_engine(path)
    try:
        inspector = inspect(engine)
        assert set(inspector.get_table_names()) == {
            "alembic_version",
            "contract_candidates",
            "contract_versions",
            "evidence_index",
            "findings",
            "finding_occurrences",
            "regression_baselines",
            "gate_results",
            "flow_draft_revisions",
            "job_events",
            "jobs",
            "llm_profiles",
            "execution_profiles",
            "projects",
            "recordings",
            "requirements",
            "runs",
        }
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == "0001_initial"
    finally:
        engine.dispose()


def test_migration_does_not_disable_existing_application_logger(tmp_path: Path) -> None:
    stream = StringIO()
    logger = configure_logging("INFO", stream=stream)
    logger.info("before migration")

    upgrade_database(tmp_path / "logging.db")
    logger.info("after migration")

    assert [
        json.loads(line)["message"] for line in stream.getvalue().splitlines()
    ] == ["before migration", "after migration"]


def test_migrated_schema_matches_sqlalchemy_metadata(
    migrated_storage: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _, engine, _ = migrated_storage
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) - {"alembic_version"} == set(
        Base.metadata.tables
    )

    for table_name, expected_table in Base.metadata.tables.items():
        actual_columns = {
            item["name"]: item for item in inspector.get_columns(table_name)
        }
        if table_name == "projects":
            actual_columns = {
                name: item
                for name, item in actual_columns.items()
                if name not in {"source_path", "source_hash", "active_contract_path", "active_contract_hash"}
            }
        assert set(actual_columns) == set(expected_table.columns.keys())
        for column in expected_table.columns:
            actual = actual_columns[column.name]
            assert actual["nullable"] is column.nullable
            assert bool(actual["primary_key"]) is column.primary_key
            expected_type = str(column.type.compile(dialect=engine.dialect)).split(
                " COLLATE",
                1,
            )[0]
            assert str(actual["type"]) == expected_type

        actual_primary_key = inspector.get_pk_constraint(table_name)
        assert actual_primary_key["name"] == expected_table.primary_key.name
        assert tuple(actual_primary_key["constrained_columns"]) == tuple(
            column.name for column in expected_table.primary_key.columns
        )

        expected_checks = {
            constraint.name
            for constraint in expected_table.constraints
            if isinstance(constraint, CheckConstraint)
        }
        assert {
            item["name"] for item in inspector.get_check_constraints(table_name)
        } == expected_checks

        expected_uniques = {
            (constraint.name, tuple(column.name for column in constraint.columns))
            for constraint in expected_table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        assert {
            (item["name"], tuple(item["column_names"]))
            for item in inspector.get_unique_constraints(table_name)
        } == expected_uniques

        expected_foreign_keys = {
            (
                constraint.name,
                tuple(element.parent.name for element in constraint.elements),
                tuple(element.column.table.name for element in constraint.elements),
                tuple(element.column.name for element in constraint.elements),
                constraint.ondelete,
            )
            for constraint in expected_table.foreign_key_constraints
        }
        assert {
            (
                item["name"],
                tuple(item["constrained_columns"]),
                tuple(item["referred_table"] for _ in item["referred_columns"]),
                tuple(item["referred_columns"]),
                item["options"].get("ondelete"),
            )
            for item in inspector.get_foreign_keys(table_name)
        } == expected_foreign_keys

        expected_indexes = {
            (index.name, tuple(column.name for column in index.columns), index.unique)
            for index in expected_table.indexes
        }
        assert {
            (item["name"], tuple(item["column_names"]), item["unique"])
            for item in inspector.get_indexes(table_name)
        } == expected_indexes

    with engine.connect() as connection:
        evidence_sql = connection.execute(
            text(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'table' AND name = 'evidence_index'"
            )
        ).scalar_one()
    assert "COLLATE \"NOCASE\"" in evidence_sql


def test_project_governed_binding_database_trigger_rejects_partial_values(
    migrated_storage: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _, engine, factory = migrated_storage
    with StorageUnitOfWork(factory) as work:
        work.projects.add(_project())
        work.commit()
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE projects SET governed_contract_id = :contract_id WHERE project_id = :project_id"),
                {"contract_id": "ownership-contract", "project_id": PROJECT_ID},
            )
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE projects SET governed_contract_version = 0 WHERE project_id = :project_id"),
                {"project_id": PROJECT_ID},
            )

def test_every_new_connection_enables_required_sqlite_pragmas(
    migrated_storage: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _, engine, _ = migrated_storage
    for _ in range(2):
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one() == "wal"
            assert (
                connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one()
                == SQLITE_BUSY_TIMEOUT_MS
            )


def test_foreign_key_violation_really_fails(
    migrated_storage: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _, engine, _ = migrated_storage
    with engine.connect() as connection:
        transaction = connection.begin()
        with pytest.raises(IntegrityError):
            connection.execute(
                insert(RunRow).values(
                    run_id=RUN_ID,
                    project_id="missing-project",
                    contract_id="contract",
                    contract_version=1,
                    engine_version="0.1.0",
                    lifecycle="QUEUED",
                    verdict=None,
                    created_at_us=NOW_US,
                    updated_at_us=NOW_US,
                    finished_at_us=None,
                )
            )
        transaction.rollback()


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
                "stage21-request",
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
    assert "stage21-request" not in serialized_error
    assert "INSERT" not in serialized_error
    assert ".db" not in serialized_error
    with StorageUnitOfWork(factory) as reader:
        assert reader.runs.get(second_run_id) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"request_hash": "A" * 64},
        {"attempt": 4, "max_attempts": 3},
        {"fencing_token": -1},
        {"fencing_token": 0},
        {"available_at_us": -1},
        {"lease_expires_at_us": None},
        {
            "state": "RUNNING",
            "lease_owner": None,
            "lease_expires_at_us": None,
        },
    ],
)
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


@pytest.mark.parametrize(
    ("lifecycle", "verdict"),
    [
        (RunLifecycle.COMPLETED, None),
        (RunLifecycle.FAILED, RunVerdict.INCONCLUSIVE),
        (RunLifecycle.CANCELLED, RunVerdict.PASS),
        (RunLifecycle.EXECUTING, RunVerdict.BLOCK),
    ],
)
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


@pytest.mark.parametrize(
    "changes",
    [
        {"artifact_path": "../escape.json"},
        {"artifact_path": "NUL.txt"},
        {"artifact_path": "name."},
        {"artifact_path": "file.txt:stream"},
        {"byte_count": STAGED_ARTIFACT_MAX_BYTES + 1},
        {"evidence_id": "ev_" + "b" * 20},
    ],
)
def test_evidence_record_rejects_unsafe_path_size_or_content_address(
    changes: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        _evidence(**changes)


def test_evidence_record_accepts_exact_single_item_size_limit() -> None:
    assert _evidence(byte_count=STAGED_ARTIFACT_MAX_BYTES).byte_count == (
        STAGED_ARTIFACT_MAX_BYTES
    )


def test_evidence_path_uniqueness_is_windows_case_insensitive(
    migrated_storage: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _, _, factory = migrated_storage
    second_hash = "b" * 64
    with pytest.raises(JiejianError) as captured:
        with StorageUnitOfWork(factory) as work:
            work.projects.add(_project())
            work.runs.add(_run())
            work.evidence.add(
                _evidence(artifact_path="evidence/A.json")
            )
            work.evidence.add(
                _evidence(
                    evidence_id="ev_" + second_hash[:20],
                    case_id="second-case",
                    artifact_path="evidence/a.json",
                    sha256=second_hash,
                )
            )
    assert captured.value.code == ErrorCode.STORAGE_CONSTRAINT.value


def test_known_secret_and_evidence_body_never_enter_database(
    migrated_storage: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    path, engine, factory = migrated_storage
    sentinel = "stage21-real-secret-sentinel"
    with pytest.raises(JiejianError) as captured:
        with StorageUnitOfWork(factory, known_secrets=("", sentinel)) as work:
            work.projects.add(_project(name=f"prefix-{sentinel}-suffix"))
    assert captured.value.code == ErrorCode.STORAGE_SECRET.value
    serialized_error = str(captured.value) + repr(captured.value.to_dict())
    assert sentinel not in serialized_error

    with StorageUnitOfWork(factory) as work:
        work.projects.add(_project())
        work.runs.add(_run())
        work.commit()
    with pytest.raises(JiejianError) as evidence_error:
        with StorageUnitOfWork(factory, known_secrets=(sentinel,)) as work:
            work.evidence.add(
                _evidence(artifact_path=f"evidence/{sentinel}.json")
            )
    assert evidence_error.value.code == ErrorCode.STORAGE_SECRET.value
    assert sentinel not in str(evidence_error.value)
    with StorageUnitOfWork(factory) as reader:
        assert reader.evidence.list_for_run(RUN_ID) == ()

    inspector = inspect(engine)
    assert set(column["name"] for column in inspector.get_columns("evidence_index")) == {
        "evidence_id",
        "run_id",
        "case_id",
        "artifact_path",
        "sha256",
        "byte_count",
        "created_at_us",
    }
    engine.dispose()
    persisted = b"".join(
        candidate.read_bytes()
        for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm"))
        if candidate.exists()
    )
    assert sentinel.encode() not in persisted


def test_default_database_path_and_uow_public_boundary(tmp_path: Path) -> None:
    assert default_database_path(tmp_path) == tmp_path / "jiejian.db"
    engine = create_sqlite_engine(tmp_path / "boundary.db")
    try:
        work = StorageUnitOfWork(create_session_factory(engine))
        assert not hasattr(work, "session")
        with pytest.raises(JiejianError) as captured:
            work.commit()
        assert captured.value.code == ErrorCode.STORAGE_STATE.value
    finally:
        engine.dispose()


def test_database_initialization_errors_are_stable_and_hide_paths(
    tmp_path: Path,
) -> None:
    sentinel = "stage21-path-secret-sentinel"
    blocking_file = tmp_path / sentinel
    blocking_file.write_text("not a directory", encoding="utf-8")

    with pytest.raises(JiejianError) as engine_error:
        create_sqlite_engine(blocking_file / "database.db")
    with pytest.raises(JiejianError) as migration_error:
        upgrade_database(blocking_file / "database.db")

    assert engine_error.value.code == ErrorCode.STORAGE_FAILURE.value
    assert migration_error.value.code == ErrorCode.STORAGE_MIGRATION.value
    serialized = (
        str(engine_error.value)
        + repr(engine_error.value.to_dict())
        + str(migration_error.value)
        + repr(migration_error.value.to_dict())
    )
    assert sentinel not in serialized
    assert "FileExistsError" not in serialized
