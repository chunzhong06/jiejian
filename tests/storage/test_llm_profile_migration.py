from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

from jiejian.storage import upgrade_database


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_0007_adds_only_non_secret_profile_table_and_has_no_downgrade(tmp_path: Path) -> None:
    database = tmp_path / "profiles.db"
    config = Config(str(PROJECT_ROOT / "backend" / "alembic.ini"))
    config.attributes["configure_logger"] = False
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database.resolve().as_posix()}")
    command.upgrade(config, "0006_stage5_governed_project_binding")
    upgrade_database(database)
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0007_stage5_llm_profiles",
        )
        columns = {row[1] for row in connection.execute("PRAGMA table_info(llm_profiles)")}
        assert columns == {
            "profile_name",
            "schema_version",
            "provider",
            "model",
            "base_url",
            "timeout_ms",
            "max_input_bytes",
            "max_output_bytes",
            "max_budget_microusd",
            "enabled",
            "secret_ref",
            "allow_local_http",
            "created_at_us",
            "updated_at_us",
        }
        assert "secret" not in columns
    finally:
        connection.close()

    try:
        command.downgrade(config, "0006_stage5_governed_project_binding")
    except RuntimeError as exc:
        assert "只允许向前" in str(exc)
    else:
        raise AssertionError("0007 must not provide an automatic downgrade")
