# 验证通用同步记录的原子性、完整历史和幂等；不依赖任何本地业务应用。
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

import pytest

from product.backend.infrastructure.observers.records.transaction_store import RecordStoreError, TransactionRecordStore
from product.protocols.runtime.transaction_records import RecordChange, RecordSeed, RecordTransaction


def store(tmp_path: Path):
    value = TransactionRecordStore(tmp_path / "records" / "business.sqlite")
    value.seed(RecordSeed(collection="records", resource_id="item-1", owner_id="person-1", data={"state": "initial", "nested": {"flag": False}}))
    return value


def command(**changes):
    return RecordTransaction(collection="records", resource_id="item-1", subject_id="person-2", request_key="request-1",
        expected_version=0, changes=(RecordChange(path=("state",), value="changed"),), **changes)


def test_trace_requires_own_request_parent_and_committed_operation(tmp_path):
    from product.protocols.runtime.record_trace import RecordTraceInput, RecordTraceWrite
    value=store(tmp_path)
    first=value.open_scope('a'*64,'b'*64)
    second=value.open_scope('c'*64,'d'*64)
    def append(scope,kind='ENTRY',parent=None,operation=None):
        return value.append_trace(RecordTraceWrite(scope_id=scope.scope_id,collection='records',resource_id='item-1',
            event=RecordTraceInput(kind=kind,semantic_key='test_event',parent_event_id=parent,operation_id=operation,
                subject_id='person-2',source_component='ordinary_app',source_location='handler')))
    entry=append(first)
    with pytest.raises(ValueError,match='trace parent'):
        append(second,'IDENTITY',entry.event_id)
    second_entry=append(second)
    operation=value.transact(command(scope_id=first.scope_id))
    with pytest.raises(RecordStoreError,match='TRACE_OPERATION_MISMATCH'):
        append(second,'PERSISTENT_EFFECT',second_entry.event_id,operation.operation_id)
    committed=append(first,'PERSISTENT_EFFECT',entry.event_id,operation.operation_id)
    value.close_scope(first.scope_id,True)
    with pytest.raises(RecordStoreError,match='RECORD_SCOPE_CLOSED'):
        append(first,'IDENTITY',committed.event_id)
    value.close()
    restored=TransactionRecordStore(value.database)
    try:
        log=restored.trace_view('records','item-1',first.request_nonce)
        assert log.scope_state=='COMPLETE' and log.request_digest==first.request_digest
        assert [item.event_id for item in log.events]==[entry.event_id,committed.event_id]
        assert log.events[-1].operation_id==operation.operation_id
        empty=restored.open_scope('e'*64,'f'*64)
        restored.close_scope(empty.scope_id,True)
        assert not restored.trace_view('records','item-1',empty.request_nonce).events
    finally:restored.close()


def test_occurrence_history_survives_restoring_final_state_and_restart(tmp_path):
    value = store(tmp_path)
    operation = value.transact(command().model_copy(update={"changes": (
        RecordChange(path=("state",), value="changed"), RecordChange(path=("state",), value="initial"),
    )}))
    assert [item.after["state"] for item in operation.transitions] == ["changed", "initial"]
    value.close()
    reopened = TransactionRecordStore(value.database)
    assert reopened.read("records", "item-1").data["state"] == "initial"
    assert reopened.operation(operation.operation_id) == operation
    assert operation.before_version == 0 and operation.after_version == 1 and operation.state == "COMMITTED"
    reopened.close()


def test_same_request_replays_once_and_different_request_content_is_rejected(tmp_path):
    value = store(tmp_path)
    request = command()
    first = value.transact(request)
    assert value.transact(request) == first
    assert value.read("records", "item-1").version == 1
    with pytest.raises(RecordStoreError, match="RECORD_OPERATION_CONFLICT"):
        value.transact(request.model_copy(update={"subject_id": "someone-else"}))


def test_invalid_later_step_rolls_back_data_and_operation_receipt(tmp_path):
    value = store(tmp_path)
    request = command().model_copy(update={"changes": (RecordChange(path=("state",), value="changed"), RecordChange(path=("missing", "value"), value=1))})
    with pytest.raises(RecordStoreError, match="RECORD_FIELD_UNAVAILABLE"):
        value.transact(request)
    assert value.read("records", "item-1").version == 0
    assert value.read("records", "item-1").data["state"] == "initial"
    assert value.transact(command()).before_version == 0


