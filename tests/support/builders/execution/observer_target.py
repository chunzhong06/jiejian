# 所属业务域的共享测试构造器；不导入测试用例。
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest

@pytest.fixture
def observer_target():
    state = {"subject_id": "subject-1", "workflow_state": "DRAFT", "value": "before"}
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.path, self.headers.get("X-Jiejian-Case-ID")))
            payload = {"subject_id": state["subject_id"]} if self.path == "/identity" else dict(
                resource_id="resource-1", workflow_state=state["workflow_state"], value=state["value"])
            raw = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def log_message(self, *_args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port, state, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()
