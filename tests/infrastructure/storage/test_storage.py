# 验证持久化基础设施中的存储装配。

from __future__ import annotations
from tests.support.builders.migration_history import migration_head
import json
from collections.abc import Iterator
from io import StringIO
from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from sqlalchemy import CheckConstraint, UniqueConstraint, inspect, insert, text
from sqlalchemy.engine import Connection, Engine
pytestmark = [pytest.mark.level3, pytest.mark.database]
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from product.backend.domain.lifecycle import JobState, ProjectStatus, RunLifecycle, RunVerdict
from product.backend.domain.errors import ErrorCode, JiejianError
from product.protocols.runner.input import STAGED_ARTIFACT_MAX_BYTES
from product.backend.infrastructure.runtime.logging import configure_logging
from product.backend.infrastructure.storage.db import SQLITE_BUSY_TIMEOUT_MS, create_session_factory, create_sqlite_engine, default_database_path, prepare_database
from product.backend.infrastructure.storage.results.evidence import EvidenceIndexRecord
from product.backend.infrastructure.storage.execution.jobs import JobEventRecord, JobRecord
from product.backend.infrastructure.storage.applications.projects import ProjectRecord
from product.backend.infrastructure.storage.execution.runs import RunRecord
from product.backend.infrastructure.storage.unit_of_work import StorageUnitOfWork
from product.backend.migrations.runtime import migration_resources
from product.backend.infrastructure.storage.base import Base
from product.backend.infrastructure.storage.execution.jobs import JobRow
from product.backend.infrastructure.storage.execution.runs import RunRow
from product.backend.infrastructure.storage.applications.projects import ProjectRow
from product.backend.infrastructure.storage.results.evidence import EvidenceIndexRow
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
    prepare_database(database_path)
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

def test_sourcemigration_resources_uses_backend_single_source() -> None:
    with migration_resources() as root:
        assert root == Path(__file__).resolve().parents[3] / "product" / "backend"
        assert (root / "alembic.ini").is_file()
        assert (root / "migrations").is_dir()

@pytest.mark.parametrize('filename', ['blank.db', '含 空格%及#号.db'])
def test_blank_database_upgrade_is_repeatable_and_at_head(tmp_path: Path, filename: str) -> None:
    path = tmp_path / filename
    prepare_database(path)
    prepare_database(path)
    engine = create_sqlite_engine(path)
    try:
        inspector = inspect(engine)
        assert set(inspector.get_table_names()) == set(Base.metadata.tables) | {
            "alembic_version"
        }
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == migration_head()
        recording_columns = {item["name"] for item in inspector.get_columns("recordings")}
        assert {"purpose", "parent_recording_id"} <= recording_columns
    finally:
        engine.dispose()

def test_migration_does_not_disable_existing_application_logger(tmp_path: Path) -> None:
    stream = StringIO()
    logger = configure_logging("INFO", stream=stream)
    logger.info("before migration")

    prepare_database(tmp_path / "logging.db")
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
                    request_hash="b" * 64,
                    plan_fingerprint="c" * 64,
                    source_fingerprint="d" * 64,
                    policy_epoch=3,
                    engine_version="0.1.0",
                    lifecycle="QUEUED",
                    verdict=None,
                    created_at_us=NOW_US,
                    updated_at_us=NOW_US,
                    finished_at_us=None,
                )
            )
        transaction.rollback()

def test_default_database_path_and_uow_public_boundary(tmp_path: Path) -> None:
    assert default_database_path(tmp_path) == tmp_path / "data" / "jiejian.db"
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
    sentinel = "storage-path-secret-sentinel"
    blocking_file = tmp_path / sentinel
    blocking_file.write_text("not a directory", encoding="utf-8")

    with pytest.raises(JiejianError) as engine_error:
        create_sqlite_engine(blocking_file / "database.db")
    with pytest.raises(JiejianError) as migration_error:
        prepare_database(blocking_file / "database.db")

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
