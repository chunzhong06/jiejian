import hashlib
import os
import secrets
import time

import httpx
import pytest

from product.backend.infrastructure.runtime.process.controlled.node_owned import start_owned_node
from tests.support.builders.runtime.node_runtime import free_port, node_runtime_input


pytestmark = [pytest.mark.level4, pytest.mark.skipif(os.name != 'nt', reason='Windows owned runtime')]

APPLICATION = """
import http from 'node:http';
import {DatabaseSync} from 'node:sqlite';
import fs from 'node:fs';
const db=new DatabaseSync(process.env.JIEJIAN_DATA_DIR+'/app.sqlite');
db.exec('CREATE TABLE counter(value INTEGER); INSERT INTO counter VALUES(0)');
http.createServer((req,res)=>{
  if(req.url==='/abort') return res.destroy();
  if(req.url==='/deny') {res.writeHead(403);return res.end('denied')}
  try {
    if(req.url==='/error') db.prepare('SELECT nonexistent_probe_secret FROM missing').get();
    if(req.url==='/change') db.prepare('UPDATE counter SET value=value+1').run();
    if(req.url==='/many') for(let i=0;i<160;i++) db.prepare('SELECT value FROM counter').get();
    const value=db.prepare('SELECT value FROM counter').get().value;
    fs.writeFileSync(process.env.JIEJIAN_DATA_DIR+'/marker','private_probe_secret');
    const body=JSON.stringify({value});res.setHeader('Content-Type','application/json');res.end(body);
  } catch { res.writeHead(500);res.end('failed') }
}).listen(Number(process.env.PORT),'127.0.0.1');
"""


def test_ordinary_app_is_captured_without_event_code_and_preserves_business(tmp_path):
    port = free_port()
    node, _, request = node_runtime_input(tmp_path, port, script=APPLICATION)
    owned = start_owned_node(tmp_path/'var', request, node, environ=dict(os.environ))
    try:
        captures = {}
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', trust_env=False) as client:
            initial_bytes = owned.record_server.store._file.tell()
            before = client.get('/').json()
            assert owned.record_server.store._file.tell() == initial_bytes
            for route in ('/', '/change', '/', '/deny', '/error', '/many', '/abort'):
                nonce = secrets.token_hex(32)
                try:
                    response = client.get(route, headers={'X-Jiejian-Request-Nonce':nonce})
                except httpx.RemoteProtocolError:
                    assert route == '/abort'
                scope = owned.record_server.store.request_scope(nonce)
                if route == '/abort':
                    deadline = time.monotonic()+2
                    while scope.state == 'OPEN' and time.monotonic()<deadline:
                        time.sleep(.01)
                        scope = owned.record_server.store.request_scope(nonce)
                activity = scope.activity
                assert activity.request_nonce == nonce
                assert activity.request_digest == hashlib.sha256(('GET\n'+route).encode()).hexdigest()
                assert activity.events[0].kind == 'HTTP_SERVER'
                assert all(event.parent_event_id == activity.events[0].event_id for event in activity.events[1:])
                assert 'private_probe_secret' not in activity.model_dump_json()
                assert 'nonexistent_probe_secret' not in activity.model_dump_json()
                assert 'app.sqlite' not in activity.model_dump_json()
                captures[nonce] = activity
                if route == '/':
                    assert response.json()['value'] in (before['value'], before['value']+1)
                    assert {'HTTP_SERVER','SQLITE','FILESYSTEM'} <= {event.kind for event in activity.events}
                if route == '/change':
                    assert response.json()['value'] == before['value']+1
                    assert any(event.operation == 'RUN' for event in activity.events)
                if route == '/deny':
                    assert response.status_code == 403 and not any(event.kind=='SQLITE' for event in activity.events)
                if route == '/error':
                    assert response.status_code == 500 and any(event.kind=='SQLITE' and event.outcome=='ERROR' for event in activity.events)
                if route == '/many':
                    assert activity.dropped_count > 0 and not activity.complete
                if route == '/abort':
                    assert scope.state == 'INCOMPLETE' and not activity.complete
            assert client.get('/').json() == {'value':before['value']+1}
        ids = [event.event_id for capture in captures.values() for event in capture.events]
        assert len(ids) == len(set(ids))
        assert all(capture.events[1].source_location.startswith('app.mjs:') for capture in captures.values() if len(capture.events)>1)
    finally:
        owned.stop()
