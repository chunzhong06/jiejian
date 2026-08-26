# 验证 Results storage 中 Evidence、Finding 与秘密/路径完整性边界。

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

@pytest.mark.parametrize("changes", [{"artifact_path": "../escape.json"}, {"artifact_path": "NUL.txt"}, {"artifact_path": "name."}, {"artifact_path": "file.txt:stream"}, {"byte_count": STAGED_ARTIFACT_MAX_BYTES + 1}, {"evidence_id": "ev_" + "b" * 20}])
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

def test_one_case_can_publish_distinct_evidence_for_multiple_twins(
    migrated_storage: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _, _, factory = migrated_storage
    second_hash = "b" * 64
    with StorageUnitOfWork(factory) as work:
        work.projects.add(_project())
        work.runs.add(_run())
        work.evidence.add(_evidence())
        work.evidence.add(
            _evidence(
                evidence_id="ev_" + second_hash[:20],
                artifact_path="evidence/second-twin.json",
                sha256=second_hash,
            )
        )
        work.commit()

    with StorageUnitOfWork(factory) as work:
        evidence = work.evidence.list_for_run(RUN_ID)
    assert len(evidence) == 2
    assert {item.case_id for item in evidence} == {"foreign-read-case"}

def test_known_secret_and_evidence_body_never_enter_database(
    migrated_storage: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    path, engine, factory = migrated_storage
    sentinel = "storage-real-secret-sentinel"
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
