# 创建对象从真实浏览器响应进入审阅与 Flow；不把旧编号注入下一次创建请求。
import json
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace

import pytest

from product.backend.infra.recording.browser import BrowserRecordingAdapter
from product.backend.workflows.recording.processing import FlowDraftProcessor
from product.backend.workflows.recording.review import FlowDraftReviewer
from product.backend.workflows.recording.flow_compiler import FlowDraftCompiler
from product.backend.workflows.preparation.bindings.recording_candidates import recorded_resource_value, flow_resource_injection
from product.protocols.recording.flow_draft import ConfirmFlowDraftResource, canonical_flow_draft_json_bytes, parse_flow_draft
from product.protocols.recording.created_resource import response_object_candidates, location_resource
from product.protocols.recording.recording_flow import Flow
from product.protocols import RecordingRunnerResultType
from tests.fixtures.preparation.recording import COOKIE_ENV_NAME, TEST_IDENTITY_ID, recording_request


@contextmanager
def creation_server():
    class Handler(BaseHTTPRequestHandler):
        count = 0
        def log_message(self, *args): pass
        def respond(self, status, body, media):
            self.send_response(status)
            self.send_header('Content-Type', media)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def do_GET(self):
            self.respond(200,b'<button id="create" onclick="fetch(\'/galleries\',{method:\'POST\'}).then(r=>r.json()).then(v=>window.created=v.id)">create</button>','text/html')
        def do_POST(self):
            self.rfile.read(int(self.headers.get('content-length','0')))
            Handler.count += 1
            self.respond(201,json.dumps({'id':f'gallery-{Handler.count}'}).encode(),'application/json')
    server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread = Thread(target=server.serve_forever,daemon=True); thread.start()
    try: yield server
    finally: server.shutdown(); server.server_close(); thread.join()


@pytest.mark.browser
@pytest.mark.slow
def test_creation_response_can_be_confirmed_compiled_and_bound_without_request_id():
    with creation_server() as server:
        request=recording_request(server.server_port)
        def interact(session):
            page=session.new_page(TEST_IDENTITY_ID)
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            page.click('#create')
            page.wait_for_function('window.created === "gallery-1"')
        result=BrowserRecordingAdapter().run(request,interact,secret_values={COOKIE_ENV_NAME:'session-only'})
    assert result.result_type is RecordingRunnerResultType.CAPTURED
    draft=FlowDraftProcessor().build(recording_id=request.recording_id,flow_id='flow-created',
        business_action_id=request.business_action_id,action_revision=request.action_revision,
        subject_test_identity_id=request.subject_test_identity_id,resource_owner_test_identity_id=request.resource_owner_test_identity_id,
        events=result.events,action_path_templates=('POST /galleries',),allow_created_resources=True)
    draft=parse_flow_draft(canonical_flow_draft_json_bytes(draft))
    assert draft.schema_version=='4' and draft.resource_candidate_id is None
    target=next(step for step in draft.steps if step.id==draft.target_step_id)
    candidate=next(c for c in target.resource_candidates if c.consumer=='RESPONSE_JSON')
    confirmed=FlowDraftReviewer().apply(draft,ConfirmFlowDraftResource(operation='CONFIRM_RESOURCE_SLOT',candidate_id=candidate.candidate_id,expected_revision=draft.revision))
    flow=FlowDraftCompiler().compile(confirmed)
    assert Flow.model_validate_json(flow.model_dump_json(),strict=True)==flow
    request_template=next(step for step in flow.steps if step.id==flow.target_step_id).request_template
    assert not request_template.input_slots
    assert request_template.response_extractors[0].json_path=='$.id'
    assert 'gallery-1' not in flow.model_dump_json()
    assert recorded_resource_value(SimpleNamespace(browser_events=result.events),target,candidate)=='gallery-1'
    assert flow_resource_injection(flow,candidate).consumer.value=='RESPONSE_JSON'


def test_created_candidates_keep_ambiguity_and_reject_secret_or_unsafe_identifiers():
    values=response_object_candidates('{"id":"gallery-2","owner_id":"owner-1","token":"s","detail":{"id":false},"bad_id":"../escape"}',[], 'http://127.0.0.1:3000/galleries')
    assert {(kind,path,value) for kind,path,value in values}=={('RESPONSE_JSON','$.id','gallery-2'),('RESPONSE_JSON','$.owner_id','owner-1')}
    assert location_resource('/galleries/gallery-3','http://127.0.0.1:3000/galleries')=='gallery-3'
    assert location_resource('http://example.com/galleries/3','http://127.0.0.1:3000/galleries') is None
    assert location_resource('/galleries/3?token=s','http://127.0.0.1:3000/galleries') is None