def test_unchanged_transaction_still_has_completed_operation_and_no_changes(tmp_path):
    value = store(tmp_path)
    operation = value.transact(command().model_copy(update={"changes": ()}))
    assert operation.transitions == () and operation.state == "COMMITTED"
    assert value.read("records", "item-1").last_operation_id == operation.operation_id


def test_seed_cannot_reset_history_or_transfer_ownership(tmp_path):
    value = store(tmp_path)
    operation = value.transact(command())
    snapshot = value.seed(RecordSeed(collection="records", resource_id="item-1", owner_id="person-1", data={"state": "initial"}))
    assert snapshot.version == 1 and snapshot.data["state"] == "changed"
    assert value.operation(operation.operation_id) == operation
    with pytest.raises(RecordStoreError, match="RECORD_OWNER_CONFLICT"):
        value.seed(RecordSeed(collection="records", resource_id="item-1", owner_id="person-2", data={}))


def test_concurrent_writers_cannot_both_claim_same_base_version(tmp_path):
    value = store(tmp_path)
    def submit(key):
        try:
            return value.transact(command().model_copy(update={"request_key": key})).state
        except RecordStoreError as error:
            return str(error)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(submit, ["request-a", "request-b"]))
    assert outcomes == ["COMMITTED", "RECORD_VERSION_CONFLICT"]
    assert value.read("records", "item-1").version == 1


def test_open_record_file_cannot_be_reopened_or_overwritten(tmp_path):
    value = store(tmp_path)
    with pytest.raises(OSError):
        value.database.write_bytes(b'not permitted')
    with pytest.raises(OSError):
        TransactionRecordStore(value.database)
    assert value.read('records', 'item-1').version == 0


def test_damaged_history_is_not_silently_reset(tmp_path):
    value = store(tmp_path)
    value.transact(command())
    value.close()
    with value.database.open('ab') as stream:
        stream.write(b'partial')
    with pytest.raises(RecordStoreError, match='RECORD_HISTORY_'):
        TransactionRecordStore(value.database)


def test_closed_request_cannot_be_reopened_or_receive_later_writes(tmp_path):
    value=store(tmp_path)
    scope=value.open_scope('a'*64,'b'*64)
    value.transact(command(scope_id=scope.scope_id))
    value.close_scope(scope.scope_id,True)
    with pytest.raises(RecordStoreError,match='RECORD_SCOPE_CLOSED'):
        value.transact(command(scope_id=scope.scope_id).model_copy(update={'request_key':'late','expected_version':1}))
    with pytest.raises(RecordStoreError,match='RECORD_REQUEST_REPLAYED'):
        value.open_scope('a'*64,'c'*64)
    value.close()
    restored=TransactionRecordStore(value.database)
    view=restored.proof_view('records','item-1',request_nonce='a'*64)
    assert view.scope.state=='COMPLETE' and len(view.operations)==1
    restored.close()


def test_request_ordinal_is_independent_of_internal_steps_and_closed_receipt_survives(tmp_path):
    value=store(tmp_path)
    try:
        scope=value.open_scope('a'*64,'b'*64)
        requests=[]
        for index in range(32):
            changes=tuple(RecordChange(path=('nested','flag'),value=bool(step%2)) for step in range(index%9))
            request=command(scope_id=scope.scope_id).model_copy(update={'request_key':f'request-{index}',
                'expected_version':index,'changes':changes})
            operation=value.transact(request);requests.append(request)
            assert operation.scope_ordinal==index and operation.commit_semantics=='ATOMIC_COMMIT'
        with pytest.raises(RecordStoreError,match='RECORD_REQUEST_LIMIT'):
            value.transact(requests[-1].model_copy(update={'request_key':'over-limit','expected_version':32}))
        value.close_scope(scope.scope_id,True)
        assert value.transact(requests[0]).scope_ordinal==0
        with pytest.raises(RecordStoreError,match='RECORD_OPERATION_CONFLICT'):
            value.transact(requests[0].model_copy(update={'subject_id':'different-person'}))
        view=value.proof_view('records','item-1',request_nonce='a'*64)
        assert [item.scope_ordinal for item in view.operations]==list(range(32))
        assert value.read('records','item-1').version==32
    finally:value.close()


