# 用真实受控 HTTP 观察验证注册效果投影、独立身份与逐 Case 基线隔离。
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from product.backend.infra.execution.web.check_runtime import CheckWebRuntime
from product.backend.infra.observers.check_runtime import CheckObserverRuntime
from tests.fixtures.check_execution import execution_pair


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


@pytest.fixture
def observer_runtime(observer_target, tmp_path):
    port, state, requests = observer_target
    request, bundle = execution_pair(port=port)
    environ = {"CHECK_TEST_BEARER": "loopback-fixture-value"}
    web = CheckWebRuntime(bundle, environ=environ, cancellation_requested=lambda: False)
    observer = CheckObserverRuntime(bundle, web, attempt_dir=tmp_path, environ=environ,
        cancellation_requested=lambda: False)
    try:
        yield request, bundle, observer, state, requests
    finally:
        web.close()


def observe(parts, case, phase, *, baseline=False):
    request, bundle, runtime, _state, _requests = parts
    return runtime.observe(case=case, action_id=request.actions[0].action_id,
        requirement=case.proof_requirements[0], proof=bundle.actions[0].proofs[0],
        phase=phase, baseline_trusted=baseline)


def test_registered_owner_api_projects_actual_business_state_change(observer_runtime):
    request, _bundle, _runtime, state, requests = observer_runtime
    case = request.actions[0].cases[0]
    before = observe(observer_runtime, case, "BEFORE")
    assert before.baseline_projection == (True, "DRAFT", "before")
    state["value"] = "after"
    after = observe(observer_runtime, case, "AFTER", baseline=True)
    assert after.observation.state == "CONFIRMED"
    assert after.observation.complete and after.observation.reliable and after.observation.correlated
    assert after.observation.closure == "CLOSED"
    assert all(marker == case.case_id for _path, marker in requests)


def test_other_case_does_not_inherit_first_cases_before_observation(observer_runtime):
    request, _bundle, _runtime, state, _requests = observer_runtime
    first, second = request.actions[0].cases
    observe(observer_runtime, first, "BEFORE")
    state["value"] = "after"
    assert observe(observer_runtime, first, "AFTER", baseline=True).observation.state == "CONFIRMED"
    assert observe(observer_runtime, second, "AFTER", baseline=True).observation.state == "UNKNOWN"


def test_unverified_observation_identity_cannot_provide_authoritative_effect(observer_runtime):
    request, _bundle, _runtime, state, _requests = observer_runtime
    case = request.actions[0].cases[0]
    observe(observer_runtime, case, "BEFORE")
    state.update(subject_id="other-account", value="after")
    observed = observe(observer_runtime, case, "AFTER", baseline=True).observation
    assert not observed.reliable and not observed.correlated and not observed.complete


def test_incomplete_business_projection_is_not_a_trusted_baseline(observer_runtime):
    request, _bundle, _runtime, state, _requests = observer_runtime
    state["workflow_state"] = None
    assert observe(observer_runtime, request.actions[0].cases[0], "BEFORE").baseline_projection is None


@pytest.mark.parametrize("field,expected", [("value", "CONFIRMED"), ("missing", "UNKNOWN")])
def test_disclosure_uses_owner_projection_and_actual_target_response(observer_runtime, field, expected):
    request, bundle, runtime, state, _requests = observer_runtime
    case = request.actions[0].cases[0]
    proof = bundle.actions[0].proofs[0].model_copy(update={"effect_kind": "DATA_DISCLOSURE", "protected_projection": (field,)})
    state["workflow_state"] = None
    def observed(phase):
        return runtime.observe(case=case, action_id=request.actions[0].action_id,
            requirement=case.proof_requirements[0], proof=proof, phase=phase, baseline_trusted=True)
    before = observed("BEFORE")
    if expected == "CONFIRMED":
        assert before.baseline_projection is not None
        assert "before" not in repr(before.baseline_projection)
    else:
        assert before.baseline_projection is None
    runtime.web.execute_flow(bundle.actions[0], case, verify_identity=True)
    result = observed("AFTER")
    assert result.observation.state == expected
    assert "before" not in result.observation.model_dump_json()


def test_disclosure_empty_or_redacted_baseline_cannot_confirm():
    from product.backend.infra.observers.check_disclosure import disclosure_proof
    for value in (None, "[REDACTED]", "<redacted>"):
        proof = disclosure_proof(owner={"value": value}, response={"value": value}, fields=("value",), key=b"ephemeral", marker="case")
        assert not proof.projection_complete and not proof.matched
    proof = disclosure_proof(owner={"value": "protected"}, response={}, fields=("value",), key=b"ephemeral", marker="case")
    assert proof.projection_complete and not proof.matched
