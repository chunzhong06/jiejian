"""在真实入口和线程切换处核对失败含义、关联隔离及净化后的诊断。"""
import asyncio
import json
import logging
from io import StringIO

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.interfaces.http.errors import jiejian_error_handler
from product.backend.interfaces.http.mcp.errors import _as_mcp_error, _invoke
from product.backend.infrastructure.runtime.logging import (
    configure_logging, request_log_context, request_trace_id,
)


def test_entity_budget_stops_before_parser_ignores_declared_length_and_keeps_upload_separate(monkeypatch):
    from product.backend.interfaces.http import body as owner
    monkeypatch.setattr(owner, 'API_JSON_LIMIT', 3)
    monkeypatch.setattr(owner, 'SOURCE_JSON_LIMIT', 8)

    async def exercise(path, messages):
        remaining = list(messages); consumed = []; sent = []; accepted = []
        async def receive():
            message = remaining.pop(0); consumed.append(message)
            return message
        async def send(message):
            sent.append(message)
        async def handler(scope, receive, send):
            accepted.append(await Request(scope, receive).body())
        scope = dict(type='http', method='POST', path=path, headers=[(b'content-length', b'1')], state={'trace_id':'bounded'})
        await owner.ApiBodyBudget(handler)(scope, receive, send)
        return consumed, sent, accepted

    chunks = [dict(type='http.request', body=b'ab', more_body=True),
        dict(type='http.request', body=b'cd', more_body=True), dict(type='http.request', body=b'ef', more_body=False)]
    consumed, sent, accepted = asyncio.run(exercise('/api/applications', chunks))
    assert len(consumed) == 2 and not accepted and sent[0]['status'] == 413
    assert json.loads(sent[1]['body'])['error']['code'] == 'REQUEST_TOO_LARGE'
    for path in ('/api/projects/example/api-sources/preview', '/api/projects/example/proof-preparation/reference-inputs'):
        _, _, accepted = asyncio.run(exercise(path, chunks))
        assert accepted == [b'abcdef']
    _, sent, accepted = asyncio.run(exercise('/api/applications', [chunks[0], {'type':'http.disconnect'}]))
    assert not sent and not accepted


def test_mcp_intake_uses_sdk_budget_after_bearer_check(tmp_path):
    from tests.support.builders.control_plane import create_app, TestClient
    from product.backend.interfaces.http.body import MCP_JSON_LIMIT
    app = create_app(tmp_path/'instance', start_worker=False)
    token = app.state.mcp_access.pair().access_token
    with TestClient(app) as client:
        oversized = b' ' * (MCP_JSON_LIMIT + 1)
        headers = {'content-type':'application/json', 'accept':'application/json, text/event-stream'}
        assert client.post('/mcp', content=oversized, headers=headers).status_code == 401
        assert client.post('/mcp', content=oversized, headers=headers | {'authorization':'Bearer '+token}).status_code == 413


def test_small_route_budget_still_stops_before_global_budget():
    from product.backend.interfaces.http.body import ApiBodyBudget, read_bounded_body
    consumed=[]
    async def exercise():
        async def receive():
            consumed.append(1)
            return dict(type='http.request',body=b'x'*4096,more_body=True)
        async def handler(scope, receive, send):
            await read_bounded_body(Request(scope,receive),limit=16384,message='small route')
        async def send(_message):
            pytest.fail('small route error was replaced by global budget')
        with pytest.raises(JiejianError,match='small route'):
            await ApiBodyBudget(handler)(dict(type='http',method='POST',path='/api/small',headers=[]),receive,send)
    asyncio.run(exercise())
    assert len(consumed)==5


def test_ordinary_api_intake_is_bounded_before_framework_validation(tmp_path, monkeypatch):
    from tests.support.builders.control_plane import create_app, TestClient
    from product.backend.interfaces.http import body as owner
    monkeypatch.setattr(owner, 'API_JSON_LIMIT', 32)
    app = create_app(tmp_path/'instance', start_worker=False)
    with TestClient(app) as client:
        response = client.post('/api/applications', content=b' '*33, headers={'content-type':'application/json'})
    assert response.status_code == 413
    assert response.json()['trace_id'] == response.headers['x-trace-id']


@pytest.mark.parametrize('code,status', [
    (ErrorCode.INPUT_INVALID,400), (ErrorCode.STORAGE_FAILURE,500),
    (ErrorCode.STORAGE_STATE,500), (ErrorCode.JOB_REQUEST_CORRUPT,500),
    (ErrorCode.RUNNER_START_FAILED,500), (ErrorCode.RUNNER_PROTOCOL_INVALID,500), (ErrorCode.JOB_REQUEST_CONFLICT,400), (ErrorCode.STORAGE_CONSTRAINT,409),
    (ErrorCode.SECRET_STORE_UNAVAILABLE,503),
    (ErrorCode.JOB_QUEUE_FULL,429),
    (ErrorCode.REQUEST_TOO_LARGE,413),
])
def test_http_and_mcp_keep_failure_identity_and_distinguish_internal_fault(code,status):
    app=FastAPI()
    app.add_exception_handler(JiejianError,jiejian_error_handler)
    @app.get('/failure')
    def failure(request:Request):
        request.state.trace_id='original-request'
        raise JiejianError(code,'保持原说明')
    with TestClient(app) as client:
        response=client.get('/failure')
    assert response.status_code==status
    assert response.json()['error']['code']==code.value
    assert response.json()['trace_id']=='original-request'
    machine=_as_mcp_error(JiejianError(code,'保持原说明'))
    assert machine.data['error_code']==code.value
    if status in (500,503):
        assert '原' in machine.data['recovery']


def test_internal_mcp_validation_enters_product_log_without_invalid_value():
    class Record(BaseModel):
        count:int
    stream=StringIO();configure_logging('ERROR',stream=stream)
    def invalid():
        return Record(count='private-input-must-not-be-logged')
    with pytest.raises(Exception):
        _invoke(invalid)
    payload=json.loads(stream.getvalue())
    assert payload['component'].startswith('jiejian.')
    assert 'validation' in payload['message']
    assert 'private-input' not in stream.getvalue()


def test_request_trace_survives_threadpool_without_cross_request_leak():
    stream=StringIO();configure_logging('INFO',stream=stream,trace_id='default')
    logger=logging.getLogger('jiejian.request.test')
    async def request(identity):
        with request_log_context(identity):
            await asyncio.sleep(0)
            await run_in_threadpool(logger.info,identity)
    async def concurrent():
        await asyncio.gather(request('request-a'),request('request-b'))
    asyncio.run(concurrent());logger.info('after')
    rows=[json.loads(line) for line in stream.getvalue().splitlines()]
    assert {(row['message'],row['trace_id']) for row in rows}=={
        ('request-a','request-a'),('request-b','request-b'),('after','default')}


@pytest.mark.parametrize('supplied',['x'*65,'token=private','中文','line\nbreak',None])
def test_external_trace_is_bounded_and_never_echoes_invalid_input(supplied):
    value=request_trace_id(supplied)
    assert value.startswith('tr_') and len(value)==35
    assert request_trace_id('client-request_1')=='client-request_1'


pytestmark=[pytest.mark.level3]
