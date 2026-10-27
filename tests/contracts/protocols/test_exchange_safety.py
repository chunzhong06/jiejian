# 交换格式按独立根和固定身份验证，未知字段与篡改指纹不能进入执行快照。
import pytest
from pydantic import ValidationError
from product.protocols.checks.execution_request import content_hash
from tests.support.facts import decision


def test_fingerprint_is_order_independent_and_domain_separated():
    assert content_hash('Permission',{'a':1,'b':2})==content_hash('Permission',{'b':2,'a':1})
    assert content_hash('Permission',{'a':1})!=content_hash('Source',{'a':1})

def test_snapshot_rejects_extra_sensitive_field_without_echoing_value():
    case=decision().case
    payload={**case.model_dump(),'password':'synthetic-private-value'}
    with pytest.raises(ValidationError) as captured:type(case)(**payload)
    assert 'synthetic-private-value' not in str(captured.value)

def test_proof_fingerprint_cannot_be_substituted():
    proof=decision().case.proof_requirements[0]
    with pytest.raises(ValidationError):type(proof)(**{**proof.model_dump(),'proof_fingerprint':'0'*64})
