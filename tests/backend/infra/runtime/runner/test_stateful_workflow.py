from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from types import SimpleNamespace

import pytest

from product.backend.core.verification.differential import TwinExecutionRole
from product.backend.infra.execution.port import TargetBaselineResult
from product.backend.infra.execution.web.runtime import WebTargetRuntimeFactory
from product.backend.infra.runtime.runner import executor as runner_execution
from product.backend.infra.runtime.runner.executor import RunnerExecutor, _validate_twin_baseline
from product.backend.infra.runtime.runner.result_builder import evidence_from_case
from product.protocols import (
    BaselineIntegrityMode,
    BaselineProjection,
    CookieSessionIdentityBinding,
    WebExecutionIdentity,
    HttpOutcomeClassifier,
    HttpPredicate,
    HttpPredicateKind,
    HttpRequestTemplate,
    HttpWorkflowBinding,
    HttpWorkflowStep,
    IdentityBootstrapRequest,
    ResponseExtractor,
    ResponseExtractorKind,
    ValueSlot,
    ValueSlotConsumer,
    ValueSlotSource,
    WebTargetDefinition,
    WebTargetScope,
    WorkflowStepPurpose,
)
from product.protocols.web.workflow import CASE_SUBJECT_IDENTITY
from tests.fixtures.runner import runner_input


class _WorkflowHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
        self.server.events.append(self.path)  # type: ignore[attr-defined]
        length = int(self.headers.get("Content-Length", "0"))
        if length:
            self.rfile.read(length)
        if self.path == "/login":
            self._send(200, {"csrf": "csrf-bootstrap-secret"}, headers={"Set-Cookie": "sid=isolated-session; Path=/"})
        elif self.path == "/reset":
            self.server.project = None  # type: ignore[attr-defined]
            self._send(200, {"reset": True})
        elif self.path == "/projects":
            if "sid=isolated-session" not in self.headers.get("Cookie", ""):
                self._send(403, {})
                return
            self.server.project = {"id": "project-dynamic", "approved": False}  # type: ignore[attr-defined]
            self._send(201, {"id": "project-dynamic"})
        elif self.path == "/projects/project-dynamic/approve":
            self.server.project["approved"] = True  # type: ignore[attr-defined]
            self._send(200, {"approved": True})
        elif self.path == "/workflow-cleanup":
            self.server.project = None  # type: ignore[attr-defined]
            self._send(200, {"cleaned": True})
        else:
            self._send(404, {})

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        self.server.events.append(self.path)  # type: ignore[attr-defined]
        if self.path == "/projects/project-dynamic" and self.server.project is not None:  # type: ignore[attr-defined]
            self._send(200, dict(self.server.project))  # type: ignore[attr-defined]
        elif self.path.startswith("/owner/resources/"):
            project = self.server.project  # type: ignore[attr-defined]
            self._send(200, {"exists": project is not None, "approved": bool(project and project["approved"])})
        else:
            self._send(404, {})

    def _send(self, status: int, payload: dict[str, object], *, headers: dict[str, str] | None = None) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def _server() -> tuple[ThreadingHTTPServer, Thread]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _WorkflowHandler)
    server.events = []  # type: ignore[attr-defined]
    server.project = None  # type: ignore[attr-defined]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _document(port: int, *, expected_fingerprint: str | None = None):
    document = runner_input()
    origin = f"http://127.0.0.1:{port}"
    target = WebTargetDefinition(
        scope=WebTargetScope(
            base_url=origin,
            allowed_origins=(origin,),
            allowed_hosts=("127.0.0.1",),
            allowed_ports=(port,),
            allow_private_network=True,
            timeout_seconds=5,
            max_requests=11,
            max_response_bytes=262_144,
        ),
        reset_path="/reset",
    )
    original_identity = document.project_snapshot.identities[0]
    cookie_identity = WebExecutionIdentity(
        identity_id=original_identity.identity_id,
        role=original_identity.role,
        binding=CookieSessionIdentityBinding(bootstrap_template_ids=("login",)),
        bootstrap_requests=(IdentityBootstrapRequest(
            template_id="login",
            request_template=HttpRequestTemplate(
                method="POST",
                path="/login",
                response_extractors=(ResponseExtractor(
                    extractor_id="login-csrf",
                    kind=ResponseExtractorKind.JSON_PATH,
                    json_path="$.csrf",
                    secret=True,
                ),),
            ),
        ),),
    )
    project_slot = ValueSlot(
        slot_id="project_id",
        source=ValueSlotSource.PRIOR_STEP_JSON_PATH,
        consumer=ValueSlotConsumer.PATH,
        source_path="$.id",
        producer_step_id="create-project",
    )
    workflow = HttpWorkflowBinding(
        workflow_id="approve-workflow",
        source_flow_id="recorded-project-flow",
        action_id="modify",
        steps=(
            HttpWorkflowStep(
                id="create-project",
                purpose=WorkflowStepPurpose.SETUP,
                identity_id=CASE_SUBJECT_IDENTITY,
                request_template=HttpRequestTemplate(
                    method="POST",
                    path="/projects",
                    body={"kind": "JSON", "value": {"name": "bounded"}},
                    response_extractors=(ResponseExtractor(extractor_id="project_id", kind=ResponseExtractorKind.JSON_PATH, json_path="$.id"),),
                ),
                classifier=HttpOutcomeClassifier(accepted=(HttpPredicate(kind=HttpPredicateKind.STATUS_IN, statuses=(201,)),)),
            ),
            HttpWorkflowStep(
                id="open-project",
                purpose=WorkflowStepPurpose.SETUP,
                identity_id=CASE_SUBJECT_IDENTITY,
                request_template=HttpRequestTemplate(
                    method="GET",
                    path="/projects/{project_id}",
                    input_slots=(project_slot.model_copy(update={"consumer_step_id": "open-project"}),),
                ),
                classifier=HttpOutcomeClassifier(accepted=(HttpPredicate(kind=HttpPredicateKind.STATUS_IN, statuses=(200,)),)),
                depends_on_step_ids=("create-project",),
            ),
            HttpWorkflowStep(
                id="approve-project",
                purpose=WorkflowStepPurpose.TARGET,
                identity_id=CASE_SUBJECT_IDENTITY,
                request_template=HttpRequestTemplate(
                    method="POST",
                    path="/projects/{project_id}/approve",
                    input_slots=(project_slot.model_copy(update={"consumer_step_id": "approve-project"}),),
                ),
                classifier=HttpOutcomeClassifier(accepted=(HttpPredicate(kind=HttpPredicateKind.STATUS_IN, statuses=(200,)),)),
                depends_on_step_ids=("open-project",),
            ),
            HttpWorkflowStep(
                id="cleanup-project",
                purpose=WorkflowStepPurpose.CLEANUP,
                identity_id=CASE_SUBJECT_IDENTITY,
                request_template=HttpRequestTemplate(method="POST", path="/workflow-cleanup"),
                depends_on_step_ids=("approve-project",),
            ),
        ),
        target_step_id="approve-project",
        baseline_projections=(BaselineProjection(
            projection_id="project-state",
            logical_resource_handle="created-project",
            normalization_version="1",
            projection_version="1",
            expected_fingerprint=expected_fingerprint,
        ),),
        reset_strategy={"kind": "RESET_ENDPOINT", "path": "/reset"},
    )
    snapshot = document.project_snapshot.model_copy(update={"target": target, "identities": (cookie_identity,), "workflow_bindings": (workflow,)})
    return document.model_copy(update={"budget": document.budget.model_copy(update={"max_requests": 11}), "project_snapshot": snapshot})


