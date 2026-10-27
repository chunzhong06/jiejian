# 验证记录组件完整基线、重开保留和不支持格式的只读拒绝。
import pytest

from product.backend.infrastructure.observers.records.transaction_store import TransactionRecordStore, RecordStoreError
from product.protocols.runtime.transaction_records import RecordSeed

pytestmark = [pytest.mark.level3]


def test_reopen_preserves_current_resources_and_generation(tmp_path):
    path = tmp_path / "records.journal"
    store = TransactionRecordStore(path)
    before = store.seed(RecordSeed(collection="items", resource_id="one", owner_id="owner", data={"state":"kept"}))
    store.close()
    reopened = TransactionRecordStore(path)
    try:
        assert reopened.read("items", "one") == before
    finally:
        reopened.close()


@pytest.mark.parametrize("damage", ["old-format", "extra-table", "missing-table"])
def test_unknown_or_drifted_record_store_is_not_repaired(tmp_path, damage):
    path = tmp_path / "records.journal"
    store = TransactionRecordStore(path)
    if damage != "old-format":
        store._db.execute("CREATE TABLE unexpected(value TEXT)" if damage == "extra-table" else "DROP TABLE resource_incarnations")
        store._persist()
    store.close()
    if damage == "old-format":
        path.write_bytes(path.read_bytes().replace(b"RECORDS-3\n", b"RECORDS-2\n", 1))
    before = path.read_bytes()
    with pytest.raises(RecordStoreError):
        TransactionRecordStore(path)
    assert path.read_bytes() == before
