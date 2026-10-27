# 验证录制基础设施中的浏览器录制边界。

from __future__ import annotations
from unittest.mock import Mock
from product.backend.infrastructure.recording.events import RecordingEventCollector

import time
from urllib.parse import quote

import pytest

from product.protocols.recording.events import RecordingEventKind, RecordingRunnerResultType, canonical_recording_json_bytes
from product.backend.infrastructure.recording.browser import BrowserRecordingAdapter, RecordingBrowserSession

pytestmark = [pytest.mark.level4, pytest.mark.browser, pytest.mark.slow]

from tests.support.builders.preparation.recording import COOKIE_ENV_NAME, TEST_IDENTITY_ID, browser_server, recording_request


def test_preparation_request_finished_never_reads_response_or_body():
    request = recording_request(8765)
    collector = RecordingEventCollector(request.target_scope, request.budget, (), lambda: 1, started_at_us=1)
    callback_request = Mock()
    callback_request.response.side_effect = AssertionError("准备期不可读取 response/body")
    collector._request_finished(TEST_IDENTITY_ID, callback_request)
    callback_request.response.assert_not_called()
    assert collector.events == ()


def test_browser_contexts_isolate_identity_state_and_redact_before_result(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    sentinel = "recording-browser-secret-sentinel"
    observed: dict[str, object] = {}
    with browser_server(sentinel) as server:
        request = recording_request(server.server_port)

        def interact(session: RecordingBrowserSession) -> None:
            owner = session.new_page(TEST_IDENTITY_ID)
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
            owner.wait_for_timeout(200)
            owner.goto(
                server.url(
                    f"/secret?token={quote(sentinel)}&note={quote(sentinel)}"
                )
            )
        result = BrowserRecordingAdapter().run(
            request,
            interact,
            known_secrets=(sentinel,),
            secret_values={COOKIE_ENV_NAME: sentinel},
        )

    assert result.result_type is RecordingRunnerResultType.CAPTURED
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
            page = session.new_page(TEST_IDENTITY_ID)
            page.goto(server.url("/ui"))
            page.evaluate("void fetch('/slow')")
            deadline = time.monotonic() + 2
            while "/slow" not in server.paths:
                if time.monotonic() >= deadline:
                    pytest.fail("slow preparation request did not reach the server")
                page.wait_for_timeout(20)
            signals["start"] = True
            assert session.wait_for_capture_start(page, TEST_IDENTITY_ID)
            page.fill("input[name='password']", sentinel)
            page.click("button[data-testid='submit']")
            page.wait_for_timeout(350)
            signals["stop"] = True
            assert session.stop_requested()

        result = BrowserRecordingAdapter().run(
            request,
            interact,
            known_secrets=(sentinel,),
            secret_values={COOKIE_ENV_NAME: sentinel},
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
            page = session.new_page(TEST_IDENTITY_ID)
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
            secret_values={COOKIE_ENV_NAME: sentinel},
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
            lambda session: session.new_page(TEST_IDENTITY_ID).goto(server.url(path)),
            known_secrets=(sentinel,),
            secret_values={COOKIE_ENV_NAME: sentinel},
        )

    assert result.result_type is RecordingRunnerResultType.SAFETY_STOPPED
    assert "UNSUPPORTED_RESPONSE" in result.reason_codes
    assert any(
        event.reason_code in {"SSE_UNSUPPORTED", "CONTENT_LENGTH_REQUIRED"}
        for event in result.events
    )


def test_browser_init_script_captures_ui_metadata_without_input_values() -> None:
    sentinel = "ui-secret"
    with browser_server(sentinel) as server:
        def interact(session: RecordingBrowserSession) -> None:
            page = session.new_page(TEST_IDENTITY_ID)
            page.goto(server.url("/ui"))
            page.fill('input[name="password"]', sentinel)
            page.click('[data-testid="submit"]')
            page.wait_for_timeout(300)

        result = BrowserRecordingAdapter().run(
            recording_request(server.server_port),
            interact,
            known_secrets=(sentinel,),
            secret_values={COOKIE_ENV_NAME: sentinel},
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


def test_intercepted_login_preserves_cookie_path_without_expanding_host_scope(monkeypatch):
    import httpx
    from playwright.sync_api import sync_playwright
    from product.backend.infrastructure.recording.transport import BoundedRouteTransport
    # 只操作临时浏览器内存，不请求外部域名，也不写Windows凭据。
    login = 'http://app.example.test/session/login'
    response = httpx.Response(200, request=httpx.Request('POST', login), headers=[
        ('Set-Cookie', 'root_session=temporary-root; Path=/; HttpOnly; SameSite=Strict'),
        ('Set-Cookie', 'private_session=temporary-private; Path=/private; HttpOnly'),
    ])
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context()
            BoundedRouteTransport._apply_response_cookies(context, login, response)
            assert {item['name'] for item in context.cookies('http://app.example.test/service/tickets')} == {'root_session'}
            assert {item['name'] for item in context.cookies('http://app.example.test/private/one')} == {'root_session', 'private_session'}
            from types import SimpleNamespace
            observed = []
            client_type = httpx.Client
            def receive(request):
                observed.append(request.headers.get('cookie'))
                return httpx.Response(200, stream=httpx.ByteStream(b'{}'), headers={'Content-Type':'application/json','Content-Length':'2'})
            monkeypatch.setattr(httpx,'Client',lambda **kwargs:client_type(transport=httpx.MockTransport(receive),**kwargs))
            request = SimpleNamespace(url='http://app.example.test/private-other',headers={},method='GET',post_data_buffer=None)
            BoundedRouteTransport(SimpleNamespace(timeout_seconds=5,max_response_bytes=1024)).fetch(request,context,Mock())
            assert observed == ['root_session=temporary-root']
            for host in ('sub.app.example.test','other.example.test'):
                request.url = 'http://'+host+'/service/tickets'
                BoundedRouteTransport(SimpleNamespace(timeout_seconds=5,max_response_bytes=1024)).fetch(request,context,Mock())
            assert observed[1:] == [None,None]
            root = next(item for item in context.cookies() if item['name'] == 'root_session')
            assert root['path'] == '/' and root['httpOnly'] and root['sameSite'] == 'Strict'
        finally:
            browser.close()
