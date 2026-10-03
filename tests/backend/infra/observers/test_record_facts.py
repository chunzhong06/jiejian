# 通用状态证明必须覆盖完整事务链，并拒绝错人、错资源、并发版本和伪造结束记录。

import pytest

from product.backend.infra.observers.records.record_facts import transaction_fact
from product.backend.infra.observers.records.transaction_store import TransactionRecordStore
from product.protocols.runtime.transaction_records import RecordSeed, RecordChange, RecordTransaction


def example(tmp_path, changes):
    store = TransactionRecordStore(tmp_path/'state.journal')
    before = store.seed(RecordSeed(collection='objects',resource_id='unit-1',owner_id='principal-1',data={'phase':'initial'}))
    result = store.transact(RecordTransaction(collection='objects',resource_id='unit-1',subject_id='principal-2',
        request_key='request-1',expected_version=0,changes=tuple(RecordChange(path=('phase',),value=value) for value in changes)))
    after = store.proof_view('objects','unit-1',result.operation_id)
    store.close()
    return before, after


def evaluate(before, after, **changes):
    values = dict(path=('phase',),expected_state='protected',request_key='request-1',subject_id='principal-2',
        resource_id='unit-1',owner_id='principal-1',collection='objects')
    return transaction_fact(before,after,**(values|changes))


@pytest.mark.parametrize('changes,expected', [((), 'ABSENT'), (('protected',),'CONFIRMED'), (('protected','initial'),'CONFIRMED')])
def test_complete_transaction_retains_intermediate_occurrence(tmp_path,changes,expected):
    before, after = example(tmp_path,changes)
    assert evaluate(before,after).state == expected
    assert evaluate(before,after).closure == 'CLOSED'


@pytest.mark.parametrize('field,value', [('request_key','other'),('subject_id','other'),('resource_id','other'),('owner_id','other'),('collection','other')])
def test_unrelated_operation_never_proves_absence(tmp_path,field,value):
    before, after = example(tmp_path,())
    assert evaluate(before,after,**{field:value}).state == 'UNKNOWN'


def test_missing_transition_and_concurrent_write_cannot_close_observation(tmp_path):
    before, after = example(tmp_path,('protected','initial'))
    changed = after.model_copy(update={'operation':after.operation.model_copy(update={'transitions':after.operation.transitions[1:]})})
    assert evaluate(before,changed).state == 'UNKNOWN'
    changed = after.model_copy(update={'snapshot':after.snapshot.model_copy(update={'version':2})})
    assert evaluate(before,changed).state == 'UNKNOWN'
    changed = after.model_copy(update={'snapshot':after.snapshot.model_copy(update={'generation':'another-generation'})})
    assert evaluate(before,changed).reason_codes == ('HISTORY_GENERATION_CHANGED',)
