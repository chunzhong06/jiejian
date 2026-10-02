# 独立记录组件的数据边界：内存事务与独占持久快照形成一次提交，应用没有修改历史的接口。
from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
import os
import sqlite3
import struct
from threading import RLock
from uuid import uuid4

from product.protocols.transaction_records import (
    RecordOperation, RecordSeed, RecordSnapshot, RecordTransaction, RecordTransition, RecordProofView,
    RecordRequestScope, bounded_record_data,
)


class RecordStoreError(ValueError):
    """只暴露稳定原因，不将数据、SQL 或磁盘路径放进异常。"""


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


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
        from product.backend.infra.runtime.process.exclusive_file import open_exclusive_record_file
        self._file = open_exclusive_record_file(database)
        self._db = sqlite3.connect(':memory:', isolation_level=None, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        try:
            loaded = self._restore()
            with self._connection() as db:
                db.executescript("""
                CREATE TABLE IF NOT EXISTS metadata(singleton INTEGER PRIMARY KEY CHECK(singleton=1), format INTEGER NOT NULL, generation TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS resources(collection TEXT NOT NULL, resource_id TEXT NOT NULL, owner_id TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK(version>=0), data TEXT NOT NULL, last_operation_id TEXT,
                    PRIMARY KEY(collection,resource_id));
                CREATE TABLE IF NOT EXISTS operations(operation_id TEXT PRIMARY KEY, request_key TEXT NOT NULL UNIQUE,
                    command_hash TEXT NOT NULL, document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS scopes(scope_id TEXT PRIMARY KEY, request_nonce TEXT UNIQUE NOT NULL,
                    document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS scope_operations(scope_id TEXT NOT NULL, operation_id TEXT UNIQUE NOT NULL,
                    ordinal INTEGER NOT NULL, PRIMARY KEY(scope_id,ordinal));
                """)
                db.execute("INSERT OR IGNORE INTO metadata VALUES(1,1,?)", (uuid4().hex,))
                if db.execute("SELECT format FROM metadata WHERE singleton=1").fetchone()[0] != 1:
                    raise RecordStoreError("RECORD_STORE_FORMAT_UNSUPPORTED")
                if not loaded:
                    self._persist()
        except BaseException:
            self.close()
            raise

    def _restore(self):
        """任何截断、摘要不符都拒绝开放，不把损坏尾部当成“没有发生”。"""
        magic = b'JIEJIAN-TRANSACTION-RECORDS-1\n'
        size = os.fstat(self._file.fileno()).st_size
        if size == 0:
            self._file.write(magic)
            return False
        if size > 128 * 1024 * 1024 or self._file.read(len(magic)) != magic:
            raise RecordStoreError('RECORD_HISTORY_INVALID')
        latest = None
        while self._file.tell() < size:
            length_raw = self._file.read(4)
            if len(length_raw) != 4:
                raise RecordStoreError('RECORD_HISTORY_INCOMPLETE')
            length = struct.unpack('>I', length_raw)[0]
            if not 1 <= length <= 128 * 1024 * 1024:
                raise RecordStoreError('RECORD_HISTORY_INVALID')
            data = self._file.read(length)
            digest = self._file.read(32)
            if len(data) != length or len(digest) != 32 or hashlib.sha256(self._last_hash + length_raw + data).digest() != digest:
                raise RecordStoreError('RECORD_HISTORY_INCOMPLETE')
            self._last_hash, latest = digest, data
        if latest is None:
            raise RecordStoreError('RECORD_HISTORY_INCOMPLETE')
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
                ordinal = 0
                if command.scope_id is not None:
                    scope = self._scope(db, command.scope_id)
                    if scope.state != 'OPEN':
                        raise RecordStoreError('RECORD_SCOPE_CLOSED')
                    ordinal = db.execute('SELECT COUNT(*) FROM scope_operations WHERE scope_id=?', (scope.scope_id,)).fetchone()[0]
                    if ordinal >= 32:
                        raise RecordStoreError('RECORD_REQUEST_LIMIT')
                prior = db.execute("SELECT command_hash,document FROM operations WHERE request_key=?", (command.request_key,)).fetchone()
                if prior is not None:
                    if prior["command_hash"] != command_hash:
                        raise RecordStoreError("RECORD_OPERATION_CONFLICT")
                    db.execute("ROLLBACK")
                    return RecordOperation.model_validate_json(prior["document"])
                current = self._snapshot(db, command.collection, command.resource_id)
                if current.version != command.expected_version:
                    raise RecordStoreError("RECORD_VERSION_CONFLICT")
                value = current.data
                transitions = []
                for ordinal, change in enumerate(command.changes):
                    before = bounded_record_data(value)
                    value = bounded_record_data(value)
                    parent = value
                    for key in change.path[:-1]:
                        if not isinstance(parent.get(key), dict):
                            raise RecordStoreError("RECORD_FIELD_UNAVAILABLE")
                        parent = parent[key]
                    parent[change.path[-1]] = change.value
                    value = bounded_record_data(value)
                    transitions.append(RecordTransition(ordinal=ordinal, before=before, after=value))
                operation = RecordOperation(operation_id=uuid4().hex, generation=current.generation,
                    collection=current.collection, resource_id=current.resource_id, owner_id=current.owner_id,
                    subject_id=command.subject_id, request_key=command.request_key, scope_id=command.scope_id, before_version=current.version,
                    after_version=current.version + 1, transitions=tuple(transitions))
                db.execute("UPDATE resources SET version=?,data=?,last_operation_id=? WHERE collection=? AND resource_id=?",
                    (operation.after_version, _json(value), operation.operation_id, current.collection, current.resource_id))
                db.execute("INSERT INTO operations VALUES(?,?,?,?)",
                    (operation.operation_id, command.request_key, command_hash, operation.model_dump_json()))
                if command.scope_id is not None:
                    db.execute('INSERT INTO scope_operations VALUES(?,?,?)', (command.scope_id, operation.operation_id, ordinal))
                db.execute("COMMIT")
                self._persist()
                return operation
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise
