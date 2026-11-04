"""独立参照的反例：状态码不替代实体事实，参照变化不证明没有披露。"""
import json
from types import SimpleNamespace as Object
import pytest
from product.backend.infrastructure.observers.checks.http_entity import observe_http_entity


@pytest.mark.parametrize('target,status,after,expectation,expected', [
    ({'id':'order-1','owner_id':'owner','price':120,'note':'private'},403,None,'DENY','CONFIRMED'),
    ({'id':'order-2','owner_id':'owner','price':120,'note':'private'},200,None,'DENY','UNKNOWN'),
    ({'error':'forbidden'},403,None,'DENY','ABSENT'),
    ({'error':'forbidden'},403,{'id':'order-1','owner_id':'owner','price':121,'note':'private'},'DENY','UNKNOWN'),
    ({'id':'order-1','owner_id':'owner','price':120},200,None,'ALLOW','UNKNOWN'),
])
def test_entity_comparison_uses_declared_resource_owner_and_fields(target,status,after,expectation,expected):
    baseline={'id':'order-1','owner_id':'owner','price':120,'note':'private'}
    responses=iter([Object(data=baseline,status_code=200),Object(data=after or baseline,status_code=200)])
    owner=Object(web=Object(request=lambda *a,**k:next(responses),request_marker=lambda case:'request-marker',target_response=lambda case:Object(data=target,status_code=status)),
        bundle=Object(identities=[Object(identity_id='owner-identity',verification=Object(expected_application_subject_id='owner'))]),
        _http_entities={},_disclosure_key=b'private-run-key',clock=lambda:2)
    case=Object(case_id='case-1',resource_id='order-1',resource_owner_test_identity_id='owner-identity',permission=Object(expectation=expectation))
    proof=Object(entity_query=Object(request=None,resource_path='$.id',owner_path='$.owner_id',data_path='$'),
        binding_fingerprint='f'*64,protected_projection=('price','note'))
    common=dict(effect_id='bef_'+'a'*32,proof_fingerprint='f'*64,observer_id='entity-query',level='VERDICT_REQUIRED',window_start_us=1)
    observe_http_entity(owner,case=case,action_id='action',proof=proof,phase='BEFORE',common=common|dict(phase='BEFORE'),source_identity='MATCH',cleanup=False)
    result=observe_http_entity(owner,case=case,action_id='action',proof=proof,phase='AFTER',common=common|dict(phase='AFTER'),source_identity='MATCH',cleanup=False)
    assert result.observation.state == expected
    published=result.observation.model_dump_json()
    assert 'private' not in published and '120' not in published
