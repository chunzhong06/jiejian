# 验证只读投影在单次请求内复用，并在请求结束、异常或显式事务处重新读取。
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from product.backend.application.reading import projected_once, projection_read
from product.backend.application.preparation.selection import preparation_recommendation
from product.backend.application.preparation.bindings.service import PreparationBindingService


def test_projection_reuses_exact_input_and_returns_independent_values():
    owner=object()
    read=Mock(return_value={'items':[1]})

    @projection_read
    def view():
        first=projected_once(owner,'project-a',read)
        first['items'].append(2)
        assert projected_once(owner,'project-a',read)=={'items':[1]}
        assert projected_once(owner,'project-b',read)=={'items':[1]}
        assert projected_once(object(),'project-a',read)=={'items':[1]}

    view()
    assert read.call_count==3
    view()
    assert read.call_count==6
    projected_once(owner,'project-a',read)
    projected_once(owner,'project-a',read)
    assert read.call_count==8


def test_nested_projection_shares_scope_and_exception_releases_it():
    owner=object()
    read=Mock(return_value=1)

    @projection_read
    def nested():return projected_once(owner,'a',read)

    @projection_read
    def failed():
        assert nested()==projected_once(owner,'a',read)
        raise ValueError('read failed')

    with pytest.raises(ValueError):failed()
    assert read.call_count==1
    nested()
    assert read.call_count==2


def test_explicit_transaction_bypasses_projection_reuse():
    service=PreparationBindingService.__new__(PreparationBindingService)
    service._inspect=Mock(return_value='fresh facts')
    transaction=object()

    @projection_read
    def view():
        service.inspect(None,None,None,work=transaction)
        service.inspect(None,None,None,work=transaction)

    view()
    assert service._inspect.call_count==2
    service._inspect.assert_called_with(None,None,None,work=transaction)


def action(identity='SATISFIED',execution='SATISFIED',evidence='SATISFIED',complete=False):
    item=lambda status:SimpleNamespace(status=status)
    return SimpleNamespace(action_id='download',preparation_complete=complete,
        identity_requirements=SimpleNamespace(slots=(item(identity),)),execution=item(execution),
        resources=(),effect_evidence=(item(evidence),),recovery=item('NOT_REQUIRED'))


@pytest.mark.parametrize('values,expected',[
    ({'identity':'NEEDS_USER','execution':'STALE'},'identity'),
    ({'execution':'STALE'},'execution'),
    ({'evidence':'BLOCKED'},'evidence'),
    ({'complete':True},None),
])
def test_recommendation_selects_first_gap_without_assigning_a_verdict(values,expected):
    assert preparation_recommendation((action(**values),))==('download',expected)
    assert preparation_recommendation(())==(None,None)
