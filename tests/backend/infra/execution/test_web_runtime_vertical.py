from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from product.backend.core.lifecycle import CaseVerdict
from product.backend.core.verification.facts import (
    ObservationFact,
    ObservedEffect,
    TemporalClosure,
    aggregate_security_effect,
)
from product.backend.core.verification.permission_evaluation import (
    CaseDecisionInput,
    evaluate_permission_case,
)
from product.backend.infra.execution.port import TargetRuntimeContext
from product.backend.infra.execution.web.runtime import WebTargetRuntimeFactory
from product.protocols import (
    BaselineIntegrityMode,
    BaselineProjection,
    CookieSessionIdentityBinding,
    Correlation,
    HttpOutcomeClassifier,
    HttpPredicate,
    HttpPredicateKind,
    HttpRequestTemplate,
    IdentityBootstrapRequest,
    ObservationPhase,
    ResponseExtractor,
    ResponseExtractorKind,
    ValueSlot,
    ValueSlotConsumer,
    ValueSlotSource,
    WebExecutionIdentity,
    WebTargetDefinition,
    WebTargetScope,
    WebExecutionProfile,
    HttpWorkflowBinding,
    HttpWorkflowStep,
    SubjectExecutionBinding,
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


def _document(port: int):
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
                response_extractors=(ResponseExtractor(extractor_id="login-csrf", kind=ResponseExtractorKind.JSON_PATH, json_path="$.csrf", secret=True),),
            ),
        ),),
    )
    project_slot = ValueSlot(slot_id="project_id", source=ValueSlotSource.PRIOR_STEP_JSON_PATH, consumer=ValueSlotConsumer.PATH, source_path="$.id", producer_step_id="create-project")
    workflow = HttpWorkflowBinding(
        workflow_id="approve-workflow",
        source_flow_id="recorded-project-flow",
        action_id="modify",
        steps=(
            HttpWorkflowStep(
                id="create-project",
                purpose=WorkflowStepPurpose.SETUP,
                identity_id=CASE_SUBJECT_IDENTITY,
                request_template=HttpRequestTemplate(method="POST", path="/projects", body={"kind": "JSON", "value": {"name": "bounded"}}, response_extractors=(ResponseExtractor(extractor_id="project_id", kind=ResponseExtractorKind.JSON_PATH, json_path="$.id"),)),
                classifier=HttpOutcomeClassifier(accepted=(HttpPredicate(kind=HttpPredicateKind.STATUS_IN, statuses=(201,)),)),
            ),
            HttpWorkflowStep(
                id="open-project",
                purpose=WorkflowStepPurpose.SETUP,
                identity_id=CASE_SUBJECT_IDENTITY,
                request_template=HttpRequestTemplate(method="GET", path="/projects/{project_id}", input_slots=(project_slot.model_copy(update={"consumer_step_id": "open-project"}),)),
                classifier=HttpOutcomeClassifier(accepted=(HttpPredicate(kind=HttpPredicateKind.STATUS_IN, statuses=(200,)),)),
                depends_on_step_ids=("create-project",),
            ),
            HttpWorkflowStep(
                id="approve-project",
                purpose=WorkflowStepPurpose.TARGET,
                identity_id=CASE_SUBJECT_IDENTITY,
                request_template=HttpRequestTemplate(method="POST", path="/projects/{project_id}/approve", input_slots=(project_slot.model_copy(update={"consumer_step_id": "approve-project"}),)),
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
        baseline_projections=(BaselineProjection(projection_id="project-state", logical_resource_handle="created-project", normalization_version="1", projection_version="1", integrity_mode=BaselineIntegrityMode.EXACT_RESTORE),),
        reset_strategy={"kind": "RESET_ENDPOINT", "path": "/reset"},
    )
    snapshot = document.project_snapshot.model_copy(update={"target": target, "identities": (cookie_identity,), "workflow_bindings": (workflow,)})
    return document.model_copy(update={"budget": document.budget.model_copy(update={"max_requests": 10}), "project_snapshot": snapshot})


def _owner_observation(session, document, case, phase):
    spec = document.project_snapshot.observers[0]
    binding = document.project_snapshot.observer_bindings[0]
    correlation = Correlation(
        case_id=case.case_id,
        resource_id=case.resource_ids[0],
        request_marker=case.case_id,
    )
    result = session.observe_target(spec, binding, correlation, phase)
    assert result is not None
    return result.envelope


def test_web_runtime_vertical_case_has_one_target_and_no_response_on_port(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server, thread = _server()
    try:
        document = _document(server.server_port)
        snapshot = document.project_snapshot
        case = snapshot.plan.cases[0]
        action = snapshot.contract.actions[0]
        runtime = WebTargetRuntimeFactory().create(
            snapshot,
            TargetRuntimeContext(
                environ={
                    "JIEJIAN_TEST_TOKEN": "subject-secret",
                    "OWNER_READ_ONLY": "owner-secret",
                },
                staging=tmp_path / "staging",
                clock=iter(range(100, 200)).__next__,
                cancellation_requested=lambda: False,
            ),
        )
        calls: list[tuple[str, bool]] = []
        original_execute_detailed = runtime.adapter.execute_detailed

        def record_budget_marker(binding, **kwargs):
            calls.append((binding.path, bool(kwargs.get("cleanup_request", False))))
            return original_execute_detailed(binding, **kwargs)

        monkeypatch.setattr(runtime.adapter, "execute_detailed", record_budget_marker)
        session = runtime.open_case(case, action)
        assert not hasattr(session, "response")
        try:
            session.prepare()
            baseline = _owner_observation(session, document, case, ObservationPhase.BASELINE)
            _owner_observation(session, document, case, ObservationPhase.BEFORE)
            baseline_result = session.evaluate_baseline((baseline,))
            assert baseline_result.valid is True
            assert baseline_result.comparison_fingerprints != (
                baseline.state.canonical_sha256,
            )

            ignored = ("subject_id",)
            allow_comparison = session.evaluate_baseline(
                (baseline,),
                ignored_case_fields=ignored,
            ).comparison_fingerprints
            changed_subject = case.model_copy(update={"subject_id": "other-member"})
            changed_subject_comparison = runtime.open_case(
                changed_subject,
                action,
            ).evaluate_baseline(
                (baseline,),
                ignored_case_fields=ignored,
            ).comparison_fingerprints
            changed_relationship = case.model_copy(
                update={"relation_paths": (("different-relation",),)}
            )
            changed_relationship_comparison = runtime.open_case(
                changed_relationship,
                action,
            ).evaluate_baseline(
                (baseline,),
                ignored_case_fields=ignored,
            ).comparison_fingerprints
            changed_effect_comparison = runtime.open_case(
                case,
                action.model_copy(update={"effect_ids": ("other-effect",)}),
            ).evaluate_baseline(
                (baseline,),
                ignored_case_fields=ignored,
            ).comparison_fingerprints
            changed_workflow = snapshot.workflow_bindings[0].model_copy(
                update={"workflow_fingerprint": "f" * 64}
            )
            changed_workflow_runtime = WebTargetRuntimeFactory().create(
                snapshot.model_copy(
                    update={"workflow_bindings": (changed_workflow,)}
                ),
                TargetRuntimeContext(
                    environ={
                        "JIEJIAN_TEST_TOKEN": "subject-secret",
                        "OWNER_READ_ONLY": "owner-secret",
                    },
                    staging=tmp_path / "changed-workflow-staging",
                    clock=iter(range(200, 300)).__next__,
                    cancellation_requested=lambda: False,
                ),
            )
            try:
                changed_workflow_comparison = changed_workflow_runtime.open_case(
                    case,
                    action,
                ).evaluate_baseline(
                    (baseline,),
                    ignored_case_fields=ignored,
                ).comparison_fingerprints
            finally:
                changed_workflow_runtime.close()
            changed_projection = snapshot.workflow_bindings[0].baseline_projections[
                0
            ].model_copy(update={"projection_version": "2"})
            changed_version_workflow = snapshot.workflow_bindings[0].model_copy(
                update={"baseline_projections": (changed_projection,)}
            )
            changed_version_runtime = WebTargetRuntimeFactory().create(
                snapshot.model_copy(
                    update={"workflow_bindings": (changed_version_workflow,)}
                ),
                TargetRuntimeContext(
                    environ={
                        "JIEJIAN_TEST_TOKEN": "subject-secret",
                        "OWNER_READ_ONLY": "owner-secret",
                    },
                    staging=tmp_path / "changed-version-staging",
                    clock=iter(range(300, 400)).__next__,
                    cancellation_requested=lambda: False,
                ),
            )
            try:
                changed_version_comparison = changed_version_runtime.open_case(
                    case,
                    action,
                ).evaluate_baseline(
                    (baseline,),
                    ignored_case_fields=ignored,
                ).comparison_fingerprints
            finally:
                changed_version_runtime.close()
            assert changed_subject_comparison == allow_comparison
            assert changed_relationship_comparison != allow_comparison
            assert changed_effect_comparison != allow_comparison
            assert changed_workflow_comparison != allow_comparison
            assert changed_version_comparison != allow_comparison

            execution = session.execute_target()
            target_count = len(server.events)  # type: ignore[attr-defined]
            with pytest.raises(RuntimeError, match="TARGET already executed"):
                session.execute_target()
            assert len(server.events) == target_count  # type: ignore[attr-defined]

            after = _owner_observation(session, document, case, ObservationPhase.AFTER)
            eventual = _owner_observation(session, document, case, ObservationPhase.EVENTUAL)
            before_resolve = len(server.events)  # type: ignore[attr-defined]
            resolved = session.resolve_execution((baseline, after, eventual))
            assert resolved == execution
            assert len(server.events) == before_resolve  # type: ignore[attr-defined]

            observation_fact = ObservationFact(
                requirement_id="resource_state",
                resource_id=case.resource_ids[0],
                effect=ObservedEffect.CONFIRMED,
                complete=True,
                reliable=True,
                correlated=True,
                temporal_closure=TemporalClosure.CLOSED,
            )
            effect = snapshot.contract.effects[0]
            effect_binding = snapshot.effect_bindings[0]
            effect_fact = aggregate_security_effect(
                effect,
                resource_id=case.resource_ids[0],
                required_requirement_ids=effect_binding.required_channels,
                corroborating_requirement_ids=effect_binding.corroborating_channels,
                observations=(observation_fact,),
                baseline_integrity=True,
            )
            verdict, reasons = evaluate_permission_case(
                CaseDecisionInput(
                    case=case,
                    action=action,
                    execution=resolved,
                    effects=(effect_fact,),
                    allow_control_valid=True,
                    baseline_integrity=True,
                )
            )
            assert verdict is CaseVerdict.SAFE
            assert reasons == ()
        finally:
            session.cleanup()
            runtime.close()
        assert server.events[:7] == [  # type: ignore[attr-defined]
            "/reset",
            "/login",
            "/projects",
            "/projects/project-dynamic",
            "/owner/resources/document",
            "/owner/resources/document",
            "/projects/project-dynamic/approve",
        ]
        assert server.events[7:] == [  # type: ignore[attr-defined]
            "/owner/resources/document",
            "/owner/resources/document",
            "/workflow-cleanup",
            "/reset",
        ]
        assert calls[:2] == [
            ("/projects", False),
            ("/projects/{project_id}", False),
        ]
        assert ("/workflow-cleanup", True) in calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_web_runtime_cleanup_is_still_attempted_after_target_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server, thread = _server()
    try:
        document = _document(server.server_port)
        snapshot = document.project_snapshot
        case = snapshot.plan.cases[0]
        runtime = WebTargetRuntimeFactory().create(
            snapshot,
            TargetRuntimeContext(
                environ={"OWNER_READ_ONLY": "owner-secret"},
                staging=tmp_path / "staging",
                clock=iter(range(100, 200)).__next__,
                cancellation_requested=lambda: False,
            ),
        )
        session = runtime.open_case(case, snapshot.contract.actions[0])
        session.prepare()
        adapter = runtime.adapter
        original = adapter.execute_detailed

        def fail_target(binding, **kwargs):
            if binding.path == "/projects/{project_id}/approve":
                raise RuntimeError("target failure")
            return original(binding, **kwargs)

        monkeypatch.setattr(adapter, "execute_detailed", fail_target)
        try:
            with pytest.raises(RuntimeError, match="target failure"):
                session.execute_target()
        finally:
            session.cleanup()
            runtime.close()
        assert "/workflow-cleanup" in server.events  # type: ignore[attr-defined]
        assert "/reset" in server.events  # type: ignore[attr-defined]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
