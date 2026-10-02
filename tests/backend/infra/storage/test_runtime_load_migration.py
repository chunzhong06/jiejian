# 验证运行加载迁移保留已发布检查与Job外键；中断时DDL与数据同时回滚。
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


def _prior_with_published_run(tmp_path):
    path = prior_database(tmp_path, "0010_rule_candidates")
    run, job, digest = "run_" + "1" * 32, "job_" + "2" * 32, "a" * 64
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (run,"project",digest,digest,digest,1,"1.1.13","COMPLETED","PASS",10,20,20))
        connection.execute("INSERT INTO jobs (job_id,project_id,run_id,operation_type,state,idempotency_key,request_hash,attempt,max_attempts,available_at_us,fencing_token,created_at_us,updated_at_us) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (job,"project",run,"CHECK","SUCCEEDED","original",digest,1,1,10,1,10,20))
        connection.execute("INSERT INTO job_events VALUES (?,?,?,?,?,?,?)",(job,1,"JOB_SUCCEEDED","RUNNING","SUCCEEDED",20,"{}"))
        connection.execute("INSERT INTO check_publications VALUES (?,?,?,?,?,?,?,?)",(run,job,1,1,digest,digest,digest,20))
    return path


def _snapshot(path):
    with sqlite3.connect(path) as connection:
        return {name:connection.execute(f"SELECT * FROM {name}").fetchall()
            for name in ("runs","jobs","job_events","check_publications")}


def test_runtime_load_upgrade_preserves_published_jobs_and_children(tmp_path):
    path = _prior_with_published_run(tmp_path)
    before = _snapshot(path)
    upgrade_database(path)
    require_current_database(path)
    after = _snapshot(path)
    assert after["jobs"] == [(*row,None,None) for row in before["jobs"]]
    for name in ("runs","job_events","check_publications"):
        assert after[name] == before[name]
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT count(*) FROM runtime_loads").fetchone() == (0,)


def test_failure_after_job_rebuild_rolls_back_all_old_references(tmp_path, monkeypatch):
    path = _prior_with_published_run(tmp_path)
    before = _snapshot(path)
    spec = importlib.util.spec_from_file_location("runtime_migration",ROOT/'product/backend/migrations/versions/0011_runtime_load_jobs.py')
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    engine = create_engine('sqlite+pysqlite:///'+path.as_posix())
    with engine.connect() as connection:
        context=MigrationContext.configure(connection)
        monkeypatch.setattr(module,'op',Operations(context))
        execute=connection.exec_driver_sql
        def interrupt(statement,*args,**kwargs):
            if statement == 'RELEASE SAVEPOINT runtime_load_jobs':
                raise RuntimeError('injected failure after rebuilding parent')
            return execute(statement,*args,**kwargs)
        monkeypatch.setattr(connection,'exec_driver_sql',interrupt)
        with pytest.raises(RuntimeError):
            with context.begin_transaction(_per_migration=True): module.upgrade()
    engine.dispose()
    assert _snapshot(path)==before
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT version_num FROM alembic_version').fetchone()==('0010_rule_candidates',)
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='runtime_loads'").fetchall()==[]
