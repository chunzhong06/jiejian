# 验证非空旧库升级保留事实，漂移和 DDL 中断不能留下半套开发任务表。
import importlib.util
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine

from product.backend.infra.storage import upgrade_database
from product.backend.infra.storage.db import require_current_database

ROOT = Path(__file__).resolve().parents[4]


def prior(tmp_path, revision="0007_preparation_recovery"):
    path = tmp_path / "old.db"
    config = Config(str(ROOT / "product/backend/alembic.ini"))
    config.attributes["configure_logger"] = False
    config.set_main_option("sqlalchemy.url", "sqlite+pysqlite:///" + path.as_posix())
    command.upgrade(config, revision)
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO projects VALUES ('project','保留的项目','READY','WEB',NULL,NULL,1,1)")
        connection.execute("INSERT INTO preparation_receipts VALUES ('receipt','project',?,1,'{}')", ("a" * 64,))
    return path


@pytest.mark.parametrize("revision", ["0007_preparation_recovery", "0008_development_delivery"])
def test_nonempty_prior_upgrade_preserves_history_without_inventing_tasks(tmp_path, revision):
    path = prior(tmp_path, revision)
    with sqlite3.connect(path) as connection:
        before = connection.execute("SELECT * FROM preparation_receipts").fetchall()
    upgrade_database(path)
    require_current_database(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT * FROM preparation_receipts").fetchall() == before
        assert connection.execute("SELECT count(*) FROM development_tasks").fetchone() == (0,)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    saved = path.read_bytes()
    upgrade_database(path)
    assert path.read_bytes() == saved


def test_drift_is_read_only_rejection(tmp_path):
    path = prior(tmp_path)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE INDEX unexpected ON projects(name)")
    before = path.read_bytes()
    with pytest.raises(Exception):
        upgrade_database(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("previous,current,absent", [("0007_preparation_recovery", "0008_development_delivery", "development_tasks"),
    ("0008_development_delivery", "0009_delivery_check_links", "development_check_runs")])
def test_interrupted_ddl_rolls_back_all_new_tables(tmp_path, monkeypatch, previous, current, absent):
    path = prior(tmp_path, previous)
    spec = importlib.util.spec_from_file_location("development_migration", ROOT / f"product/backend/migrations/versions/{current}.py")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite+pysqlite:///" + path.as_posix())
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        monkeypatch.setattr(migration, "op", Operations(context))
        monkeypatch.setattr(migration, "_CREATE_SQL", (*migration._CREATE_SQL[:2], "INVALID DDL"))
        with pytest.raises(Exception):
            with context.begin_transaction(_per_migration=True):
                migration.upgrade()
    engine.dispose()
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (previous,)
        assert connection.execute("SELECT name FROM sqlite_master WHERE name = ?", (absent,)).fetchall() == []
        assert connection.execute("SELECT count(*) FROM preparation_receipts").fetchone() == (1,)
