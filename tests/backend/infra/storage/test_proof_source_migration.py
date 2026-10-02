# 验证0012升级保留非空材料回执与发布事实，重建父表失败时原库整体不变。
import importlib.util
import sqlite3
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine

from product.backend.infra.storage import upgrade_database
from product.backend.infra.storage.db import require_current_database
from tests.fixtures.migration_history import prior_database

ROOT = Path(__file__).resolve().parents[4]


def _snapshot(path):
    with sqlite3.connect(path) as connection:
        return tuple(connection.iterdump())


def test_proof_upgrade_keeps_old_receipt_namespace(tmp_path):
    path = prior_database(tmp_path, '0011_runtime_load_jobs')
    upgrade_database(path)
    require_current_database(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT * FROM preparation_receipts').fetchall() == [
            ('receipt', 'project', 'a' * 64, 1, '{}', 'MATERIAL_CHANGE')]
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
        assert connection.execute('SELECT count(*) FROM proof_sources').fetchone() == (0,)


def test_proof_upgrade_rollback_preserves_original_schema_and_rows(tmp_path, monkeypatch):
    path = prior_database(tmp_path, '0011_runtime_load_jobs')
    before = _snapshot(path)
    spec = importlib.util.spec_from_file_location('proof_migration', ROOT / 'product/backend/migrations/versions/0012_proof_preparation.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine('sqlite+pysqlite:///' + path.as_posix())
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        monkeypatch.setattr(module, 'op', Operations(context))
        execute = connection.exec_driver_sql
        def interrupt(statement, *args, **kwargs):
            if statement == 'RELEASE SAVEPOINT proof_preparation':
                raise RuntimeError('injected interruption')
            return execute(statement, *args, **kwargs)
        monkeypatch.setattr(connection, 'exec_driver_sql', interrupt)
        with pytest.raises(RuntimeError):
            with context.begin_transaction(_per_migration=True):
                module.upgrade()
    engine.dispose()
    assert _snapshot(path) == before
