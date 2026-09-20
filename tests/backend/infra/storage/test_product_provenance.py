# 验证新增元数据迁移严格保留非空 0005；不启动产品或执行目标。
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
from product.backend.infra.storage.db import require_current_database, _sqlite_schema_signature

ROOT = Path(__file__).resolve().parents[4]


def config(path):
    value = Config(str(ROOT / "product/backend/alembic.ini"))
    value.attributes["configure_logger"] = False
    value.set_main_option("sqlalchemy.url", "sqlite+pysqlite:///" + path.as_posix())
    return value


def old(tmp_path):
    path = tmp_path / "old.db"
    command.upgrade(config(path), "0005_verification_loop_v3")
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO projects VALUES ('project','原项目','READY','WEB',NULL,NULL,1,1)")
        connection.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ("run_" + "a" * 32, "project", "a" * 64, "b" * 64, "c" * 64, 1, "1.1.9", "COMPLETED", "PASS", 1, 2, 2))
    return path


def dump(path):
    with sqlite3.connect(path) as connection:
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'alembic_version'")]
        return {table: connection.execute(f'SELECT * FROM "{table}"').fetchall() for table in tables}


def test_nonempty_0005_preserved_fresh_repeat(tmp_path):
    prior = old(tmp_path)
    before = dump(prior)
    upgrade_database(prior)
    require_current_database(prior)
    after = dump(prior)
    assert {key: after[key] for key in before} == before
    first = prior.read_bytes()
    upgrade_database(prior)
    assert prior.read_bytes() == first
    fresh = tmp_path / "fresh.db"
    upgrade_database(fresh)
    with sqlite3.connect(prior) as left, sqlite3.connect(fresh) as right:
        assert _sqlite_schema_signature(left) == _sqlite_schema_signature(right)
        assert left.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0006_product_provenance"
        assert left.execute("PRAGMA foreign_key_check").fetchall() == []


def test_0005_drift_rejected_unchanged(tmp_path):
    prior = old(tmp_path)
    with sqlite3.connect(prior) as connection:
        connection.execute("CREATE INDEX unexpected ON projects(name)")
    before = prior.read_bytes()
    with pytest.raises(Exception):
        upgrade_database(prior)
    assert prior.read_bytes() == before


def test_downgrade_refused_without_mutation(tmp_path):
    path = tmp_path / "current.db"
    upgrade_database(path)
    before = path.read_bytes()
    with pytest.raises(RuntimeError):
        command.downgrade(config(path), "0005_verification_loop_v3")
    assert path.read_bytes() == before


def test_mid_ddl_failure_rolls_back_tables_and_marker(tmp_path, monkeypatch):
    path = old(tmp_path)
    before = dump(path)
    spec = importlib.util.spec_from_file_location("provenance_migration", ROOT / "product/backend/migrations/versions/0006_product_provenance.py")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite+pysqlite:///" + path.as_posix())
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        monkeypatch.setattr(migration, "op", Operations(context))
        monkeypatch.setattr(migration, "_CREATE_SQL", (*migration._CREATE_SQL[:2], "INVALID INJECTED DDL"))
        with pytest.raises(Exception):
            with context.begin_transaction(_per_migration=True):
                migration.upgrade()
    engine.dispose()
    assert dump(path) == before
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0005_verification_loop_v3"
