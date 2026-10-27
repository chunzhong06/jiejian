# 文件录制仍走真实浏览器；覆盖正文不入存档、默认登录边界及传输限制。
import hashlib
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from product.backend.infrastructure.recording.browser import BrowserRecordingAdapter
from product.backend.infrastructure.recording.transport import BoundedRouteTransport
from product.protocols.recording.events import RecordingEventKind, RecordingRunnerResultType, canonical_recording_json_bytes
from tests.support.builders.preparation.recording import COOKIE_ENV_NAME, TEST_IDENTITY_ID, recording_request

PAYLOAD = b"PK\x03\x04private-test-file-body\x00\xff"


@contextmanager
def file_server():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path == '/files/campus':
                body, media = PAYLOAD, 'application/zip'
            else:
                body, media = b'<button id="get" onclick="fetch(\'/files/campus\').then(r=>r.blob()).then(b=>window.received=b.size)">download</button>', 'text/html'
            self.send_response(200)
            self.send_header('Content-Type', media)
            self.send_header('Content-Length', str(len(body)))
            if self.path == '/files/campus':
                self.send_header('Content-Disposition', 'attachment; filename="test.zip"')
            self.end_headers()
            self.wfile.write(body)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_login_transport_remains_closed_to_files_and_recording_keeps_limits():
    request = recording_request(8765)
    headers = {'content-type': 'application/zip', 'content-disposition': 'attachment', 'content-length': '32'}
    assert BoundedRouteTransport(request.target_scope)._unsupported_reason('GET', headers) == 'DOWNLOAD_UNSUPPORTED'
    transport = BoundedRouteTransport(request.target_scope, allow_files=True)
    assert transport._unsupported_reason('GET', headers) is None
    assert transport._unsupported_reason('GET', {**headers, 'content-length': str(request.target_scope.max_response_bytes + 1)}) == 'CONTENT_LENGTH_EXCEEDED'
    assert transport._unsupported_reason('GET', {**headers, 'content-encoding': 'gzip'}) == 'ENCODING_UNSUPPORTED'
    assert transport._unsupported_reason('GET', {**headers, 'transfer-encoding': 'chunked'}) == 'STREAMING_UNSUPPORTED'


@pytest.mark.browser
@pytest.mark.slow
def test_real_file_fetch_records_one_response_without_binary_or_secret():
    observed = {}
    sentinel = 'private-session-sentinel'
    with file_server() as server:
        request = recording_request(server.server_port)
        def interact(session):
            page = session.new_page(TEST_IDENTITY_ID)
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            page.click('#get')
            for _ in range(30):
                page.wait_for_timeout(100)
                if page.evaluate('window.received || 0'):
                    break
            observed['size'] = page.evaluate('window.received || 0')
        result = BrowserRecordingAdapter().run(request, interact, known_secrets=(sentinel,), secret_values={COOKIE_ENV_NAME: sentinel})
    assert result.result_type is RecordingRunnerResultType.CAPTURED
    assert observed['size'] == len(PAYLOAD)
    files = [e for e in result.events if e.kind is RecordingEventKind.RESPONSE and e.url and e.url.endswith('/files/campus')]
    assert len(files) == 1 and files[0].body is None and not files[0].truncated
    assert hashlib.sha256(PAYLOAD).hexdigest() in files[0].message
    wire = canonical_recording_json_bytes(result, known_secrets=(sentinel,))
    assert b'private-test-file-body' not in wire and sentinel.encode() not in wire

pytestmark = [pytest.mark.level4]
