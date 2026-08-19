from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

from jiejian.storage import upgrade_database


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_old_database_upgrades_to_stage7_findings_without_rewriting_v1_tables(tmp_path: Path) -> None:
    database = tmp_path / "stage7-findings.db"
    config = Config(str(PROJECT_ROOT / "backend" / "alembic.ini"))
    config.attributes["configure_logger"] = False
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database.resolve().as_posix()}")
    command.upgrade(config, "0008_permission_execution_profiles")
    upgrade_database(database)

    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0010_stage7_gate",
        )
        assert {row[1] for row in connection.execute("PRAGMA table_info(evidence_index)")} == {
            "evidence_id", "run_id", "case_id", "artifact_path", "sha256", "byte_count", "created_at_us",
        }
        assert {row[1] for row in connection.execute("PRAGMA table_info(findings)")} == {
            "finding_id", "schema_version", "project_id", "identity_json", "created_at_us", "updated_at_us",
        }
        assert {row[1] for row in connection.execute("PRAGMA table_info(finding_occurrences)")} == {
            "occurrence_id", "schema_version", "finding_id", "project_id", "run_id", "status",
            "verdict", "severity", "evidence_refs_json", "object_context_json", "coverage_context_json", "created_at_us",
        }
        assert {row[1] for row in connection.execute("PRAGMA table_info(regression_baselines)")} >= {
            "baseline_id", "accepted_run_id", "finding_refs_json", "coverage_ids_json", "actor", "reason",
        }
        assert {row[1] for row in connection.execute("PRAGMA table_info(gate_results)")} >= {
            "gate_result_id", "baseline_id", "run_id", "input_hash", "decision", "reasons_json",
        }
    finally:
        connection.close()
