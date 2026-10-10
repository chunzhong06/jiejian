# 验证材料建议迁移保留非空历史、缺失的批准实体引用不补编，失败时整次回滚。
import importlib.util
import json
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
from product.backend.core.errors import JiejianError
from tests.fixtures.migration_history import prior_database

ROOT=Path(__file__).resolve().parents[4]


def _prior(tmp_path):
    path=prior_database(tmp_path,'0011_runtime_load_jobs')
    config=Config(str(ROOT/'product/backend/alembic.ini'));config.attributes['configure_logger']=False
    config.set_main_option('sqlalchemy.url','sqlite+pysqlite:///'+path.as_posix())
    command.upgrade(config,'0013_rule_decisions')
    payload=json.dumps({'schema_version':'1','project_id':'project','candidate_id':'rcd_'+'1'*32,'revision':1,
        'basis_id':'rb_'+'a'*64,'content':{'original_text':'原有的业务要求'},'submitted_via':'MCP','created_at_us':1},ensure_ascii=False)
    with sqlite3.connect(path) as connection:
        connection.execute('INSERT INTO rule_candidates VALUES (?,?,1,1)',('rcd_'+'1'*32,'project'))
        connection.execute('INSERT INTO rule_candidate_revisions VALUES (?,1,?)',('rcd_'+'1'*32,payload))
    return path,payload


def _snapshot(path):
    with sqlite3.connect(path) as connection:return tuple(connection.iterdump())


def test_suggestion_upgrade_preserves_prior_data_and_has_no_invented_advice(tmp_path):
    path,payload=_prior(tmp_path)
    upgrade_database(path);require_current_database(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT payload FROM rule_candidate_revisions').fetchone()==(payload,)
        assert connection.execute('SELECT count(*) FROM preparation_receipts').fetchone()==(1,)
        assert connection.execute('SELECT count(*) FROM preparation_suggestions').fetchone()==(0,)
        column=next(row for row in connection.execute('PRAGMA table_info(rule_candidate_approval_mappings)') if row[1]=='entity_references_json')
        assert column[3]==0 and column[4] is None
        assert connection.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_suggestion_migration_interruption_restores_schema_and_data(tmp_path,monkeypatch):
    path,_=_prior(tmp_path);before=_snapshot(path)
    spec=importlib.util.spec_from_file_location('suggestion_migration',ROOT/'product/backend/migrations/versions/0014_preparation_suggestions.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    engine=create_engine('sqlite+pysqlite:///'+path.as_posix())
    with engine.connect() as connection:
        context=MigrationContext.configure(connection);monkeypatch.setattr(module,'op',Operations(context))
        execute=connection.exec_driver_sql
        interrupted=False
        def interrupt(statement,*args,**kwargs):
            nonlocal interrupted
            if statement=='RELEASE SAVEPOINT preparation_suggestions' and not interrupted:
                interrupted=True
                raise RuntimeError('injected interruption')
            return execute(statement,*args,**kwargs)
        monkeypatch.setattr(connection,'exec_driver_sql',interrupt)
        with pytest.raises(RuntimeError):
            with context.begin_transaction(_per_migration=True):module.upgrade()
    engine.dispose();assert _snapshot(path)==before


def test_unexpected_prior_structure_is_not_silently_migrated(tmp_path):
    path,_=_prior(tmp_path)
    with sqlite3.connect(path) as connection:connection.execute('ALTER TABLE rule_candidates ADD COLUMN unexpected TEXT')
    before=_snapshot(path)
    with pytest.raises(JiejianError):upgrade_database(path)
    assert _snapshot(path)==before
