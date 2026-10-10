# 冻结旧日志结构验证代际迁移：只保留业务状态及所有者，运行占用或损坏时不覆盖历史。
import hashlib
import json
import sqlite3
import struct

import pytest
from product.backend.infra.observers.records.transaction_store import TransactionRecordStore
from product.backend.infra.runtime.process.exclusive_file import open_exclusive_record_file
from product.protocols.runtime.transaction_records import RecordTransaction,RecordChange


def legacy_file(tmp_path):
    path=tmp_path/'records.journal'
    db=sqlite3.connect(':memory:')
    try:
        db.executescript('''
        CREATE TABLE metadata(singleton INTEGER PRIMARY KEY CHECK(singleton=1),format INTEGER NOT NULL,generation TEXT NOT NULL);
        CREATE TABLE resources(collection TEXT NOT NULL,resource_id TEXT NOT NULL,owner_id TEXT NOT NULL,
            version INTEGER NOT NULL CHECK(version>=0),data TEXT NOT NULL,last_operation_id TEXT,PRIMARY KEY(collection,resource_id));
        CREATE TABLE operations(operation_id TEXT PRIMARY KEY,request_key TEXT NOT NULL UNIQUE,command_hash TEXT NOT NULL,document TEXT NOT NULL);
        CREATE TABLE scopes(scope_id TEXT PRIMARY KEY,request_nonce TEXT UNIQUE NOT NULL,document TEXT NOT NULL);
        CREATE TABLE scope_operations(scope_id TEXT NOT NULL,operation_id TEXT UNIQUE NOT NULL,ordinal INTEGER NOT NULL,PRIMARY KEY(scope_id,ordinal));
        INSERT INTO metadata VALUES(1,1,'original-generation');
        ''')
        operation={'schema_version':'1','operation_id':'old-operation','generation':'original-generation','collection':'objects',
            'resource_id':'one','owner_id':'owner-one','subject_id':'owner-one','request_key':'old-request','scope_id':None,
            'before_version':0,'after_version':1,'state':'COMMITTED','transitions':[{'ordinal':0,'before':{'state':'initial'},'after':{'state':'retained'}}]}
        db.execute('INSERT INTO operations VALUES(?,?,?,?)',('old-operation','old-request','a'*64,json.dumps(operation)))
        db.execute('INSERT INTO resources VALUES(?,?,?,?,?,?)',('objects','one','owner-one',1,'{"state":"retained"}','old-operation'))
        db.commit();raw=db.serialize()
    finally:db.close()
    length=struct.pack('>I',len(raw))
    path.write_bytes(b'JIEJIAN-TRANSACTION-RECORDS-1\n'+length+raw+hashlib.sha256(bytes(32)+length+raw).digest())
    return path


def test_new_generation_keeps_state_and_owner_without_relabeling_old_operations(tmp_path):
    old=legacy_file(tmp_path);original=old.read_bytes();destination=tmp_path/'records-atomic.journal'
    store=TransactionRecordStore(destination,legacy_database=old)
    try:
        snapshot=store.read('objects','one');receipt=store.migration_receipt()
        assert snapshot.data=={'state':'retained'} and snapshot.owner_id=='owner-one'
        assert snapshot.version==0 and snapshot.last_operation_id is None
        assert snapshot.generation!='original-generation'
        assert receipt.resource_count==1 and receipt.source_state_sha256==receipt.target_state_sha256
        assert receipt.target_generation==snapshot.generation
        assert store.proof_view('objects','one').operation is None
        store.transact(RecordTransaction(collection='objects',resource_id='one',subject_id='owner-one',request_key='new-request',
            expected_version=0,changes=(RecordChange(path=('state',),value='new-state'),)))
    finally:store.close()
    reopened=TransactionRecordStore(destination,legacy_database=old)
    try:
        assert reopened.read('objects','one').data=={'state':'new-state'}
        assert reopened.read('objects','one').generation==snapshot.generation
        assert reopened.migration_receipt()==receipt
    finally:reopened.close()
    assert old.read_bytes()==original


def test_running_legacy_owner_blocks_new_loading_without_poisoning_empty_destination(tmp_path):
    old=legacy_file(tmp_path);destination=tmp_path/'records-atomic.journal';original=old.read_bytes()
    with open_exclusive_record_file(old,read_only=True):
        with pytest.raises(OSError):TransactionRecordStore(destination,legacy_database=old)
    assert old.read_bytes()==original and destination.stat().st_size==0
    loaded=TransactionRecordStore(destination,legacy_database=old)
    loaded.close()


def test_truncated_legacy_history_is_not_treated_as_an_empty_application(tmp_path):
    old=legacy_file(tmp_path);truncated=old.read_bytes()[:-1];old.write_bytes(truncated)
    destination=tmp_path/'records-atomic.journal'
    with pytest.raises(ValueError,match='RECORD_HISTORY_INCOMPLETE'):
        TransactionRecordStore(destination,legacy_database=old)
    assert old.read_bytes()==truncated and destination.stat().st_size==0
