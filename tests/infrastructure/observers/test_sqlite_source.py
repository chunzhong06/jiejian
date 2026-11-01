import json,sqlite3
from types import SimpleNamespace
import pytest

from product.backend.infrastructure.observers.records import sqlite_source as reader
from product.backend.infrastructure.observers.records.record_facts import request_fact
from product.backend.infrastructure.observers.adapters.json_source import SourceReadError
from product.protocols.runtime.transaction_records import RecordRequestScope
from product.protocols.runtime.node_runtime import SqliteDatabaseCapture,SqliteTableCapture


@pytest.fixture
def source(tmp_path,monkeypatch):
    table=SqliteTableCapture(table='tickets',resource_column='id',owner_column='owner_id',fields=('title',))
    spec=SqliteDatabaseCapture(relative_path='store.sqlite',tables=(table,))
    path=tmp_path/'data/controlled-applications/app/sqlite/0.sqlite';path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as db:
        db.executescript('''CREATE TABLE tickets(id TEXT PRIMARY KEY,owner_id TEXT,title TEXT);
            INSERT INTO tickets VALUES('ticket1','owner','initial');
            CREATE TABLE _jj_meta(generation TEXT,config TEXT);
            CREATE TABLE _jj_rows(seq INTEGER PRIMARY KEY,table_name TEXT,resource_id TEXT,owner_id TEXT,kind TEXT,
                request_nonce TEXT,transaction_id TEXT,before_data TEXT,after_data TEXT,identity_changed INTEGER);
            CREATE TRIGGER _jj_0_tickets_insert AFTER INSERT ON tickets BEGIN SELECT '_jj_rows','_jj_nonce'; END;
            CREATE TRIGGER _jj_0_tickets_update AFTER UPDATE ON tickets BEGIN SELECT '_jj_rows','_jj_nonce'; END;
            CREATE TRIGGER _jj_0_tickets_delete AFTER DELETE ON tickets BEGIN SELECT '_jj_rows','_jj_nonce'; END;''')
        db.execute('INSERT INTO _jj_meta VALUES(?,?)',('generation',spec.model_dump_json()))
    monkeypatch.setattr(reader,'sqlite_selection',lambda *args:(0,spec,table))
    config=SimpleNamespace(source_kind='SQLITE_AUDIT',max_response_bytes=262144)
    reference=SimpleNamespace(project_id='app')
    scope=RecordRequestScope(scope_id='scope',generation='host',request_nonce='a'*64,request_digest='b'*64,state='COMPLETE')
    return tmp_path,path,table,config,reference,scope


@pytest.mark.parametrize('separate_commits,rollback,expected',[(False,False,'ABSENT'),(True,False,'CONFIRMED'),(False,True,'ABSENT')])
def test_committed_effect_distinguishes_internal_steps_restore_and_rollback(source,separate_commits,rollback,expected):
    root,path,_,config,reference,scope=source
    before=reader.read_sqlite_source(root,reference,config,'ticket1').snapshot
    with sqlite3.connect(path) as db:
        for index,(old,new) in enumerate((('initial','reviewed'),('reviewed','initial'))):
            db.execute('UPDATE tickets SET title=? WHERE id=?',(new,'ticket1'))
            db.execute('INSERT INTO _jj_rows VALUES(?,?,?,?,?,?,?,?,?,?)',(index+1,'tickets','ticket1','owner','UPDATE',scope.request_nonce,'tx'+str(index if separate_commits else 0),json.dumps({'title':old}),json.dumps({'title':new}),0))
            if separate_commits:db.commit()
        if rollback:db.rollback()
    view=reader.read_sqlite_source(root,reference,config,'ticket1',scope=scope,verified_subject='member')
    fact=request_fact(before,view,path=('title',),expected_state='reviewed',request_nonce=scope.request_nonce,
        request_digest=scope.request_digest,subject_id='member',resource_id='ticket1',owner_id='owner',collection='tickets')
    assert fact.state==expected


def test_creation_history_keeps_committed_create_then_remove_without_inventing_live_object(source):
    root,path,_,config,reference,scope=source
    config.source_kind='SQLITE_OBJECTS'
    with sqlite3.connect(path) as db:
        for sequence,(kind,before,after) in enumerate((('INSERT',None,'{"title":"created"}'),('DELETE','{"title":"created"}',None)),1):
            db.execute('INSERT INTO _jj_rows VALUES(?,?,?,?,?,?,?,?,?,?)',(sequence,'tickets','new-ticket','owner',kind,scope.request_nonce,'tx'+str(sequence),before,after,0));db.commit()
    view=reader.read_sqlite_source(root,reference,config,'ticket1',scope=scope,verified_subject='member')
    assert [event.kind for event in view.events]==['CREATE','REMOVE']
    assert view.events[0].member.incarnation==view.events[1].member.incarnation
    assert all(item.resource_id!='new-ticket' for item in view.members)


