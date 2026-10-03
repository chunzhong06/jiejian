# 验证通用同步记录的原子性、完整历史和幂等；不依赖任何本地业务应用。
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from product.backend.infra.observers.records.transaction_store import RecordStoreError, TransactionRecordStore
from product.protocols.runtime.transaction_records import RecordChange, RecordSeed, RecordTransaction


def store(tmp_path: Path):
    value = TransactionRecordStore(tmp_path / "records" / "business.sqlite")
    value.seed(RecordSeed(collection="records", resource_id="item-1", owner_id="person-1", data={"state": "initial", "nested": {"flag": False}}))
    return value


def command(**changes):
    return RecordTransaction(collection="records", resource_id="item-1", subject_id="person-2", request_key="request-1",
        expected_version=0, changes=(RecordChange(path=("state",), value="changed"),), **changes)


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


@pytest.mark.parametrize("payload", [{"token": "not-a-real-token"}, {"a": float("nan")}, {"a": "x" * 9000}])
def test_credential_fields_and_unbounded_values_are_rejected(payload):
    with pytest.raises(ValueError):
        RecordSeed(collection="records", resource_id="item-1", owner_id="person-1", data=payload)
