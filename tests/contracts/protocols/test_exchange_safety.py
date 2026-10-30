# 交换格式按独立根和固定身份验证，未知字段与篡改指纹不能进入执行快照。
import pytest
from pydantic import ValidationError
from product.protocols.checks.execution_request import content_hash
from product.protocols.codec import decode_document, decode_json, encode_json
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


@pytest.mark.parametrize('raw', [
    b'{"a":1,"a":2}', b'{"nested":{"a":1,"a":2}}',
    b'{"a":1,"\\u0061":2}', b'{"value":NaN}', b'{"value":Infinity}',
    b'{"value":-Infinity}', b'{"value":1e400}', b'[]', b'null',
    b'\xef\xbb\xbf{}', b'{"value":"\xff"}', b'{"private":',
])
def test_shared_json_reader_rejects_ambiguous_or_invalid_wire_without_echo(raw):
    with pytest.raises(ValueError) as captured:
        decode_json(raw)
    assert 'private' not in str(captured.value)


def test_json_budget_counts_utf8_bytes_and_canonical_roots_keep_their_identity():
    raw = '{"name":"界鉴"}'.encode('utf-8')
    assert decode_json(raw, limit=len(raw)) == {'name': '界鉴'}
    with pytest.raises(ValueError):
        decode_json(raw, limit=len(raw) - 1)
    value = {'document_type': 'test.root', 'schema_version': '1', 'nested': {'n': 1.25}}
    canonical = encode_json(value)
    assert decode_document(canonical, document_type='test.root', version='1', limit=len(canonical)) == value
    for wire, kind, version in [(b' ' + canonical, 'test.root', '1'),
                                (canonical, 'other.root', '1'), (canonical, 'test.root', '2')]:
        with pytest.raises(ValueError):
            decode_document(wire, document_type=kind, version=version, limit=len(wire))
