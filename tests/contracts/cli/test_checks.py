"""自动执行入口的授权、未知回执与退出语义；不调用受检目标。"""
import json

import httpx
import pytest
from typer.testing import CliRunner

from product.backend.domain.errors import JiejianError
from product.backend.interfaces.cli.app import app
from product.backend.interfaces.cli.check_client import CheckClient, execution_exit
from product.protocols.checks.routine_reference import RoutineReference


ORIGIN = 'http://127.0.0.1:8765'
REFERENCE = RoutineReference(routine_id='csp_'+'a'*32, revision=2, binding_id='crb_'+'b'*32)


def response(data):
    return httpx.Response(200, json={'schema_version':'1', 'data':data})


def test_check_client_gets_current_session_and_never_replays_unknown_write():
    requests, accepted = [], {}

    def server(request):
        requests.append((request.method, request.url.path))
        if request.url.path == '/':
            return httpx.Response(200, headers={'Set-Cookie':'jiejian_control_session=ephemeral; Path=/api; HttpOnly; SameSite=Strict'})
        assert request.headers['origin'] == ORIGIN
        assert request.headers['cookie'] == 'jiejian_control_session=ephemeral'
        if request.method == 'POST':
            accepted.update(json.loads(request.content))
            raise httpx.ReadTimeout('模拟服务已接收后响应丢失', request=request)
        assert request.url.params['binding_id'] == REFERENCE.binding_id
        return response({'run':{'run_id':'run_'+'c'*32}})

    with CheckClient(ORIGIN, transport=httpx.MockTransport(server)) as client:
        with pytest.raises(JiejianError) as error:
            client.run('orders', REFERENCE, 'd'*64, 'e'*32)
        assert error.value.to_dict()['details']['receipt_unknown'] is True
        receipt = client.receipt('orders', REFERENCE, 'd'*64, 'e'*32)
        assert receipt['run']['run_id'] == 'run_'+'c'*32
    assert accepted['routine'] == REFERENCE.model_dump(mode='json')
    assert [method for method, _ in requests] == ['GET', 'POST', 'GET']
    assert not client.http.cookies


@pytest.mark.parametrize('endpoint', ['https://127.0.0.1:8765', 'http://localhost:8765', 'http://127.0.0.1:8765/api',
    'http://127.0.0.1:8765?token=x', 'http://user:secret@127.0.0.1:8765', 'http://example.com:80'])
def test_check_client_rejects_other_origins_before_network(endpoint):
    with pytest.raises(JiejianError) as error:
        CheckClient(endpoint, transport=httpx.MockTransport(lambda _:pytest.fail('不得请求不合法服务地址')))
    assert error.value.code == 'INPUT_INVALID'


def test_redirect_is_not_followed_and_no_session_is_persisted():
    calls = []
    def server(request):
        calls.append(request.url)
        return httpx.Response(302, headers={'Location':'http://example.com/'})
    with pytest.raises(JiejianError) as error:
        with CheckClient(ORIGIN, transport=httpx.MockTransport(server)):
            pytest.fail('未签发会话不能继续')
    assert error.value.code == 'API_CONTROL_REJECTED'
    assert len(calls) == 1


@pytest.mark.parametrize('lifecycle,verdict,integrity,code', [('QUEUED',None,'NOT_PUBLISHED',6),
    ('COMPLETED','PASS','VALID',0), ('COMPLETED','BLOCK','VALID',10), ('COMPLETED','INCONCLUSIVE','VALID',11),
    ('COMPLETED','PASS','INVALID',4), ('FAILED',None,'NOT_PUBLISHED',4), ('CANCELLED',None,'NOT_PUBLISHED',130)])
def test_checks_exit_code_separates_lifecycle_verdict_and_publication(lifecycle, verdict, integrity, code):
    assert execution_exit({'run':{'lifecycle':lifecycle,'verdict':verdict},'result_integrity':integrity}) == code


def test_wait_timeout_does_not_cancel_or_resubmit():
    reads=[]
    def server(request):
        reads.append(request.method)
        if request.url.path == '/':
            return httpx.Response(200, headers={'Set-Cookie':'jiejian_control_session=ephemeral; Path=/api'})
        return response({'run':{'project_id':'orders','lifecycle':'RUNNING'}})
    with CheckClient(ORIGIN, transport=httpx.MockTransport(server)) as client:
        status, timed_out = client.wait('orders', 'run_'+'c'*32, timeout=0)
    assert timed_out and status['run']['lifecycle'] == 'RUNNING'
    assert reads == ['GET','GET']


def test_cli_rejects_incomplete_plan_before_opening_service(monkeypatch):
    monkeypatch.setattr(CheckClient, '__enter__', lambda _:pytest.fail('无效准确引用不得握手'))
    result=CliRunner().invoke(app, ['--json','check','run','--project','orders','--plan','csp_'+'a'*32,
        '--revision','1','--binding','wrong','--fingerprint','c'*64,'--request-id','d'*32])
    assert result.exit_code == 3
    assert json.loads(result.stdout)['error']['error_code'] == 'INPUT_INVALID'


pytestmark = [pytest.mark.level3]