@pytest.mark.parametrize("payload", [{"token": "not-a-real-token"}, {"a": float("nan")}, {"a": "x" * 9000}])
def test_credential_fields_and_unbounded_values_are_rejected(payload):
    with pytest.raises(ValueError):
        RecordSeed(collection="records", resource_id="item-1", owner_id="person-1", data=payload)

pytestmark = [pytest.mark.level3]


def test_incremental_history_limits_writes_and_preserves_operations_after_checkpoints(tmp_path):
    value = store(tmp_path)
    for index in range(24):
        value.seed(RecordSeed(collection='large', resource_id=f'item-{index}', owner_id='person-1', data={'text':'x'*5000}))
    before = value._file.tell()
    snapshots = 0
    operations = []
    for index in range(80):
        operations.append(value.transact(command().model_copy(update={
            'request_key':f'change-{index}', 'expected_version':index})))
        snapshots += len(value._db.serialize())
    written = value._file.tell() - before
    assert written < snapshots // 3
    value.close()
    with closing(TransactionRecordStore(value.database)) as reopened:
        assert reopened.read('records', 'item-1').version == 80
        assert [reopened.operation(item.operation_id) for item in operations] == operations


def test_existing_snapshot_history_continues_without_rewriting_its_prefix(tmp_path):
    import hashlib
    import struct
    value = store(tmp_path)
    image = value._db.serialize()
    value.close()
    length = struct.pack('>I', len(image))
    legacy = b'JIEJIAN-TRANSACTION-RECORDS-3\n' + length + image + hashlib.sha256(bytes(32)+length+image).digest()
    value.database.write_bytes(legacy)
    with closing(TransactionRecordStore(value.database)) as reopened:
        operation = reopened.transact(command())
    assert value.database.read_bytes().startswith(legacy)
    with closing(TransactionRecordStore(value.database)) as reopened:
        assert reopened.operation(operation.operation_id) == operation


def test_unconfirmed_persistence_poisoning_prevents_further_reads(tmp_path, monkeypatch):
    import os
    value = store(tmp_path)
    with monkeypatch.context() as scope:
        scope.setattr(os, 'fsync', lambda descriptor: (_ for _ in ()).throw(OSError('interrupted')))
        with pytest.raises(OSError):
            value.transact(command())
    try:
        with pytest.raises(RecordStoreError, match='RECORD_STORE_UNAVAILABLE'):
            value.read('records', 'item-1')
    finally:
        value.close()


@pytest.mark.parametrize('damage', ['size', 'expansion', 'duplicate-page', 'trailing-stream'])
def test_compressed_history_rejects_invalid_payload_even_with_a_matching_chain(tmp_path, damage):
    import hashlib
    import struct
    import zlib
    value = store(tmp_path)
    image = value._db.serialize()
    value.close()
    first = b'JJC1' + struct.pack('>I', len(image)) + zlib.compress(image)
    if damage == 'size':
        payload = b'JJC1' + struct.pack('>I', 2**31) + zlib.compress(image)
    elif damage == 'expansion':
        payload = b'JJC1' + struct.pack('>I', 16) + zlib.compress(b'x'*17)
    elif damage == 'trailing-stream':
        payload = first + zlib.compress(b'extra')
    else:
        page_size = struct.unpack('>H', image[16:18])[0]
        page = struct.pack('>I', 0) + image[:page_size]
        payload = b'JJD1' + zlib.compress(struct.pack('>III', len(image), page_size, 2) + page + page)
    raw, digest = b'JIEJIAN-TRANSACTION-RECORDS-3\n', bytes(32)
    for data in (first, payload):
        length = struct.pack('>I', len(data))
        digest = hashlib.sha256(digest+length+data).digest()
        raw += length + data + digest
    value.database.write_bytes(raw)
    with pytest.raises(RecordStoreError, match='RECORD_HISTORY_'):
        TransactionRecordStore(value.database)
