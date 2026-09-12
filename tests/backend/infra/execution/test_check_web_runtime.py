# 用真实 loopback HTTP 验证 v3 身份确认、目标单次执行与认证/因果头隔离。
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from product.backend.core.errors import JiejianError
from product.backend.infra.execution.web.check_runtime import CheckWebRuntime
from product.protocols.check_runtime import CheckRuntimeBundle
from tests.fixtures.check_plan import plan
from tests.fixtures.check_runtime import runtime_bundle


@pytest.fixture
def local_target():
    requests = []
    state = {"subject_id": "subject-1", "target_status": 200}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.path, self.headers.get("Authorization"), self.headers.get("X-Jiejian-Case-ID")))
            payload = {"subject_id": state["subject_id"]} if self.path == "/identity" else {"resource_id": "resource-1"}
            raw = json.dumps(payload).encode()
            self.send_response(200 if self.path == "/identity" else state["target_status"])
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
        yield server.server_port, requests, state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


def runtime_and_case(port, *, cancelled=False):
    bundle = runtime_bundle(port=port)
    case = plan().actions[0].cases[0]
    payload = bundle.model_dump(mode="json")
    identity = payload["identities"][0]
    identity.update(identity_id=case.subject_test_identity_id, actor_id=case.subject_actor_id,
        actor_revision=case.subject_actor_revision, identity_fingerprint=case.subject_identity_fingerprint)
    identity["verification"].update(expected_actor_id=case.subject_actor_id,
        expected_actor_revision=case.subject_actor_revision)
    payload["actions"][0]["proofs"][0]["observation_identity_id"] = case.subject_test_identity_id
    bundle = CheckRuntimeBundle.model_validate_json(json.dumps(payload))
    runtime = CheckWebRuntime(bundle, environ={"CHECK_TEST_BEARER": "local-fixture-value"},
        cancellation_requested=lambda: cancelled)
    return runtime, case


def test_actual_identity_comes_from_readonly_application_response(local_target):
    port, requests, state = local_target
    runtime, case = runtime_and_case(port)
    try:
        assert runtime.verify_identity(case.subject_test_identity_id, case) == "MATCH"
        state["subject_id"] = "someone-else"
        assert runtime.verify_identity(case.subject_test_identity_id, case) == "MISMATCH"
        assert all(auth == "Bearer local-fixture-value" and marker == case.case_id for _, auth, marker in requests)
    finally:
        runtime.close()


def test_target_is_sent_once_with_adapter_owned_headers(local_target):
    port, requests, _state = local_target
    runtime, case = runtime_and_case(port)
    try:
        execution, response = runtime.execute_flow(runtime.bundle.actions[0], case)
        assert execution.outcome.value == "ACCEPTED" and response.status_code == 200
        assert requests == [("/objects/resource-1", "Bearer local-fixture-value", case.case_id)]
        with pytest.raises(JiejianError):
            runtime.execute_flow(runtime.bundle.actions[0], case)
        assert len(requests) == 1
    finally:
        runtime.close()


def test_ambiguous_target_result_cannot_trigger_replay(local_target):
    port, requests, state = local_target
    state["target_status"] = 500
    runtime, case = runtime_and_case(port)
    try:
        execution, _ = runtime.execute_flow(runtime.bundle.actions[0], case)
        assert execution.outcome.value == "UNKNOWN"
        with pytest.raises(JiejianError):
            runtime.execute_flow(runtime.bundle.actions[0], case)
        assert len(requests) == 1
    finally:
        runtime.close()


def test_cancellation_prevents_target_traffic(local_target):
    port, requests, _state = local_target
    runtime, case = runtime_and_case(port, cancelled=True)
    try:
        with pytest.raises(JiejianError) as caught:
            runtime.execute_flow(runtime.bundle.actions[0], case)
        assert caught.value.code == "EXEC_CANCELLED"
        assert requests == []
    finally:
        runtime.close()


def test_verified_execution_checks_identity_immediately_before_target_in_same_session(local_target, monkeypatch):
    port, requests, _state = local_target
    runtime, case = runtime_and_case(port)
    sessions = []
    execute = runtime.adapter.execute_detailed
    def capture(*args, **kwargs):
        sessions.append(kwargs["identity_runtime"])
        return execute(*args, **kwargs)
    monkeypatch.setattr(runtime.adapter, "execute_detailed", capture)
    try:
        execution, _response, identity = runtime.execute_flow(runtime.bundle.actions[0], case, verify_identity=True)
        assert execution.outcome.value == "ACCEPTED" and identity == "MATCH"
        assert [path for path, *_ in requests] == ["/identity", "/objects/resource-1"]
        assert len(sessions) == 2 and sessions[0] is sessions[1]
    finally:
        runtime.close()


def test_secret_collection_ignores_business_labels():
    from product.backend.infra.execution.web.check_runtime import check_secret_names
    payload = runtime_bundle().model_dump(mode="json")
    payload["identities"][0]["label"] = "env:UNRELATED_SECRET"
    bundle = CheckRuntimeBundle.model_validate_json(json.dumps(payload))
    assert check_secret_names(bundle) == ("CHECK_TEST_BEARER",)
