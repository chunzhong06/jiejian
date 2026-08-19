from __future__ import annotations

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, quote, urlsplit

import pytest

from product.protocols.runner import WebTargetScope
from product.protocols import (
    RecordingBudget,
    RecordingEventKind,
    RecordingRunnerRequest,
    RecordingRunnerResultType,
    RecordingSessionRef,
    canonical_recording_json_bytes,
)
from product.backend.infra.recording.browser import BrowserRecordingAdapter, RecordingBrowserSession

pytestmark = [pytest.mark.browser, pytest.mark.slow]


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
                "cookie": "identity=owner" in self.headers.get("Cookie", ""),
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
        schema_version="1",
        recording_id="rec_0123456789abcdef0123456789abcdef",
        project_id="ownership-recording",
        created_at_us=created_at_us,
        target_scope=WebTargetScope(
            schema_version="2",
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
                schema_version="1",
                identity_id="owner",
                session_ref="session_0123456789abcdef0123456789abcdef",
                expires_at_us=created_at_us + 60_000_000,
            ),
            RecordingSessionRef(
                schema_version="1",
                identity_id="attacker",
                session_ref="session_fedcba9876543210fedcba9876543210",
                expires_at_us=created_at_us + 60_000_000,
            ),
        ),
        budget=RecordingBudget(
            schema_version="1",
            max_duration_us=30_000_000,
            max_events=256,
            max_pages=8,
            max_contexts=2,
            max_field_chars=1_024,
            max_body_bytes=16_384,
            max_total_payload_bytes=262_144,
        ),
    )


