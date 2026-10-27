# 独立记录组件的数据边界：内存事务与独占持久快照形成一次提交，应用没有修改历史的接口。
from __future__ import annotations

import hashlib
import json
from contextlib import closing, contextmanager
from pathlib import Path
import os
import sqlite3
import struct
import time
import zlib
from threading import RLock
from uuid import uuid4

from product.protocols.runtime.transaction_records import RecordOperation, RecordSeed, RecordSnapshot, RecordTransaction, RecordTransition, RecordProofView, RecordRequestScope, bounded_record_data
from product.backend.infrastructure.observers.records.record_history import read_history


_SCHEMA_SQL = r"""
                CREATE TABLE metadata(singleton INTEGER PRIMARY KEY CHECK(singleton=1), format INTEGER NOT NULL, generation TEXT NOT NULL);
                CREATE TABLE resources(collection TEXT NOT NULL, resource_id TEXT NOT NULL, owner_id TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK(version>=0), data TEXT NOT NULL, last_operation_id TEXT,
                    PRIMARY KEY(collection,resource_id));
                CREATE TABLE operations(operation_id TEXT PRIMARY KEY, request_key TEXT NOT NULL UNIQUE,
                    command_hash TEXT NOT NULL, document TEXT NOT NULL);
                CREATE TABLE scopes(scope_id TEXT PRIMARY KEY, request_nonce TEXT UNIQUE NOT NULL,
                    document TEXT NOT NULL);
                CREATE TABLE scope_operations(scope_id TEXT NOT NULL, operation_id TEXT UNIQUE NOT NULL,
                    ordinal INTEGER NOT NULL, PRIMARY KEY(scope_id,ordinal));
                CREATE TABLE execution_traces(scope_id TEXT NOT NULL, collection TEXT NOT NULL,
                    resource_id TEXT NOT NULL, document BLOB NOT NULL, PRIMARY KEY(scope_id,collection,resource_id));
                CREATE TABLE creation_events(sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    collection TEXT NOT NULL, resource_id TEXT NOT NULL, scope_id TEXT, document TEXT NOT NULL);
                CREATE TABLE resource_incarnations(collection TEXT NOT NULL, resource_id TEXT NOT NULL,
                    incarnation TEXT NOT NULL, PRIMARY KEY(collection,resource_id));
                """

