# 验证第五种Job目标的迁移保持旧记录、严格单目标与单次尝试，并拒绝结构漂移。
import sqlite3
from pathlib import Path
import pytest
from alembic import command
from alembic.config import Config
from product.backend.infra.storage import upgrade_database
from product.backend.infra.storage.db import require_current_database
from product.backend.core.errors import JiejianError
from tests.fixtures.migration_history import prior_database

ROOT=Path(__file__).resolve().parents[4]


def prior(tmp_path):
    path=prior_database(tmp_path,'0011_runtime_load_jobs')
    config=Config(str(ROOT/'product/backend/alembic.ini'));config.attributes['configure_logger']=False
    config.set_main_option('sqlalchemy.url','sqlite+pysqlite:///'+path.as_posix())
    command.upgrade(config,'0014_preparation_suggestions')
    return path


def test_upgrade_keeps_old_jobs_and_adds_strict_capture_target(tmp_path):
    path=prior(tmp_path)
    with sqlite3.connect(path) as db:
        jobs=db.execute('SELECT job_id,operation_type,request_hash,state FROM jobs ORDER BY job_id').fetchall()
    upgrade_database(path);require_current_database(path);upgrade_database(path)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT job_id,operation_type,request_hash,state FROM jobs ORDER BY job_id').fetchall()==jobs
        assert db.execute('SELECT count(*) FROM proof_artifact_inputs').fetchone()==(0,)
        sql=db.execute("SELECT sql FROM sqlite_master WHERE name='jobs'").fetchone()[0]
        assert 'reference_capture_id IS NOT NULL' in sql and 'max_attempts = 1' in sql
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_unknown_prior_schema_remains_unchanged(tmp_path):
    path=prior(tmp_path)
    with sqlite3.connect(path) as db:
        db.execute('ALTER TABLE proof_sources ADD COLUMN unexpected TEXT')
        before=tuple(db.iterdump())
    with pytest.raises(JiejianError):upgrade_database(path)
    with sqlite3.connect(path) as db:assert tuple(db.iterdump())==before
