# 验证情境决定迁移保留旧候选原文和回执；迁移失败或旧结构漂移时不改原库。
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
from product.backend.core.boundaries.rule_candidates import read_candidate_revision
from tests.fixtures.migration_history import prior_database

ROOT=Path(__file__).resolve().parents[4]


def _prior(tmp_path):
    path=prior_database(tmp_path,'0011_runtime_load_jobs')
    config=Config(str(ROOT/'product/backend/alembic.ini')); config.attributes['configure_logger']=False
    config.set_main_option('sqlalchemy.url','sqlite+pysqlite:///'+path.as_posix())
    command.upgrade(config,'0012_proof_preparation')
    value={'schema_version':'1','project_id':'project','candidate_id':'rcd_'+'1'*32,'revision':1,
        'basis_id':'rb_'+'a'*64,'content':{'original_text':'保留旧规则原话'},'submitted_via':'MCP','created_at_us':1}
    payload=json.dumps(value,ensure_ascii=False)
    with sqlite3.connect(path) as connection:
        connection.execute('INSERT INTO rule_candidates VALUES (?,?,1,1)',(value['candidate_id'],'project'))
        connection.execute('INSERT INTO rule_candidate_revisions VALUES (?,1,?)',(value['candidate_id'],payload))
        connection.execute('INSERT INTO rule_candidate_receipts VALUES (?,?,?,?,?,1)',('project','SAVE','a'*32,'b'*64,value['candidate_id']))
    return path,payload


def _snapshot(path):
    with sqlite3.connect(path) as connection:
        return tuple(connection.iterdump())


def test_upgrade_preserves_v1_candidate_without_fabricating_decisions(tmp_path):
    path,payload=_prior(tmp_path)
    upgrade_database(path); require_current_database(path)
    with sqlite3.connect(path) as connection:
        stored=connection.execute('SELECT payload FROM rule_candidate_revisions').fetchone()[0]
        assert stored==payload
        assert read_candidate_revision(stored).schema_version=='1'
        assert connection.execute('SELECT count(*) FROM rule_candidate_decisions').fetchone()==(0,)
        assert connection.execute('SELECT count(*) FROM rule_candidate_receipts').fetchone()==(1,)
        assert connection.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_failed_decision_migration_restores_schema_and_data(tmp_path,monkeypatch):
    path,_=_prior(tmp_path); before=_snapshot(path)
    spec=importlib.util.spec_from_file_location('decision_migration',ROOT/'product/backend/migrations/versions/0013_rule_decisions.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    engine=create_engine('sqlite+pysqlite:///'+path.as_posix())
    with engine.connect() as connection:
        context=MigrationContext.configure(connection);monkeypatch.setattr(module,'op',Operations(context))
        execute=connection.exec_driver_sql
        def interrupt(statement,*args,**kwargs):
            if statement=='RELEASE SAVEPOINT rule_decisions':
                raise RuntimeError('injected interruption')
            return execute(statement,*args,**kwargs)
        monkeypatch.setattr(connection,'exec_driver_sql',interrupt)
        with pytest.raises(RuntimeError):
            with context.begin_transaction(_per_migration=True):module.upgrade()
    engine.dispose();assert _snapshot(path)==before


def test_drifted_prior_structure_is_rejected_without_changes(tmp_path):
    path,_=_prior(tmp_path)
    with sqlite3.connect(path) as connection:connection.execute('ALTER TABLE rule_candidates ADD COLUMN unexpected TEXT')
    before=_snapshot(path)
    with pytest.raises(JiejianError):upgrade_database(path)
    assert _snapshot(path)==before