def test_unsupported_values_and_oversized_history_do_not_become_absence(source):
    root,path,_,config,reference,scope=source
    with sqlite3.connect(path) as db:db.execute('UPDATE tickets SET title=?',(b'binary',))
    with pytest.raises(SourceReadError,match='SQLITE_CAPTURE_VALUE_UNSUPPORTED'):
        reader.read_sqlite_source(root,reference,config,'ticket1',scope=scope,verified_subject='member')
    with sqlite3.connect(path) as db:
        db.execute('UPDATE tickets SET title=?',('initial',))
        db.execute('INSERT INTO _jj_rows VALUES(?,?,?,?,?,?,?,?,?,?)',(1,'tickets','ticket1','owner','UPDATE',scope.request_nonce,'tx','{}','x'*1024,0))
    config.max_response_bytes=512
    with pytest.raises(SourceReadError,match='SQLITE_CAPTURE_LIMIT'):
        reader.read_sqlite_source(root,reference,config,'ticket1',scope=scope,verified_subject='member')


def test_failed_test_database_preparation_can_be_corrected_without_partial_copy(tmp_path):
    from product.backend.infrastructure.runtime.process.controlled.sqlite_capture import prepare_sqlite_copies
    original=tmp_path/'store.sqlite'
    with sqlite3.connect(original) as db:
        db.executescript("CREATE TABLE tickets(id TEXT PRIMARY KEY,owner_id TEXT,title TEXT);INSERT INTO tickets VALUES('ticket1','owner','initial');")
    def manifest(field):
        return SimpleNamespace(sqlite=(SqliteDatabaseCapture(relative_path='store.sqlite',tables=(SqliteTableCapture(
            table='tickets',resource_column='id',owner_column='owner_id',fields=(field,)),)),))
    data=tmp_path/'test-data'
    with pytest.raises(ValueError,match='capture fields missing'):
        prepare_sqlite_copies(tmp_path,data,manifest('missing'))
    assert list((data/'sqlite').iterdir())==[]
    prepare_sqlite_copies(tmp_path,data,manifest('title'))
    with sqlite3.connect(data/'sqlite/0.sqlite') as db:
        assert db.execute('SELECT title FROM tickets').fetchone()==('initial',)
        assert db.execute('SELECT config FROM _jj_meta').fetchone()
    with sqlite3.connect(original) as db:
        assert db.execute("SELECT name FROM sqlite_schema WHERE name='_jj_meta'").fetchone() is None


@pytest.mark.parametrize('column',['resource_column','owner_column','fields'])
def test_sqlite_projection_rejects_credential_columns_including_identity_keys(column):
    from pydantic import ValidationError
    values=dict(table='tickets',resource_column='id',owner_column='owner_id',fields=('title',))
    values[column]=('access_token',) if column=='fields' else 'session_token'
    with pytest.raises(ValidationError):SqliteTableCapture(**values)


def test_object_created_and_removed_inside_one_commit_never_becomes_published_creation(source):
    root,path,_,config,reference,scope=source
    config.source_kind='SQLITE_OBJECTS'
    with sqlite3.connect(path) as db:
        for sequence,(kind,before,after) in enumerate((('INSERT',None,'{"title":"created"}'),('DELETE','{"title":"created"}',None)),1):
            db.execute('INSERT INTO _jj_rows VALUES(?,?,?,?,?,?,?,?,?,?)',(sequence,'tickets','new-ticket','owner',kind,scope.request_nonce,'one-transaction',before,after,0))
    view=reader.read_sqlite_source(root,reference,config,'ticket1',scope=scope,verified_subject='member')
    assert view.events==() and not view.foreign_mutations
    assert all(item.resource_id!='new-ticket' for item in view.members)


def test_history_budget_counts_utf8_bytes_instead_of_characters(source):
    root,path,_,config,reference,scope=source
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO _jj_rows VALUES(?,?,?,?,?,?,?,?,?,?)',(1,'tickets','ticket1','owner','UPDATE',scope.request_nonce,'tx','{}','汉'*100,0))
    config.max_response_bytes=512
    with pytest.raises(SourceReadError,match='SQLITE_CAPTURE_LIMIT'):
        reader.read_sqlite_source(root,reference,config,'ticket1',scope=scope,verified_subject='member')