def _schema_signature(db):
    return tuple(tuple(row) for row in db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL ORDER BY type,name").fetchall())


class RecordStoreError(ValueError):
    """只暴露稳定原因，不将数据、SQL 或磁盘路径放进异常。"""


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _trace_log(document):
    from product.protocols.runtime.record_trace import RecordTraceLog
    if isinstance(document,bytes):
        decoder=zlib.decompressobj()
        document=decoder.decompress(document,262145)
        if len(document)>262144 or not decoder.eof or decoder.unused_data:
            raise RecordStoreError('TRACE_DOCUMENT_INVALID')
    return RecordTraceLog.model_validate_json(document)


class TransactionRecordStore:
    """由产品拥有的记录进程使用；目标应用只能通过受限业务端口访问，不能取得数据库路径。"""

    def __init__(self, database: Path):
        database = database.absolute()
        if database.resolve() != database or database.is_symlink():
            raise RecordStoreError("RECORD_STORE_PATH_INVALID")
        database.parent.mkdir(parents=True, exist_ok=True)
        self.database = database
        self._lock = RLock()
        self._poisoned = False
        self._last_hash = bytes(32)
        from product.backend.infrastructure.runtime.process.exclusive_file import open_exclusive_record_file
        self._file = open_exclusive_record_file(database)
        fresh_file = os.fstat(self._file.fileno()).st_size == 0
        self._db = sqlite3.connect(':memory:', isolation_level=None, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        try:
            loaded = self._restore()
            if loaded:
                with closing(sqlite3.connect(":memory:")) as reference:
                    reference.executescript(_SCHEMA_SQL)
                    if _schema_signature(self._db) != _schema_signature(reference):
                        raise RecordStoreError("RECORD_STORE_FORMAT_UNSUPPORTED")
                if tuple(self._db.execute("SELECT format FROM metadata WHERE singleton=1").fetchone() or ()) != (3,):
                    raise RecordStoreError("RECORD_STORE_FORMAT_UNSUPPORTED")
            else:
                self._db.executescript(_SCHEMA_SQL)
                self._db.execute("INSERT INTO metadata VALUES(1,3,?)", (uuid4().hex,))
                self._persist()
        except BaseException:
            # 初始化尚未形成持久事实时可重试；写入结果不明的日志保持封闭。
            if fresh_file and not self._poisoned:
                try:self._file.seek(0);self._file.truncate(0);os.fsync(self._file.fileno())
                except OSError:pass
            self.close()
            raise

    def _restore(self):
        """任何截断、摘要不符都拒绝开放，不把损坏尾部当成“没有发生”。"""
        try:latest,self._last_hash=read_history(self._file,3)
        except ValueError as error:raise RecordStoreError(str(error)) from None
        if latest is None:
            self._file.write(b'JIEJIAN-TRANSACTION-RECORDS-3\n')
            return False
        self._db.deserialize(latest)
        return True

    def _persist(self):
        # SQLite 只在拥有者内存中运行。落盘文件始终由 OS 独占，原生 SQLite 也不能绕过文件共享限制。
        # 先持久化完整快照，再允许其他请求读取新状态；写入结果不明时封闭整个来源等待恢复。
        try:
            data = self._db.serialize()
            length = struct.pack('>I', len(data))
            digest = hashlib.sha256(self._last_hash + length + data).digest()
            frame = length + data + digest
            if self._file.tell() + len(frame) > 128 * 1024 * 1024:
                raise RecordStoreError('RECORD_HISTORY_LIMIT')
            offset = 0
            while offset < len(frame):
                written = self._file.write(frame[offset:])
                if not written:
                    raise OSError('record persistence incomplete')
                offset += written
            os.fsync(self._file.fileno())
            self._last_hash = digest
        except BaseException:
            self._poisoned = True
            raise

    def close(self):
        with self._lock:
            self._poisoned = True
            if not self._file.closed:
                self._db.close()
                self._file.close()

    def __del__(self):
        if hasattr(self, '_file') and hasattr(self, '_db') and not self._file.closed:
            self.close()

    @contextmanager
    def _connection(self):
        with self._lock:
            if self._poisoned:
                raise RecordStoreError('RECORD_STORE_UNAVAILABLE')
            yield self._db

    @staticmethod
    def _snapshot(db, collection, resource_id):
        row = db.execute("SELECT * FROM resources WHERE collection=? AND resource_id=?", (collection, resource_id)).fetchone()
        if row is None:
            raise RecordStoreError("RECORD_RESOURCE_MISSING")
        generation = db.execute("SELECT generation FROM metadata WHERE singleton=1").fetchone()[0]
        return RecordSnapshot(generation=generation, collection=collection, resource_id=resource_id,
            owner_id=row["owner_id"], version=row["version"], data=json.loads(row["data"]), last_operation_id=row["last_operation_id"])

    def seed(self, command: RecordSeed) -> RecordSnapshot:
        """只创建尚不存在的资源；重开或重复初始化不覆盖当前数据，也不清空历史。"""
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                scope_id = getattr(command, 'scope_id', None)
                if scope_id is not None:
                    self._open_creation_scope(db, scope_id)
                # 已删除编号不复用，防止旧恢复请求命中新的一次创建；历史现存对象仍可幂等读取。
                exists = db.execute('SELECT 1 FROM resources WHERE collection=? AND resource_id=?',
                    (command.collection, command.resource_id)).fetchone()
                if not exists and db.execute('SELECT 1 FROM creation_events WHERE collection=? AND resource_id=?',
                        (command.collection, command.resource_id)).fetchone():
                    raise RecordStoreError('RECORD_RESOURCE_ID_REUSED')
                inserted = db.execute("INSERT OR IGNORE INTO resources VALUES(?,?,?,?,?,NULL)",
                    (command.collection, command.resource_id, command.owner_id, 0, _json(command.data)))
                current = self._snapshot(db, command.collection, command.resource_id)
                if current.owner_id != command.owner_id:
                    raise RecordStoreError("RECORD_OWNER_CONFLICT")
                if inserted.rowcount:
                    db.execute('INSERT INTO resource_incarnations VALUES(?,?,?)',
                        (command.collection, command.resource_id, uuid4().hex))
                    self._creation_event(db, command.collection, current, scope_id, 'CREATE')
                db.execute("COMMIT")
                if inserted.rowcount:
                    self._persist()
                return current
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    def _open_creation_scope(self, db, scope_id):
        scope = self._scope(db, scope_id)
        if scope.state != 'OPEN':
            raise RecordStoreError('RECORD_SCOPE_CLOSED')
        if db.execute('SELECT COUNT(*) FROM creation_events WHERE scope_id=?', (scope_id,)).fetchone()[0] >= 32:
            raise RecordStoreError('RECORD_REQUEST_LIMIT')

    def _creation_member(self, db, snapshot):
        from product.protocols.runtime.creation_records import CreationMember
        row = db.execute('SELECT incarnation FROM resource_incarnations WHERE collection=? AND resource_id=?',
            (snapshot.collection, snapshot.resource_id)).fetchone()
        # 老对象只有稳定身份，不补造它被创建的时间或请求回执。
        incarnation = row[0] if row else hashlib.sha256(_json(
            [snapshot.generation, snapshot.collection, snapshot.resource_id]).encode()).hexdigest()
        return CreationMember(resource_id=snapshot.resource_id, owner_id=snapshot.owner_id,
            incarnation=incarnation, version=snapshot.version,
            data_digest=hashlib.sha256(_json(snapshot.data).encode()).hexdigest())

    def _creation_event(self, db, collection, snapshot, scope_id, kind):
        from product.protocols.runtime.creation_records import CreationEvent
        cursor = db.execute('INSERT INTO creation_events(collection,resource_id,scope_id,document) VALUES(?,?,?,?)',
            (collection, snapshot.resource_id, scope_id, '{}'))
        event = CreationEvent(sequence=cursor.lastrowid, scope_id=scope_id, kind=kind,
            member=self._creation_member(db, snapshot))
        db.execute('UPDATE creation_events SET document=? WHERE sequence=?', (event.model_dump_json(), event.sequence))

    def remove(self, command):
        """按版本删除单个对象并保留不可变回执；不开放清空集合或删除历史的能力。"""
        with self._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                self._open_creation_scope(db, command.scope_id)
                current = self._snapshot(db, command.collection, command.resource_id)
                if current.version != command.expected_version:
                    raise RecordStoreError('RECORD_VERSION_CONFLICT')
                self._creation_event(db, command.collection, current, command.scope_id, 'REMOVE')
                db.execute('DELETE FROM resources WHERE collection=? AND resource_id=?',
                    (command.collection, command.resource_id))
                db.execute('COMMIT')
                self._persist()
                return current
            except BaseException:
                if db.in_transaction:
                    db.execute('ROLLBACK')
                raise

    def creation_view(self, collection, request_nonce=None):
        """在同一锁内读取完整有限集合和指定请求的创建历史；超限报错，绝不截断为完整。"""
        from product.protocols.runtime.creation_records import CreationView, CreationEvent
        with self._connection() as db:
            if not (db.execute('SELECT 1 FROM resources WHERE collection=?', (collection,)).fetchone()
                    or db.execute('SELECT 1 FROM creation_events WHERE collection=?', (collection,)).fetchone()):
                raise RecordStoreError('CREATION_COLLECTION_UNKNOWN')
            ids = [row[0] for row in db.execute('SELECT resource_id FROM resources WHERE collection=? ORDER BY resource_id LIMIT 257', (collection,))]
            if len(ids) > 256:
                raise RecordStoreError('CREATION_COLLECTION_LIMIT')
            scope, events = None, ()
            if request_nonce is not None:
                row = db.execute('SELECT document FROM scopes WHERE request_nonce=?', (request_nonce,)).fetchone()
                scope = RecordRequestScope.model_validate_json(row[0]) if row else None
                if scope is not None:
                    events = tuple(CreationEvent.model_validate_json(row[0]) for row in db.execute(
                        'SELECT document FROM creation_events WHERE collection=? AND scope_id=? ORDER BY sequence', (collection, scope.scope_id)))
            foreign = False
            for event in events:
                if event.kind == 'CREATE' and db.execute(
                        "SELECT 1 FROM operations WHERE json_extract(document,'$.collection')=? AND json_extract(document,'$.resource_id')=? AND (json_extract(document,'$.scope_id') IS NULL OR json_extract(document,'$.scope_id')<>?) LIMIT 1",
                        (collection, event.member.resource_id, scope.scope_id)).fetchone():
                    foreign = True
            return CreationView(generation=db.execute('SELECT generation FROM metadata WHERE singleton=1').fetchone()[0],
                collection=collection, watermark=db.execute('SELECT COALESCE(MAX(sequence),0) FROM creation_events').fetchone()[0],
                members=tuple(self._creation_member(db, self._snapshot(db, collection, item)) for item in ids),
                scope=scope, events=events, foreign_mutations=foreign)

    def read(self, collection: str, resource_id: str) -> RecordSnapshot:
        with self._connection() as db:
            db.execute("BEGIN")
            try:
                return self._snapshot(db, collection, resource_id)
            finally:
                db.execute("ROLLBACK")

    def operation(self, operation_id: str) -> RecordOperation:
        with self._connection() as db:
            row = db.execute("SELECT document FROM operations WHERE operation_id=?", (operation_id,)).fetchone()
            if row is None:
                raise RecordStoreError("RECORD_OPERATION_MISSING")
            return RecordOperation.model_validate_json(row[0])

    def open_scope(self, request_nonce: str, request_digest: str) -> RecordRequestScope:
        """仅宿主控制端调用；同一随机请求标记不能被重新打开或替换。"""
        with self._connection() as db:
            generation = db.execute('SELECT generation FROM metadata WHERE singleton=1').fetchone()[0]
            scope = RecordRequestScope(scope_id=uuid4().hex, generation=generation,
                request_nonce=request_nonce, request_digest=request_digest)
            if db.execute('SELECT 1 FROM scopes WHERE request_nonce=?', (request_nonce,)).fetchone():
                raise RecordStoreError('RECORD_REQUEST_REPLAYED')
            db.execute('INSERT INTO scopes VALUES(?,?,?)', (scope.scope_id, request_nonce, scope.model_dump_json()))
            self._persist()
            return scope

    def _scope(self, db, scope_id):
        row = db.execute('SELECT document FROM scopes WHERE scope_id=?', (scope_id,)).fetchone()
        if row is None:
            raise RecordStoreError('RECORD_SCOPE_MISSING')
        return RecordRequestScope.model_validate_json(row[0])

    def close_scope(self, scope_id: str, complete: bool) -> RecordRequestScope:
        """完成是单向边界；结束后不允许继续写，未结束写入或异常关闭只能记为不完整。"""
        with self._connection() as db:
            scope = self._scope(db, scope_id)
            if scope.state != 'OPEN':
                return scope
            scope = scope.model_copy(update={'state':'COMPLETE' if complete else 'INCOMPLETE'})
            db.execute('UPDATE scopes SET document=? WHERE scope_id=?', (scope.model_dump_json(), scope_id))
            self._persist()
            return scope

    def append_trace(self, command):
        """宿主绑定当前请求；父节点与提交引用均不得越过同一请求和资源。"""
        from product.protocols.runtime.record_trace import RecordTraceEvent,RecordTraceLog
        with self._connection() as db:
            scope=self._scope(db,command.scope_id)
            if scope.state!='OPEN':raise RecordStoreError('RECORD_SCOPE_CLOSED')
            self._snapshot(db,command.collection,command.resource_id)
            row=db.execute('SELECT document FROM execution_traces WHERE scope_id=? AND collection=? AND resource_id=?',
                (scope.scope_id,command.collection,command.resource_id)).fetchone()
            log=_trace_log(row[0]) if row else RecordTraceLog(scope_id=scope.scope_id,
                generation=scope.generation,request_nonce=scope.request_nonce,request_digest=scope.request_digest,
                collection=command.collection,resource_id=command.resource_id)
            if command.event.operation_id is not None:
                operation=self.operation(command.event.operation_id)
                if (operation.scope_id,operation.collection,operation.resource_id,operation.subject_id)!=(scope.scope_id,command.collection,command.resource_id,command.event.subject_id):
                    raise RecordStoreError('TRACE_OPERATION_MISMATCH')
            event=RecordTraceEvent(**command.event.model_dump(),event_id='event_'+uuid4().hex,recorded_at_us=time.time_ns()//1000)
            log=RecordTraceLog.model_validate(log.model_dump()|{'events':(*log.events,event)})
            db.execute('INSERT OR REPLACE INTO execution_traces VALUES(?,?,?,?)',
                (scope.scope_id,command.collection,command.resource_id,zlib.compress(log.model_dump_json().encode('utf-8'))))
            # 诊断事件在请求闭合时与 scope 一起持久化，避免每个节点复制整个业务快照。
            # 中途崩溃只能恢复 OPEN/部分事件，不能伪装成完整执行链。
            return event

    def trace_view(self, collection, resource_id, request_nonce):
        """只读已写入的事件与当前完成边界，不按业务状态或时间生成事件。"""
        from product.protocols.runtime.record_trace import RecordTraceLog
        with self._connection() as db:
            row=db.execute('SELECT document FROM scopes WHERE request_nonce=?',(request_nonce,)).fetchone()
            if row is None:raise RecordStoreError('RECORD_SCOPE_MISSING')
            scope=RecordRequestScope.model_validate_json(row[0])
            row=db.execute('SELECT document FROM execution_traces WHERE scope_id=? AND collection=? AND resource_id=?',
                (scope.scope_id,collection,resource_id)).fetchone()
            log=_trace_log(row[0]) if row else RecordTraceLog(scope_id=scope.scope_id,
                generation=scope.generation,request_nonce=scope.request_nonce,request_digest=scope.request_digest,
                collection=collection,resource_id=resource_id)
            return log.model_copy(update={'scope_state':scope.state})

    def proof_view(self, collection: str, resource_id: str, operation_id: str | None = None,
                   request_nonce: str | None = None) -> RecordProofView:
        """同一锁内读取资源与对应操作，防止并发写入拼接出并不存在的前后状态。"""
        with self._connection() as db:
            snapshot = self._snapshot(db, collection, resource_id)
            selected = operation_id or snapshot.last_operation_id
            operation = self.operation(selected) if selected is not None else None
            if operation is not None and (operation.collection, operation.resource_id) != (collection, resource_id):
                raise RecordStoreError('RECORD_OPERATION_MISMATCH')
            scope, operations = None, ()
            if request_nonce is not None:
                row = db.execute('SELECT document FROM scopes WHERE request_nonce=?', (request_nonce,)).fetchone()
                scope = RecordRequestScope.model_validate_json(row[0]) if row else None
                if scope is not None:
                    operations = tuple(self.operation(row[0]) for row in db.execute(
                        'SELECT operation_id FROM scope_operations WHERE scope_id=? ORDER BY ordinal', (scope.scope_id,)))
            return RecordProofView(snapshot=snapshot, operation=operation, scope=scope, operations=operations)

    def transact(self, command: RecordTransaction) -> RecordOperation:
        """执行有限同步赋值；同键同文回读，异文或版本竞争拒绝，不调用应用回调或外部服务。"""
        command_hash = hashlib.sha256(_json(command.model_dump(mode="json")).encode()).hexdigest()
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                scope = None
                if command.scope_id is not None:
                    scope = self._scope(db, command.scope_id)
                    if scope.generation != db.execute('SELECT generation FROM metadata WHERE singleton=1').fetchone()[0]:
                        raise RecordStoreError('RECORD_SCOPE_MISMATCH')
                prior = db.execute("SELECT command_hash,document FROM operations WHERE request_key=?", (command.request_key,)).fetchone()
                if prior is not None:
                    if prior["command_hash"] != command_hash:
                        raise RecordStoreError("RECORD_OPERATION_CONFLICT")
                    db.execute("ROLLBACK")
                    return RecordOperation.model_validate_json(prior["document"])
                # 回执不是新写入；相同调用者与scope已由完整command_hash核对，关闭后仍可回读。
                scope_ordinal = None
                if scope is not None:
                    if scope.state != 'OPEN':raise RecordStoreError('RECORD_SCOPE_CLOSED')
                    scope_ordinal = db.execute('SELECT COUNT(*) FROM scope_operations WHERE scope_id=?', (scope.scope_id,)).fetchone()[0]
                    if scope_ordinal >= 32:raise RecordStoreError('RECORD_REQUEST_LIMIT')
                current = self._snapshot(db, command.collection, command.resource_id)
                if current.version != command.expected_version:
                    raise RecordStoreError("RECORD_VERSION_CONFLICT")
                value = current.data
                transitions = []
                for change_ordinal, change in enumerate(command.changes):
                    before = bounded_record_data(value)
                    value = bounded_record_data(value)
                    parent = value
                    for key in change.path[:-1]:
                        if not isinstance(parent.get(key), dict):
                            raise RecordStoreError("RECORD_FIELD_UNAVAILABLE")
                        parent = parent[key]
                    parent[change.path[-1]] = change.value
                    value = bounded_record_data(value)
                    transitions.append(RecordTransition(ordinal=change_ordinal, before=before, after=value))
                operation = RecordOperation(operation_id=uuid4().hex, generation=current.generation,
                    collection=current.collection, resource_id=current.resource_id, owner_id=current.owner_id,
                    subject_id=command.subject_id, request_key=command.request_key, scope_id=command.scope_id, before_version=current.version,
                    after_version=current.version + 1, transitions=tuple(transitions),scope_ordinal=scope_ordinal)
                db.execute("UPDATE resources SET version=?,data=?,last_operation_id=? WHERE collection=? AND resource_id=?",
                    (operation.after_version, _json(value), operation.operation_id, current.collection, current.resource_id))
                db.execute("INSERT INTO operations VALUES(?,?,?,?)",
                    (operation.operation_id, command.request_key, command_hash, operation.model_dump_json()))
                if command.scope_id is not None:
                    db.execute('INSERT INTO scope_operations VALUES(?,?,?)', (command.scope_id, operation.operation_id, scope_ordinal))
                db.execute("COMMIT")
                self._persist()
                return operation
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise
