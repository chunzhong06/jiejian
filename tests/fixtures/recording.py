# 提供录制直接测试共用的受控 loopback 浏览器与请求 fixture。

from __future__ import annotations
from pathlib import Path
from product.backend.core.recording import RecordingState, RecordingStateEvent
from product.protocols import RecordingCleanupStatus, RecordingEvent, RecordingHeader, RecordingRunnerResult
from tests.fixtures.action_preparation import build_preparation_harness
from product.backend.workflows.recording.source import recording_source_fingerprint
from product.backend.workflows.recording.submission import RecordingSubmission
from product.backend.infra.recording.request_store import RecordingRequestStore
from product.backend.infra.runtime.jobs.attempts import JobAttempts

NOW_US = 1_820_000_000_000_000
PROJECT_ID = "recording-project"


class RecordingContext:
    """为生命周期测试提供正式来源和 Recording-only Job 服务。"""

    def __init__(self, tmp_path: Path, *, state_changing: bool = True) -> None:
        self.harness = build_preparation_harness(tmp_path, endpoint="http://127.0.0.1:18080", state_changing=state_changing)
        core = self.harness.core
        self.project_id = self.harness.project_id
        self.var_dir = core.var_dir
        self.database_path = self.var_dir / "data" / "jiejian.db"
        self.engine = core.engine
        self.uow_factory = core.uow_factory
        self.request_store = RecordingRequestStore(self.var_dir)
        self.job_targets = core.job_targets
        self.attempts = JobAttempts(self.uow_factory, jitter_source=lambda _: 0, targets=self.job_targets)
        self.application = RecordingSubmission(self.uow_factory, self.request_store, attempts=self.attempts)

    def bind_request(self, request: RecordingRunnerRequest) -> RecordingRunnerRequest:
        identity = self.harness.identities[0]
        with self.uow_factory() as work:
            understanding = work.application_understanding.get(self.project_id)
            assert understanding is not None
            # loopback server 使用本轮端口；指纹必须包含这个真实确认地址。
            understanding = understanding.model_copy(update={"confirmed_endpoint": request.target_scope.base_url})
            work.application_understanding.replace(understanding)
            action_binding = work.business_boundaries.action_binding(self.harness.action.action_id, 1)
            actor_binding = work.business_boundaries.actor_binding(identity.actor_id, identity.actor_revision)
            fingerprint = recording_source_fingerprint(self.harness.action, identity, understanding, action_binding, actor_binding)
            work.commit()
        return RecordingRunnerRequest.model_validate(request.model_dump(mode="python") | {
            "project_id": self.project_id,
            "business_action_id": self.harness.action.action_id,
            "action_revision": 1,
            "test_identity_id": identity.identity_id,
            "preparation_source_fingerprint": fingerprint,
            "sessions": (request.sessions[0].model_copy(update={"test_identity_id": identity.identity_id}),),
        })

    def complete_target(self):
        """经提交、fenced result 和正式审阅形成可供补录引用的 TARGET。"""
        from product.backend.workflows.recording.submission import SubmitRecording
        from product.backend.infra.runtime.jobs.models import ClaimJob
        from product.backend.workflows.recording.lifecycle import RecordingLifecycle
        from product.protocols import (ConfirmFlowDraftTarget, ConfirmFlowDraftResource,
                                       ConfirmFlowDraftVariableChoice, flow_draft_source_choice_id)
        request = self.bind_request(runner_request("rec_" + "1" * 32))
        submitted = self.application.submit(SubmitRecording(request=request, flow_id="recorded-flow",
            idempotency_key="parent-target", now_us=NOW_US, available_at_us=NOW_US))
        claimed = self.attempts.claim(ClaimJob(job_id=submitted.job.job_id, lease_owner="fixture-worker",
            now_us=NOW_US + 10, lease_duration_us=60_000_000))
        assert claimed is not None
        completed = self.application.consume_result(job_id=submitted.job.job_id, lease_owner="fixture-worker",
            fencing_token=claimed.job.fencing_token, result=captured_result(request.recording_id, project_id=self.project_id),
            now_us=NOW_US + 30)
        assert completed.draft is not None
        lifecycle = RecordingLifecycle(self.uow_factory, var_dir=self.var_dir)
        draft = completed.draft
        for variable in draft.variables:
            lifecycle.review(request.recording_id, ConfirmFlowDraftVariableChoice(
                operation="CONFIRM_VARIABLE_CHOICE", variable_name=variable.name,
                choice_id=flow_draft_source_choice_id(variable.candidate_sources[0])))
        view = lifecycle.review(request.recording_id, ConfirmFlowDraftTarget(
            operation="CONFIRM_TARGET_STEP", step_id=draft.steps[-1].id))
        resource = next(item for item in view.draft.steps[-1].resource_candidates if item.location == "path[1]")
        lifecycle.review(request.recording_id, ConfirmFlowDraftResource(
            operation="CONFIRM_RESOURCE_SLOT", candidate_id=resource.candidate_id))
        return lifecycle.finalize(request.recording_id, var_dir=self.var_dir, now_us=NOW_US + 40).recording

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, quote, urlsplit

import pytest

from product.protocols.web.target import WebTargetScope
from product.protocols import (
    RecordingAuthMethod,
    RecordingBudget,
    RecordingCookieRef,
    RecordingEventKind,
    RecordingRunnerRequest,
    RecordingRunnerResultType,
    RecordingSessionRef,
    canonical_recording_json_bytes,
)
from product.backend.infra.recording.browser import BrowserRecordingAdapter, RecordingBrowserSession



TEST_IDENTITY_ID = "tid_0123456789abcdef0123456789abcdef"
COOKIE_ENV_NAME = "JIEJIAN_RECORDING_TEST_COOKIE"


class LocalBrowserServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, secret: str) -> None:
        self.secret = secret
        self.paths: list[str] = []
        self.request_semantics: list[dict[str, bool | str]] = []
        super().__init__(("127.0.0.1", 0), LocalBrowserHandler)

    def url(self, path: str = "/") -> str:
        return f"http://127.0.0.1:{self.server_port}{path}"


class LocalBrowserHandler(BaseHTTPRequestHandler):
    server: LocalBrowserServer

    def do_GET(self) -> None:
        self.server.paths.append(self.path)
        parsed = urlsplit(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", query["target"][0])
            self.end_headers()
            return
        if parsed.path == "/secret":
            body = json.dumps(
                {"password": self.server.secret, "note": self.server.secret}
            ).encode()
            self._send(
                body,
                "application/json",
                headers={
                    "Set-Cookie": f"session={self.server.secret}; Path=/",
                    "X-Visible": self.server.secret,
                },
            )
            return
        if parsed.path == "/stream":
            self._send(b"data: bounded\n\n", "text/event-stream")
            return
        if parsed.path == "/no-length":
            body = b"bounded but length is unspecified"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/page":
            body = (
                "<!doctype html><iframe src='/frame'></iframe>"
                "<a id='popup' target='_blank' href='/popup'>popup</a>"
            ).encode()
            self._send(body, "text/html; charset=utf-8")
            return
        if parsed.path == "/ui":
            body = (
                "<!doctype html><form id='resource-form'>"
                "<input name='password' type='password'>"
                "<button data-testid='submit' type='submit'>submit</button></form>"
                "<script>document.querySelector('form').addEventListener('submit', e => {"
                "e.preventDefault(); fetch('/echo', {method:'POST', headers:{"
                "'Content-Type':'application/json','X-Method-Probe':'probe'},"
                "body:JSON.stringify({password:'ui-secret',value:'probe'})});});</script>"
            ).encode()
            self._send(body, "text/html; charset=utf-8")
            return
        if parsed.path == "/slow":
            time.sleep(0.25)
            self._send(b"slow preparation response", "text/plain")
            return
        if parsed.path in {"/frame", "/popup"}:
            self._send(b"<!doctype html><p>ok</p>", "text/html; charset=utf-8")
            return
        if parsed.path in {"/blocked-iframe", "/blocked-popup"}:
            target = query["target"][0]
            element = (
                f"<iframe src='{target}'></iframe>"
                if parsed.path.endswith("iframe")
                else f"<a id='blocked' target='_blank' href='{target}'>blocked</a>"
            )
            self._send(element.encode(), "text/html; charset=utf-8")
            return
        self._send(b"<!doctype html><p>root</p>", "text/html; charset=utf-8")

    def do_POST(self) -> None:
        self.server.paths.append(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.server.request_semantics.append(
            {
                "method": self.command,
                "body": body == json.dumps(
                    {"password": self.server.secret, "value": "probe"},
                    separators=(",", ":"),
                ).encode(),
                "header": self.headers.get("X-Method-Probe") == "probe",
                "authorization": self.headers.get("Authorization")
                == f"Bearer {self.server.secret}",
                "cookie": f"identity={self.server.secret}" in self.headers.get("Cookie", ""),
            }
        )
        self._send(b'{"ok":true}', "application/json")

    def _send(
        self,
        body: bytes,
        content_type: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


@contextmanager
def browser_server(secret: str) -> Iterator[LocalBrowserServer]:
    server = LocalBrowserServer(secret)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def recording_request(port: int) -> RecordingRunnerRequest:
    created_at_us = time.time_ns() // 1_000
    return RecordingRunnerRequest(
        schema_version="2",
        recording_id="rec_0123456789abcdef0123456789abcdef",
        project_id="ownership-recording",
        business_action_id="bac_0123456789abcdef0123456789abcdef",
        action_revision=1,
        test_identity_id=TEST_IDENTITY_ID,
        preparation_source_fingerprint="a" * 64,
        created_at_us=created_at_us,
        target_scope=WebTargetScope(
            base_url=f"http://127.0.0.1:{port}",
            allowed_origins=(f"http://127.0.0.1:{port}",),
            allowed_hosts=("127.0.0.1",),
            allowed_ports=(port,),
            allow_private_network=True,
            timeout_seconds=5,
            max_requests=64,
            max_response_bytes=65_536,
        ),
        sessions=(
            RecordingSessionRef(
                test_identity_id=TEST_IDENTITY_ID,
                session_ref="session_0123456789abcdef0123456789abcdef",
                auth_method=RecordingAuthMethod.COOKIE_SESSION,
                cookies=(
                    RecordingCookieRef(
                        name="identity",
                        domain="127.0.0.1",
                        path="/",
                        secure=False,
                        http_only=True,
                        same_site="LAX",
                        value_ref=f"env:{COOKIE_ENV_NAME}",
                    ),
                ),
                expires_at_us=created_at_us + 60_000_000,
            ),
        ),
        budget=RecordingBudget(
            max_duration_us=30_000_000,
            max_events=256,
            max_pages=8,
            max_contexts=1,
            max_field_chars=1_024,
            max_body_bytes=16_384,
            max_total_payload_bytes=262_144,
        ),
    )




def runner_request(
    recording_id: str,
    *,
    secret_refs: tuple[str, ...] = ("env:RECORDING_SECRET",),
) -> RecordingRunnerRequest:
    return RecordingRunnerRequest(
        schema_version="2",
        recording_id=recording_id,
        project_id=PROJECT_ID,
        business_action_id="bac_" + "1" * 32,
        action_revision=1,
        test_identity_id=TEST_IDENTITY_ID,
        preparation_source_fingerprint="a" * 64,
        created_at_us=NOW_US if recording_id.endswith("1" * 32) else NOW_US + 100,
        target_scope=WebTargetScope(
            base_url="http://127.0.0.1:18080",
            allowed_origins=("http://127.0.0.1:18080",),
            allowed_hosts=("127.0.0.1",),
            allowed_ports=(18080,),
            allow_private_network=True,
        ),
        sessions=(
            RecordingSessionRef(
                test_identity_id="tid_0123456789abcdef0123456789abcdef",
                session_ref="session_" + "5" * 32,
                auth_method=RecordingAuthMethod.BEARER,
                bearer_ref=secret_refs[0],
                expires_at_us=NOW_US + 1_000_000,
            ),
        ),
        budget=RecordingBudget(
            max_duration_us=1_000_000,
        ),
        headless=True,
        trace_enabled=False,
    )

def captured_result(
    recording_id: str,
    *,
    project_id: str = PROJECT_ID,
    response_body: str = '{"id":"resource-42"}',
) -> RecordingRunnerResult:
    lifecycle = (
        RecordingStateEvent(
            sequence=1,
            source=RecordingState.CREATED,
            target=RecordingState.STARTING,
            operator="RECORDING_RUNNER",
            occurred_at_us=NOW_US + 11,
        ),
        RecordingStateEvent(
            sequence=2,
            source=RecordingState.STARTING,
            target=RecordingState.RECORDING,
            operator="RECORDING_RUNNER",
            occurred_at_us=NOW_US + 12,
        ),
        RecordingStateEvent(
            sequence=3,
            source=RecordingState.RECORDING,
            target=RecordingState.CLEANING,
            operator="RECORDING_RUNNER",
            occurred_at_us=NOW_US + 13,
            reason_code="RECORDING_FINISHED",
        ),
        RecordingStateEvent(
            sequence=4,
            source=RecordingState.CLEANING,
            target=RecordingState.PROCESSING,
            operator="RECORDING_RUNNER",
            occurred_at_us=NOW_US + 14,
        ),
    )
    events = (
        RecordingEvent(
            sequence=1,
            occurred_at_us=NOW_US + 12,
            kind=RecordingEventKind.UI_SUBMIT,
            identity_id="tid_" + "0" * 31 + "1",
            page_id="page_000001",
            frame_id="frame_000001",
            action_id="action_000001",
            element_locator="#resource-form",
        ),
        RecordingEvent(
            sequence=2,
            occurred_at_us=NOW_US + 12,
            kind=RecordingEventKind.REQUEST,
            identity_id="tid_" + "0" * 31 + "1",
            page_id="page_000001",
            frame_id="frame_000001",
            request_id="request_000001",
            caused_by_action_id="action_000001",
            url="http://127.0.0.1:18080/resources",
            method="POST",
            resource_type="fetch",
            body='{"name":"demo"}',
        ),
        RecordingEvent(
            sequence=3,
            occurred_at_us=NOW_US + 13,
            kind=RecordingEventKind.RESPONSE,
            identity_id="tid_" + "0" * 31 + "1",
            page_id="page_000001",
            frame_id="frame_000001",
            request_id="request_000001",
            url="http://127.0.0.1:18080/resources",
            status_code=201,
            headers=(
                RecordingHeader(
                    name="location",
                    value="/resources/resource-42",
                ),
            ),
            body=response_body,
        ),
        RecordingEvent(
            sequence=4,
            occurred_at_us=NOW_US + 14,
            kind=RecordingEventKind.REQUEST,
            identity_id="tid_" + "0" * 31 + "1",
            page_id="page_000001",
            frame_id="frame_000001",
            request_id="request_000002",
            url="http://127.0.0.1:18080/resources/resource-42",
            method="GET",
            resource_type="fetch",
        ),
        RecordingEvent(
            sequence=5,
            occurred_at_us=NOW_US + 15,
            kind=RecordingEventKind.RESPONSE,
            identity_id="tid_" + "0" * 31 + "1",
            page_id="page_000001",
            frame_id="frame_000001",
            request_id="request_000002",
            url="http://127.0.0.1:18080/resources/resource-42",
            status_code=200,
            body="{}",
        ),
    )
    return RecordingRunnerResult(
        schema_version="1",
        recording_id=recording_id,
        project_id=project_id,
        finished_at_us=NOW_US + 20,
        result_type=RecordingRunnerResultType.CAPTURED,
        recording_state=RecordingState.PROCESSING,
        cleanup_status=RecordingCleanupStatus.SUCCEEDED,
        reason_codes=("RECORDING_FINISHED",),
        state_events=lifecycle,
        events=events,
    )
