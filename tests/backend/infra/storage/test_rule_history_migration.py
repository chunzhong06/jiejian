# 规则历史迁移保留原Run/证据，仅增加可重建索引；未知旧结构不能被猜测升级。
from pathlib import Path
import sqlite3
import pytest
from alembic import command
from alembic.config import Config
from product.backend.infra.storage import upgrade_database
from product.backend.core.errors import JiejianError
from tests.fixtures.migration_history import prior_database


def prior(tmp_path):
    path=prior_database(tmp_path,'0011_runtime_load_jobs')
    root=Path(__file__).resolve().parents[4]
    config=Config(str(root/'product/backend/alembic.ini'));config.attributes['configure_logger']=False
    config.set_main_option('sqlalchemy.url','sqlite+pysqlite:///'+path.as_posix());command.upgrade(config,'0016_capture_recovery')
    return path


def test_upgrade_does_not_invent_old_rule_associations(tmp_path):
    path=prior(tmp_path)
    with sqlite3.connect(path) as db:before=db.execute('SELECT run_id,lifecycle,verdict FROM runs ORDER BY run_id').fetchall()
    upgrade_database(path)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT run_id,lifecycle,verdict FROM runs ORDER BY run_id').fetchall()==before
        assert db.execute('SELECT count(*) FROM rule_check_index').fetchone()==(0,)
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_drifted_prior_database_is_not_partially_upgraded(tmp_path):
    path=prior(tmp_path)
    with sqlite3.connect(path) as db:
        db.execute('ALTER TABLE reference_captures ADD COLUMN unexpected TEXT');before=tuple(db.iterdump())
    with pytest.raises(JiejianError):upgrade_database(path)
    with sqlite3.connect(path) as db:assert tuple(db.iterdump())==before
