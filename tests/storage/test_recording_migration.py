from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from jiejian.storage import upgrade_database

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
        ).fetchone() == ("0003_stage4_control_plane",)
        assert connection.execute(
            "SELECT source_path, source_hash, active_contract_path, active_contract_hash "
            "FROM projects"
        ).fetchone() == (None, None, None, None)
        assert {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )} >= {"recordings", "flow_draft_revisions"}
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


def _upgrade_to(database: Path, revision: str) -> None:
    config = Config(str(PROJECT_ROOT / "backend" / "alembic.ini"))
    config.attributes["configure_logger"] = False
    config.set_main_option(
        "sqlalchemy.url",
        f"sqlite+pysqlite:///{database.resolve().as_posix()}",
    )
    command.upgrade(config, revision)
