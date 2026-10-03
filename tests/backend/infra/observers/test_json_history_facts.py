# 验证真实发生历史必须对应本次操作；身份、资源、版本、完成与响应结构不完整时不能证明未发生。
import json
from types import SimpleNamespace
import pytest
from product.backend.infra.observers.adapters.json_source import mapped_values, project_history, SourceReadError


def _records():
    before = dict(resource_id='alpha', owner_id='alice', state='draft', version=4,
        effect_count=2, history_generation='generation-1')
    after = dict(before, version=5, operation_id='request-5', operation_resource_id='alpha',
        operation_subject_id='bob', operation_before_version=4, operation_after_version=5,
        operation_state='completed', unfinished_effects=0)
    return before, after


@pytest.mark.parametrize('change', [
    {'resource_id':'beta'}, {'owner_id':'bob'}, {'operation_id':'other-request'},
    {'operation_resource_id':'beta'}, {'operation_subject_id':'alice'},
    {'operation_before_version':3}, {'operation_after_version':6},
    {'history_generation':'recreated'}, {'effect_count':1},
    {'operation_state':'pending'}, {'unfinished_effects':1},
])
def test_unmatched_or_unfinished_history_never_proves_absence(change):
    before, after = _records()
    fact = project_history(before, after | change, operation_id='request-5',
        subject_id='bob', resource_id='alpha', owner_id='alice')
    assert (fact.state, fact.closure) == ('UNKNOWN', 'OPEN')


def test_missing_response_operation_id_never_borrows_nearby_resource_history():
    before, after = _records()
    assert project_history(before, after, operation_id=None, subject_id='bob',
        resource_id='alpha', owner_id='alice').state == 'UNKNOWN'


@pytest.mark.parametrize('change', [{'version':True}, {'effect_count':'2'}, {'unfinished_effects':-1}])
def test_history_numeric_fields_do_not_coerce_bools_strings_or_negative_counts(change):
    _, record = _records()
    config = SimpleNamespace(source_contract_id='SYNC_RESOURCE_HISTORY_V1',
        mappings={key:(key,) for key in record},max_response_bytes=4096)
    with pytest.raises(SourceReadError, match='MAPPING_TYPE_INVALID'):
        mapped_values(json.dumps(record | change).encode(),config)


@pytest.mark.parametrize('kind', ['paged','truncated'])
def test_partial_transport_or_paginated_record_list_is_not_a_complete_resource_history(kind):
    _, record = _records()
    config = SimpleNamespace(source_contract_id='SYNC_RESOURCE_HISTORY_V1',
        mappings={key:(key,) for key in record},max_response_bytes=4096)
    raw = json.dumps({'items':[record],'next_page':'more'}).encode() if kind=='paged' else json.dumps(record).encode()[:-5]
    with pytest.raises(SourceReadError):mapped_values(raw,config)
