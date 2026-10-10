# 独立记录组件的数据边界：内存事务与独占持久快照形成一次提交，应用没有修改历史的接口。
from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
import os
import sqlite3
import struct
import time
import zlib
from threading import RLock
from uuid import uuid4

from product.protocols.runtime.transaction_records import RecordOperation, RecordSeed, RecordSnapshot, RecordTransaction, RecordTransition, RecordProofView, RecordRequestScope, RecordStateMigration, bounded_record_data
from product.backend.infra.observers.records.record_history import read_history, import_legacy_state


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

    def __init__(self, database: Path, *, legacy_database: Path | None = None):
        database = database.absolute()
        if database.resolve() != database or database.is_symlink():
            raise RecordStoreError("RECORD_STORE_PATH_INVALID")
        database.parent.mkdir(parents=True, exist_ok=True)
        self.database = database
        self._lock = RLock()
        self._poisoned = False
        self._last_hash = bytes(32)
        from product.backend.infra.runtime.process.exclusive_file import open_exclusive_record_file
        self._file = open_exclusive_record_file(database)
        fresh_file = os.fstat(self._file.fileno()).st_size == 0
        self._db = sqlite3.connect(':memory:', isolation_level=None, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        try:
            loaded = self._restore()
            with self._connection() as db:
                db.executescript("""
                CREATE TABLE IF NOT EXISTS metadata(singleton INTEGER PRIMARY KEY CHECK(singleton=1), format INTEGER NOT NULL, generation TEXT NOT NULL, migration TEXT);
                CREATE TABLE IF NOT EXISTS resources(collection TEXT NOT NULL, resource_id TEXT NOT NULL, owner_id TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK(version>=0), data TEXT NOT NULL, last_operation_id TEXT,
                    PRIMARY KEY(collection,resource_id));
                CREATE TABLE IF NOT EXISTS operations(operation_id TEXT PRIMARY KEY, request_key TEXT NOT NULL UNIQUE,
                    command_hash TEXT NOT NULL, document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS scopes(scope_id TEXT PRIMARY KEY, request_nonce TEXT UNIQUE NOT NULL,
                    document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS scope_operations(scope_id TEXT NOT NULL, operation_id TEXT UNIQUE NOT NULL,
                    ordinal INTEGER NOT NULL, PRIMARY KEY(scope_id,ordinal));
                CREATE TABLE IF NOT EXISTS execution_traces(scope_id TEXT NOT NULL, collection TEXT NOT NULL,
                    resource_id TEXT NOT NULL, document BLOB NOT NULL, PRIMARY KEY(scope_id,collection,resource_id));
                """)
                db.execute("INSERT OR IGNORE INTO metadata VALUES(1,2,?,NULL)", (uuid4().hex,))
                if db.execute("SELECT format FROM metadata WHERE singleton=1").fetchone()[0] != 2:
                    raise RecordStoreError("RECORD_STORE_FORMAT_UNSUPPORTED")
                if not loaded:
                    legacy_exists = False
                    if legacy_database is not None:
                        try:legacy_database.stat();legacy_exists=True
                        except FileNotFoundError:pass
                    if legacy_exists:
                        generation=db.execute('SELECT generation FROM metadata WHERE singleton=1').fetchone()[0]
                        import_legacy_state(legacy_database,db,generation,self._persist)
                    else:self._persist()
        except BaseException:
            # 旧实例占用或旧日志校验失败时，允许稍后重试新空库；持久化结果不明的文件保留待核对。
            if fresh_file and not self._poisoned:
                try:self._file.seek(0);self._file.truncate(0);os.fsync(self._file.fileno())
                except OSError:pass
            self.close()
            raise

    def _restore(self):
        """任何截断、摘要不符都拒绝开放，不把损坏尾部当成“没有发生”。"""
        try:latest,self._last_hash=read_history(self._file,2)
        except ValueError as error:raise RecordStoreError(str(error)) from None
        if latest is None:
            self._file.write(b'JIEJIAN-TRANSACTION-RECORDS-2\n')
            return False
        self._db.deserialize(latest)
        return True

    def migration_receipt(self) -> RecordStateMigration | None:
        with self._connection() as db:
            payload=db.execute('SELECT migration FROM metadata WHERE singleton=1').fetchone()[0]
            return None if payload is None else RecordStateMigration.model_validate_json(payload)

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
                inserted = db.execute("INSERT OR IGNORE INTO resources VALUES(?,?,?,?,?,NULL)",
                    (command.collection, command.resource_id, command.owner_id, 0, _json(command.data)))
                current = self._snapshot(db, command.collection, command.resource_id)
                if current.owner_id != command.owner_id:
                    raise RecordStoreError("RECORD_OWNER_CONFLICT")
                db.execute("COMMIT")
                if inserted.rowcount:
                    self._persist()
                return current
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

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
