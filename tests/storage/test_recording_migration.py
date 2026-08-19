from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

pytestmark = pytest.mark.database

from jiejian.storage import (
    StorageUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
    upgrade_database,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NOW_US = 1_810_000_000_000_000


def test_stage4_migration_preserves_run_jobs_and_enforces_single_target(
    tmp_path: Path,
) -> None:
    database = tmp_path / "legacy.db"
    _upgrade_to(database, "0001_stage2_storage")
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "INSERT INTO projects VALUES (?, ?, ?, ?, ?)",
            ("migration-project", "migration", "READY", NOW_US, NOW_US),
        )
        connection.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "run_" + "1" * 32,
                "migration-project",
                "contract",
                1,
                "0.1.0",
                "QUEUED",
                None,
                NOW_US,
                NOW_US,
                None,
            ),
        )
        connection.execute(
            "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "job_" + "2" * 32,
                "migration-project",
                "run_" + "1" * 32,
                "ACTIVE_RUN",
                "PENDING",
                "legacy",
                "a" * 64,
                0,
                3,
                NOW_US,
                None,
                0,
                None,
                None,
                NOW_US,
                NOW_US,
            ),
        )
        connection.execute(
            "INSERT INTO job_events VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "job_" + "2" * 32,
                1,
                "JOB_SUBMITTED",
                None,
                "PENDING",
                NOW_US,
                "{}",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    upgrade_database(database)
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        assert connection.execute(
            "SELECT run_id, recording_id FROM jobs"
        ).fetchone() == ("run_" + "1" * 32, None)
        assert connection.execute("SELECT count(*) FROM job_events").fetchone() == (1,)
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == ("0010_stage7_gate",)
        assert connection.execute(
            "SELECT source_path, source_hash, active_contract_path, active_contract_hash "
            "FROM projects"
        ).fetchone() == (None, None, None, None)
        assert connection.execute(
            "SELECT governed_contract_id, governed_contract_version FROM projects"
        ).fetchone() == (None, None)
        assert {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )} >= {
            "recordings",
            "flow_draft_revisions",
            "requirements",
            "contract_candidates",
            "contract_versions",
        }
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO jobs "
                "(job_id, project_id, run_id, recording_id, operation_type, state, "
                "idempotency_key, request_hash, attempt, max_attempts, available_at_us, "
                "lease_owner, fencing_token, lease_expires_at_us, "
                "cancel_requested_at_us, created_at_us, updated_at_us) "
                "VALUES (?, ?, NULL, NULL, ?, ?, ?, ?, 0, 1, ?, NULL, 0, NULL, NULL, ?, ?)",
                (
                    "job_" + "3" * 32,
                    "migration-project",
                    "BROWSER_RECORDING",
                    "PENDING",
                    "invalid-target",
                    "b" * 64,
                    NOW_US,
                    NOW_US,
                    NOW_US,
                ),
            )
        connection.execute(
            "INSERT INTO recordings "
            "(recording_id, project_id, flow_id, state, created_at_us, "
            "updated_at_us, started_at_us, capture_finished_at_us, "
            "finished_at_us, pending_terminal_state, reason_codes_json, "
            "state_events_json, browser_events_json) "
            "VALUES (?, ?, ?, 'CREATED', ?, ?, NULL, NULL, NULL, NULL, "
            "'[]', '[]', '[]')",
            (
                "rec_" + "4" * 32,
                "migration-project",
                "recorded-flow",
                NOW_US,
                NOW_US,
            ),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO jobs "
                "(job_id, project_id, run_id, recording_id, operation_type, "
                "state, idempotency_key, request_hash, attempt, max_attempts, "
                "available_at_us, lease_owner, fencing_token, "
                "lease_expires_at_us, cancel_requested_at_us, created_at_us, "
                "updated_at_us) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 1, ?, "
                "NULL, 0, NULL, NULL, ?, ?)",
                (
                    "job_" + "5" * 32,
                    "migration-project",
                    "run_" + "1" * 32,
                    "rec_" + "4" * 32,
                    "BROWSER_RECORDING",
                    "PENDING",
                    "invalid-double-target",
                    "c" * 64,
                    NOW_US,
                    NOW_US,
                    NOW_US,
                ),
            )
    finally:
        connection.close()


def test_stage5_migration_upgrades_stage4_without_changing_project_data(
    tmp_path: Path,
) -> None:
    database = tmp_path / "stage4.db"
    _upgrade_to(database, "0003_stage4_control_plane")
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "INSERT INTO projects "
            "(project_id, name, status, source_path, source_hash, "
            "active_contract_path, active_contract_hash, created_at_us, updated_at_us) "
            "VALUES (?, ?, 'READY', NULL, NULL, NULL, NULL, ?, ?)",
            ("stage4-project", "stage4", NOW_US, NOW_US),
        )
        connection.commit()
    finally:
        connection.close()

    upgrade_database(database)
    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT project_id, name, status FROM projects"
        ).fetchone() == ("stage4-project", "stage4", "READY")
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == ("0010_stage7_gate",)
        assert {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )} >= {"requirements", "contract_candidates", "contract_versions"}
        assert "llm_metadata_json" in {
            row[1] for row in connection.execute("PRAGMA table_info(contract_candidates)")
        }
    finally:
        connection.close()


def test_stage5_llm_metadata_migration_upgrades_0004(tmp_path: Path) -> None:
    database = tmp_path / "stage5-llm.db"
    _upgrade_to(database, "0004_stage5_contracts")

    requirement_id = "req_" + "1" * 32
    candidate_id = "cand_" + "2" * 32
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "INSERT INTO projects "
            "(project_id, name, status, source_path, source_hash, "
            "active_contract_path, active_contract_hash, created_at_us, updated_at_us) "
            "VALUES (?, ?, 'READY', NULL, NULL, NULL, NULL, ?, ?)",
            ("legacy-contract-project", "legacy-contract", NOW_US, NOW_US),
        )
        connection.execute(
            "INSERT INTO requirements "
            "(requirement_id, schema_version, project_id, source_type, source_locator, "
            "source_sha256, requirement_text, security_tags_json, created_by, created_at_us) "
            "VALUES (?, '1', ?, 'requirement_text', ?, ?, ?, '[]', ?, ?)",
            (
                requirement_id,
                "legacy-contract-project",
                "requirements.md#legacy",
                "a" * 64,
                "legacy requirement",
                "migration-test",
                NOW_US,
            ),
        )
        connection.execute(
            "INSERT INTO contract_candidates "
            "(candidate_id, schema_version, project_id, source_type, source_locator, "
            "source_sha256, rule_json, requirement_ids_json, created_by, created_at_us) "
            "VALUES (?, '1', ?, 'static_analysis', ?, ?, ?, ?, ?, ?)",
            (
                candidate_id,
                "legacy-contract-project",
                "analysis/legacy.py#rule",
                "b" * 64,
                json.dumps(
                    {
                        "schema_version": "1",
                        "id": "legacy-rule",
                        "kind": "foreign_read",
                        "required_observers": ["http"],
                        "severity": "high",
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                json.dumps([requirement_id], separators=(",", ":")),
                "migration-test",
                NOW_US,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    upgrade_database(database)
    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT llm_metadata_json FROM contract_candidates WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchone() == (None,)
        assert connection.execute(
            "SELECT governed_contract_id, governed_contract_version FROM projects "
            "WHERE project_id = ?",
            ("legacy-contract-project",),
        ).fetchone() == (None, None)
    finally:
        connection.close()

    engine = create_sqlite_engine(database)
    factory = create_session_factory(engine)
    with StorageUnitOfWork(factory) as work:
        stored_requirement = work.requirements.get(requirement_id)
        stored_candidate = work.contract_candidates.get(candidate_id)
    engine.dispose()
    assert stored_requirement is not None
    assert stored_candidate is not None
    assert stored_candidate.llm_metadata is None

    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == ("0010_stage7_gate",)
        assert "llm_metadata_json" in {
            row[1] for row in connection.execute("PRAGMA table_info(contract_candidates)")
        }
    finally:
        connection.close()


def _upgrade_to(database: Path, revision: str) -> None:
    config = Config(str(PROJECT_ROOT / "backend" / "alembic.ini"))
    config.attributes["configure_logger"] = False
    config.set_main_option(
        "sqlalchemy.url",
        f"sqlite+pysqlite:///{database.resolve().as_posix()}",
    )
    command.upgrade(config, revision)