def test_permission_twin_requires_same_observed_baseline() -> None:
    stored: dict[str, tuple[str, ...]] = {}
    twin = SimpleNamespace(twin_id="twin-test")
    allow = TargetBaselineResult(
        valid=True,
        comparison_fingerprints=("a" * 64,),
    )
    same = TargetBaselineResult(
        valid=True,
        comparison_fingerprints=("a" * 64,),
    )
    changed = TargetBaselineResult(
        valid=True,
        comparison_fingerprints=("b" * 64,),
    )

    assert _validate_twin_baseline(
        stored,
        twin,
        TwinExecutionRole.ALLOW_CONTROL,
        allow,
    ).valid
    assert _validate_twin_baseline(
        stored,
        twin,
        TwinExecutionRole.DENY_VARIANT,
        same,
    ).valid
    mismatch = _validate_twin_baseline(
        stored,
        twin,
        TwinExecutionRole.DENY_VARIANT,
        changed,
    )
    assert mismatch.valid is False
    assert mismatch.reason_codes == ("TWIN_BASELINE_MISMATCH",)


def test_real_dynamic_workflow_runs_setup_baseline_before_target_and_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server, thread = _server()
    try:
        evaluate = runner_execution.evaluate_permission_case

        def evaluate_with_trace(decision):
            server.events.append("verification")  # type: ignore[attr-defined]
            return evaluate(decision)

        monkeypatch.setattr(runner_execution, "evaluate_permission_case", evaluate_with_trace)
        document = _document(server.server_port)
        runner = RunnerExecutor(
            document,
            runtime_factory=WebTargetRuntimeFactory(),
            environ={"JIEJIAN_TEST_TOKEN": "subject-secret", "OWNER_READ_ONLY": "owner-secret"},
            staging=tmp_path / "staging",
            clock=iter(range(100, 200)).__next__,
        )
        result = runner.run_case(document.project_snapshot.plan.cases[0])
        evidence = evidence_from_case(document, result)
        events = server.events  # type: ignore[attr-defined]
        assert events[:7] == [
            "/reset",
            "/login",
            "/projects",
            "/projects/project-dynamic",
            "/owner/resources/document",
            "/owner/resources/document",
            "/projects/project-dynamic/approve",
        ]
        assert events[7:] == [
            "/owner/resources/document",
            "verification",
            "/workflow-cleanup",
            "/reset",
        ]
        assert evidence.execution_fact.action_id == "modify"
        assert runner.runtime.baseline_integrities[evidence.case_snapshot.case_id][0]["valid"] is True
        assert "project-dynamic" not in evidence.model_dump_json()
        assert "csrf-bootstrap-secret" not in evidence.model_dump_json()
        runner.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_baseline_mismatch_stops_before_target(tmp_path: Path) -> None:
    server, thread = _server()
    try:
        document = _document(server.server_port, expected_fingerprint="0" * 64)
        runner = RunnerExecutor(
            document,
            runtime_factory=WebTargetRuntimeFactory(),
            environ={"JIEJIAN_TEST_TOKEN": "subject-secret", "OWNER_READ_ONLY": "owner-secret"},
            staging=tmp_path / "staging",
            clock=iter(range(100, 200)).__next__,
        )
        result = runner.run_case(document.project_snapshot.plan.cases[0])
        evidence = evidence_from_case(document, result)
        assert evidence.verdict.value == "INCONCLUSIVE"
        assert evidence.baseline_integrity is False
        assert "BASELINE_INTEGRITY_INVALID" in evidence.reason_codes
        assert "/projects/project-dynamic/approve" not in server.events  # type: ignore[attr-defined]
        runner.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