def test_browser_contexts_isolate_identity_state_and_redact_before_result(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    sentinel = "recording-browser-secret-sentinel"
    observed: dict[str, object] = {}
    with browser_server(sentinel) as server:
        request = recording_request(server.server_port)

        def interact(session: RecordingBrowserSession) -> None:
            owner = session.new_page("owner")
            owner.goto(server.url("/page"))
            owner.evaluate(
                """() => {
                    document.cookie = 'identity=owner';
                    localStorage.setItem('identity', 'owner');
                    sessionStorage.setItem('identity', 'owner');
                }"""
            )
            observed["post_status"] = owner.evaluate(
                """async ([url, secret]) => {
                    const response = await fetch(url, {
                        method: 'POST',
                        credentials: 'include',
                        headers: {
                            'Authorization': `Bearer ${secret}`,
                            'Content-Type': 'application/json',
                            'X-Method-Probe': 'probe'
                        },
                        body: JSON.stringify({password: secret, value: 'probe'})
                    });
                    return response.status;
                }""",
                [server.url("/echo"), sentinel],
            )
            owner.click("#popup")
            owner.goto(
                server.url(
                    f"/secret?token={quote(sentinel)}&note={quote(sentinel)}"
                )
            )
            attacker = session.new_page("attacker")
            attacker.goto(server.url("/page"))
            observed["attacker"] = attacker.evaluate(
                "() => [document.cookie, localStorage.getItem('identity'), "
                "sessionStorage.getItem('identity')]"
            )
            attacker.wait_for_timeout(200)

        result = BrowserRecordingAdapter().run(
            request,
            interact,
            known_secrets=(sentinel,),
        )

    assert result.result_type is RecordingRunnerResultType.CAPTURED
    assert observed["attacker"] == ["", None, None]
    assert observed["post_status"] == 200
    assert server.request_semantics == [
        {
            "method": "POST",
            "body": True,
            "header": True,
            "authorization": True,
            "cookie": True,
        }
    ]
    assert any(event.kind is RecordingEventKind.FRAME_ATTACHED for event in result.events)
    assert any(event.parent_page_id is not None for event in result.events)
    encoded = canonical_recording_json_bytes(result, known_secrets=(sentinel,))
    assert sentinel.encode() not in encoded
    assert b"[REDACTED]" in encoded
    assert capsys.readouterr() == ("", "")
    assert tuple(tmp_path.iterdir()) == ()


def test_controlled_capture_omits_preparation_and_late_response_events() -> None:
    sentinel = "controlled-recording-secret-sentinel"
    signals = {"start": False, "stop": False}
    with browser_server(sentinel) as server:
        request = recording_request(server.server_port)
        request = request.model_copy(
            update={
                "sessions": (request.sessions[0],),
                "budget": request.budget.model_copy(
                    update={"max_duration_us": 10_000_000}
                ),
            }
        )

        def interact(session: RecordingBrowserSession) -> None:
            page = session.new_page("owner")
            page.goto(server.url("/ui"))
            page.evaluate("void fetch('/slow')")
            deadline = time.monotonic() + 2
            while "/slow" not in server.paths:
                if time.monotonic() >= deadline:
                    pytest.fail("slow preparation request did not reach the server")
                page.wait_for_timeout(20)
            signals["start"] = True
            assert session.wait_for_capture_start(page, "owner")
            page.fill("input[name='password']", sentinel)
            page.click("button[data-testid='submit']")
            page.wait_for_timeout(350)
            signals["stop"] = True
            assert session.stop_requested()

        result = BrowserRecordingAdapter().run(
            request,
            interact,
            known_secrets=(sentinel,),
            capture_controlled=True,
            start_requested=lambda: signals["start"],
            stop_requested=lambda: signals["stop"],
        )

    assert result.result_type is RecordingRunnerResultType.CAPTURED
    assert result.recording_state.value == "PROCESSING"
    urls = tuple(event.url or "" for event in result.events)
    assert not any("/ui" in url or "/slow" in url for url in urls), [
        (event.kind.value, event.url) for event in result.events
    ]
    assert any(event.kind is RecordingEventKind.UI_INPUT_CHANGE for event in result.events)
    assert any(
        event.kind is RecordingEventKind.REQUEST and "/echo" in (event.url or "")
        for event in result.events
    )
    encoded = canonical_recording_json_bytes(result, known_secrets=(sentinel,))
    assert sentinel.encode() not in encoded


@pytest.mark.parametrize("boundary", ["redirect", "iframe", "popup", "fetch", "websocket"])
def test_browser_blocks_every_target_escape_before_network(
    boundary: str,
) -> None:
    sentinel = "recording-block-secret-sentinel"
    with browser_server(sentinel) as allowed, browser_server(sentinel) as blocked:
        request = recording_request(allowed.server_port)
        blocked_http = blocked.url("/outside")
        blocked_ws = f"ws://127.0.0.1:{blocked.server_port}/socket"

        def interact(session: RecordingBrowserSession) -> None:
            page = session.new_page("owner")
            if boundary == "redirect":
                page.goto(allowed.url(f"/redirect?target={quote(blocked_http, safe='')}"))
            elif boundary == "iframe":
                page.goto(
                    allowed.url(
                        f"/blocked-iframe?target={quote(blocked_http, safe='')}"
                    )
                )
                page.wait_for_timeout(200)
            elif boundary == "popup":
                page.goto(
                    allowed.url(
                        f"/blocked-popup?target={quote(blocked_http, safe='')}"
                    )
                )
                page.click("#blocked")
                page.wait_for_timeout(200)
            elif boundary == "fetch":
                page.goto(allowed.url())
                page.evaluate(
                    "url => fetch(url).catch(() => undefined)",
                    blocked_http,
                )
            else:
                page.goto(allowed.url())
                page.evaluate("url => new WebSocket(url)", blocked_ws)
                page.wait_for_timeout(200)

        result = BrowserRecordingAdapter().run(
            request,
            interact,
            known_secrets=(sentinel,),
        )

        assert result.result_type is RecordingRunnerResultType.SAFETY_STOPPED
        assert any(
            event.kind is RecordingEventKind.SAFETY_BLOCKED
            for event in result.events
        )
        assert blocked.paths == []
        assert sentinel.encode() not in canonical_recording_json_bytes(
            result, known_secrets=(sentinel,)
        )


@pytest.mark.parametrize("path", ["/stream", "/no-length"])
def test_browser_safely_stops_unsupported_unbounded_response_modes(path: str) -> None:
    sentinel = "recording-response-secret-sentinel"
    with browser_server(sentinel) as server:
        result = BrowserRecordingAdapter().run(
            recording_request(server.server_port),
            lambda session: session.new_page("owner").goto(server.url(path)),
            known_secrets=(sentinel,),
        )

    assert result.result_type is RecordingRunnerResultType.SAFETY_STOPPED
    assert "UNSUPPORTED_RESPONSE" in result.reason_codes
    assert any(
        event.reason_code == "RECORD_RESPONSE_UNSUPPORTED"
        for event in result.events
    )


def test_browser_init_script_captures_ui_metadata_without_input_values() -> None:
    sentinel = "ui-secret"
    with browser_server(sentinel) as server:
        def interact(session: RecordingBrowserSession) -> None:
            page = session.new_page("owner")
            page.goto(server.url("/ui"))
            page.fill('input[name="password"]', sentinel)
            page.click('[data-testid="submit"]')
            page.wait_for_timeout(300)

        result = BrowserRecordingAdapter().run(
            recording_request(server.server_port),
            interact,
            known_secrets=(sentinel,),
        )

    kinds = {event.kind for event in result.events}
    assert RecordingEventKind.UI_INPUT_CHANGE in kinds
    assert RecordingEventKind.UI_CLICK in kinds
    assert RecordingEventKind.UI_SUBMIT in kinds
    submit = next(
        event for event in result.events if event.kind is RecordingEventKind.UI_SUBMIT
    )
    request = next(
        event
        for event in result.events
        if event.kind is RecordingEventKind.REQUEST and event.method == "POST"
    )
    assert request.caused_by_action_id == submit.action_id
    assert all(event.body is None for event in result.events if event.action_id)
    assert sentinel.encode() not in canonical_recording_json_bytes(
        result,
        known_secrets=(sentinel,),
    )
