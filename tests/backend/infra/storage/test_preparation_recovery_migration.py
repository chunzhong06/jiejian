# 核对非空 0006 增量升级、精确拒绝漂移和中途 DDL 失败的原子回滚。
from pathlib import Path
import importlib.util
import sqlite3
import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine
from product.backend.infra.storage import upgrade_database
from product.backend.infra.storage.db import require_current_database

ROOT = Path(__file__).resolve().parents[4]


def prior(tmp_path):
    path = tmp_path / "prior.db"
    config = Config(str(ROOT / "product/backend/alembic.ini"))
    config.attributes["configure_logger"] = False
    config.set_main_option("sqlalchemy.url", "sqlite+pysqlite:///" + path.as_posix())
    command.upgrade(config, "0006_product_provenance")
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO projects VALUES ('project','保留的项目','READY','WEB',NULL,NULL,1,1)")
        connection.execute("INSERT INTO environment_operations VALUES ('operation','start','UNKNOWN',1,NULL,NULL,'project',NULL,0)")
    return path


def test_existing_facts_and_unknown_ownership_remain_unchanged(tmp_path):
    path = prior(tmp_path)
    with sqlite3.connect(path) as connection:
        before = connection.execute("SELECT * FROM environment_operations").fetchall()
    upgrade_database(path); require_current_database(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT * FROM environment_operations").fetchall() == before
        assert connection.execute("SELECT COUNT(*) FROM sample_instances").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM preparation_receipts").fetchone()[0] == 0
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    data = path.read_bytes(); upgrade_database(path)
    assert path.read_bytes() == data


def test_0006_schema_drift_is_rejected_before_mutation(tmp_path):
    path = prior(tmp_path)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE INDEX unexpected ON projects(name)")
    before = path.read_bytes()
    with pytest.raises(Exception): upgrade_database(path)
    assert path.read_bytes() == before


def test_recovery_ddl_failure_keeps_old_revision_and_rows(tmp_path, monkeypatch):
    path = prior(tmp_path)
    spec = importlib.util.spec_from_file_location("recovery_migration", ROOT / "product/backend/migrations/versions/0007_preparation_recovery.py")
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    engine = create_engine("sqlite+pysqlite:///" + path.as_posix())
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        monkeypatch.setattr(migration, "op", Operations(context))
        monkeypatch.setattr(migration, "_CREATE_SQL", (*migration._CREATE_SQL[:2], "INVALID DDL"))
        with pytest.raises(Exception):
            with context.begin_transaction(_per_migration=True): migration.upgrade()
    engine.dispose()
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0006_product_provenance"
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='preparation_receipts'").fetchall() == []
        assert connection.execute("SELECT state FROM environment_operations").fetchone()[0] == "UNKNOWN"
