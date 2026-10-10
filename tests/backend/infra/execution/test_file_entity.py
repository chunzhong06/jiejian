# 文件接收使用实际解码字节；正式检查不解析或带出正文，不因拒绝状态丢掉完整接收事实。
import gzip
import hashlib
import httpx
import pytest
from product.backend.infra.execution.web.adapter import HttpExecutionAdapter
from product.backend.infra.execution.web.file_entity import FileEntityPolicy
from product.protocols.web.request import HttpRequestTemplate
from product.protocols.web.target import WebTargetScope


def receive(body,status=200,*,headers=None,capture=None,maximum=1024,known=()):
    scope=WebTargetScope(base_url='http://127.0.0.1:19800',allowed_origins=('http://127.0.0.1:19800',),
        allowed_hosts=('127.0.0.1',),allowed_ports=(19800,),allow_private_network=True,max_response_bytes=maximum)
    adapter=HttpExecutionAdapter(scope,known_secrets=known)
    adapter.client.close()
    adapter.client=httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(status,content=body,headers=headers,request=request)))
    try:
        return adapter.execute_detailed(HttpRequestTemplate(method='GET',path='/download'),case_id='case-file',
            action_id='action-file',entity_policy=FileEntityPolicy(max_bytes=maximum,private_capture=capture))[1]
    finally:adapter.close()


@pytest.mark.parametrize('status',[200,403])
def test_actual_entity_digest_ignores_status_and_claimed_headers(status):
    body=b'controlled-test-artifact'
    response=receive(body,status,headers={'Content-Length':'9999','X-Sha256':'false'})
    receipt=response.entity_receipt
    assert receipt.complete and receipt.actual_size==len(body) and receipt.actual_sha256==hashlib.sha256(body).hexdigest()
    assert response.body==b'' and response.data=={} and response.headers=={}


def test_transfer_decoding_and_only_explicit_capture_retains_private_bytes():
    raw=b'fixed test content'*30
    captured=[]
    response=receive(gzip.compress(raw),headers={'Content-Encoding':'gzip'},capture=captured.append)
    assert captured==[raw] and response.entity_receipt.actual_sha256==hashlib.sha256(raw).hexdigest()
    assert response.body==b''


@pytest.mark.parametrize('body,status,reason',[(b'',200,'FILE_RESPONSE_EMPTY'),(b'x',206,'FILE_RESPONSE_PARTIAL_OR_REDIRECT'),
    (b'x',302,'FILE_RESPONSE_PARTIAL_OR_REDIRECT'),(b'x'*1025,200,'FILE_RESPONSE_TOO_LARGE')])
def test_incomplete_or_unsupported_response_never_becomes_candidate(body,status,reason):
    captured=[]
    receipt=receive(body,status,capture=captured.append).entity_receipt
    assert not receipt.complete and receipt.reason_codes==(reason,) and not captured


def test_only_bounded_json_rejection_proves_refusal_and_secrets_are_not_saved():
    assert receive(b'{"error":"denied"}',403).entity_receipt.refused
    assert not receive(b'{"error":"denied","content":"private"}',403).entity_receipt.refused
    assert not receive(b'not available',403).entity_receipt.refused
    captured=[]
    receipt=receive(b'embedded session-value',capture=captured.append,known=('session-value',)).entity_receipt
    assert not receipt.complete and receipt.reason_codes==('FILE_RESPONSE_SENSITIVE',) and captured==[]
